from __future__ import annotations

import json
import re
from itertools import combinations

from app.services.pid_extraction import (
    HAS_PDFPLUMBER,
    extract_tags_from_text,
    generate_bom_from_tags,
)

if HAS_PDFPLUMBER:
    import pdfplumber

CONFIDENCE_THRESHOLD = 0.7
COLOUR_CONFIDENCE_THRESHOLD = 0.8
PAIR_JACCARD_THRESHOLD = 0.6
PAGE_SCORE_THRESHOLD = 0.8

DEMO_FREETEXT = [
    r"DEMO\s+DRAWING",
    r"ALL\s+BOLD\s+PIPING\s+AND\s+EQUIPMENT\s+IS\s+DEMO(?:LITION)?\s+SCOPE",
    r"DEMOLITION\s+DRAWING",
]
NEW_FREETEXT = [
    r"NEW\s+INSTALLATION\s+DRAWING",
    r"NEW\s+WORK",
    r"ALL\s+BOLD\s+PIPING\s+AND\s+EQUIPMENT\s+IS\s+IN\s+SCOPE",
]
DEMO_TITLE = [r"DEMO(?:LITION)?\s+DRAWING", r"\(\s*DEMO(?:LITION)?\s*\)", r"\bDEMO(?:LITION)?\b"]
NEW_TITLE = [r"NEW\s+INSTALLATION(?:\s+DRAWING)?", r"\(\s*NEW\s*\)", r"\bNEW\s+WORK\b"]
LABEL_WORDS = re.compile(
    r"DEMO(?:LITION)?|NEW\s+INSTALLATION|NEW\s+WORK|\bNEW\b|DRAWING|[()\-:]", re.IGNORECASE
)
LEGEND_KEYWORDS = ["LEGEND", "ABBREVIATION", "SYMBOL", "IDENTIFICATION", "KEY", "INSTRUMENT"]
ABBREV_LINE = re.compile(r"^\s*([A-Z][A-Z0-9/]{0,5})\s*[-:=]\s*(\S.*)$")

QUESTION = "Which page is the demolition/before state? Which is the new work/after state?"


def _pdf_pages(pdf_path: str):
    if not HAS_PDFPLUMBER:
        raise RuntimeError("pdfplumber is required for scope-aware BOM generation")
    return pdfplumber.open(pdf_path)


def _count_pages(pdf_path: str) -> int:
    with _pdf_pages(pdf_path) as pdf:
        return len(pdf.pages)


def _colour_key(colour) -> str | None:
    if not colour:
        return None
    try:
        return json.dumps([round(float(c), 3) for c in colour], separators=(",", ":"))
    except (TypeError, ValueError):
        return None


def _annot_colour(annot: dict):
    data = annot.get("data") or {}
    colour = annot.get("color") or annot.get("non_stroking_color")
    if not colour:
        raw = data.get("C")
        colour = raw if isinstance(raw, (list, tuple)) else None
    return _colour_key(colour)


def _annot_subtype(annot: dict) -> str:
    sub = annot.get("subtype") or (annot.get("data") or {}).get("Subtype")
    return str(sub).strip("/'\"") if sub is not None else ""


def _annot_contents(annot: dict) -> str:
    contents = annot.get("contents")
    if contents is None:
        raw = (annot.get("data") or {}).get("Contents")
        contents = raw if isinstance(raw, str) else ""
    return str(contents or "")


def _matches(patterns: list[str], text: str) -> int:
    return sum(1 for p in patterns if re.search(p, text, re.IGNORECASE))


def _score(demo_hits: int, new_hits: int, strength: float) -> tuple[float, float]:
    def conv(n: int) -> float:
        return min(1.0, strength + 0.05 * (n - 1)) if n else 0.0
    return conv(demo_hits), conv(new_hits)


def score_page_by_freetext(page_text: str) -> dict:
    """Score a page's annotation/notes text for demo vs new-work keywords."""
    text = page_text or ""
    demo, new = _score(_matches(DEMO_FREETEXT, text), _matches(NEW_FREETEXT, text), 0.9)
    return {"demo": demo, "new_work": new, "method": "freetext"}


def _title_lines(page_text: str) -> list[str]:
    return [ln.strip() for ln in (page_text or "").splitlines() if 0 < len(ln.strip()) <= 80]


def score_page_by_title(page_text: str) -> dict:
    """Score a page by title patterns such as 'DEMO DRAWING' or 'EQUIPMENT PAD (NEW)'."""
    demo = new = 0.0
    for line in _title_lines(page_text):
        d, n = _score(_matches(DEMO_TITLE, line), _matches(NEW_TITLE, line), 0.85)
        demo, new = max(demo, d), max(new, n)
    return {"demo": demo, "new_work": new, "method": "title"}


def page_title_key(page_text: str) -> str | None:
    """Title with demo/new labels stripped, e.g. 'EQUIPMENT PAD'. None if no labelled title."""
    for line in _title_lines(page_text):
        if _matches(DEMO_TITLE + NEW_TITLE, line):
            key = re.sub(r"\s+", " ", LABEL_WORDS.sub(" ", line)).strip().upper()
            if key:
                return key
    return None


def extract_page_content_signature(pdf_path: str, page_num: int) -> dict:
    """Extract tags, colours and notes from a page (1-based page_num)."""
    with _pdf_pages(pdf_path) as pdf:
        page = pdf.pages[page_num - 1]
        text = page.extract_text() or ""
        notes: list[str] = []
        colours: list[str] = []
        for annot in page.annots or []:
            sub = _annot_subtype(annot)
            if sub in ("Link", "Popup"):
                continue
            contents = _annot_contents(annot).strip()
            if sub == "FreeText":
                if contents:
                    notes.append(contents)
                continue
            colour = _annot_colour(annot)
            if colour:
                colours.append(colour)
    tags = {t["tag"] for t in extract_tags_from_text(text)}
    for note in notes:
        tags |= {t["tag"] for t in extract_tags_from_text(note)}
    return {
        "tags": tags,
        "tag_count": len(tags),
        "colours": colours,
        "text": text,
        "freetext_notes": notes,
    }


def _jaccard(a: set, b: set) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def find_page_pairs_by_content(pdf_path: str, signatures: dict) -> list[tuple]:
    """Pairwise Jaccard similarity of tag sets. Returns (page_a, page_b, similarity, overlap_tags)."""
    pairs = []
    for a, b in combinations(sorted(signatures), 2):
        tags_a, tags_b = signatures[a]["tags"], signatures[b]["tags"]
        if not tags_a or not tags_b:
            continue
        sim = _jaccard(tags_a, tags_b)
        if sim >= PAIR_JACCARD_THRESHOLD:
            pairs.append((a, b, sim, sorted(tags_a & tags_b)))
    pairs.sort(key=lambda p: (-p[2], p[0], p[1]))
    return pairs


def _dominant_hue(colours: list[str]) -> str | None:
    """'red' / 'green' when RGB annotations are clearly dominated by one of them."""
    counts = {"red": 0, "green": 0}
    for key in colours:
        rgb = json.loads(key)
        if len(rgb) != 3:
            continue
        r, g, b = rgb
        if r > 0.6 and g < 0.4 and b < 0.4:
            counts["red"] += 1
        elif g > 0.6 and r < 0.4 and b < 0.4:
            counts["green"] += 1
    best = max(counts, key=counts.get)
    if counts[best] == 0 or counts["red"] == counts["green"]:
        return None
    return best


def content_differences(demo_tags: set, new_tags: set) -> dict:
    return {
        "added": sorted(new_tags - demo_tags),
        "removed": sorted(demo_tags - new_tags),
        "unchanged": sorted(demo_tags & new_tags),
    }


def _pair_detail(a: int, b: int, sim: float, signatures: dict) -> dict:
    return {
        "pages": [a, b],
        "similarity": round(sim, 3),
        "message": f"Pages {a} and {b} appear to show similar layouts",
        "tags": {str(a): sorted(signatures[a]["tags"]), str(b): sorted(signatures[b]["tags"])},
        "differences": content_differences(signatures[a]["tags"], signatures[b]["tags"]),
    }


def classify_signatures(signatures: dict, pairs: list[tuple] | None = None) -> dict:
    """Classify pages from precomputed signatures (see classify_pages_by_content)."""
    cls: dict[int, dict] = {}
    unresolved_labels: dict[int, str] = {}

    for page, sig in sorted(signatures.items()):
        ft = score_page_by_freetext("\n".join(sig["freetext_notes"]))
        ti = score_page_by_title(sig["text"])
        for scores in (ft, ti):
            d, n = scores["demo"], scores["new_work"]
            if max(d, n) >= PAGE_SCORE_THRESHOLD and abs(d - n) >= 0.3:
                cls[page] = {
                    "label": "demo" if d > n else "new_work",
                    "method": scores["method"],
                    "confidence": max(d, n),
                }
                break

    keys = {p: page_title_key(s["text"]) for p, s in signatures.items()}
    for p, q in combinations(sorted(signatures), 2):
        if keys[p] and keys[p] == keys[q] and (p in cls) != (q in cls):
            known, other = (p, q) if p in cls else (q, p)
            cls[other] = {
                "label": "new_work" if cls[known]["label"] == "demo" else "demo",
                "method": "title_match",
                "confidence": 0.8,
            }

    if pairs is None:
        pairs = find_page_pairs_by_content(None, signatures)
    ambiguous = []
    changed = True
    while changed:
        changed = False
        ambiguous = []
        for a, b, sim, _overlap in pairs:
            if a in cls and b in cls:
                continue
            if a in cls or b in cls:
                known, other = (a, b) if a in cls else (b, a)
                cls[other] = {
                    "label": "new_work" if cls[known]["label"] == "demo" else "demo",
                    "method": "content_match",
                    "confidence": round(min(0.9, 0.6 + 0.4 * sim), 3),
                }
                changed = True
                break
            hue_a = _dominant_hue(signatures[a]["colours"])
            hue_b = _dominant_hue(signatures[b]["colours"])
            if {hue_a, hue_b} == {"red", "green"}:
                demo, new = (a, b) if hue_a == "red" else (b, a)
                conf = round(min(0.9, 0.5 + 0.4 * sim), 3)
                cls[demo] = {"label": "demo", "method": "content_match+colour", "confidence": conf}
                cls[new] = {"label": "new_work", "method": "content_match+colour", "confidence": conf}
                changed = True
                break
            ambiguous.append(_pair_detail(a, b, sim, signatures))

    demo_pages = sorted(p for p, c in cls.items() if c["label"] == "demo")
    new_pages = sorted(p for p, c in cls.items() if c["label"] == "new_work")
    confidences = [c["confidence"] for c in cls.values()]
    confidence = round(min(confidences), 3) if confidences else 0.0
    methods = sorted({c["method"] for c in cls.values()})
    return {
        "demo_pages": demo_pages,
        "new_work_pages": new_pages,
        "page_classification": {str(p): c for p, c in sorted(cls.items())},
        "method": "+".join(methods) if methods else "none",
        "confidence": confidence,
        "ambiguous_pairs": ambiguous,
    }


def classify_pages_by_content(pdf_path: str) -> dict:
    """Classify pages as demo / new work: FreeText, then title, then content comparison."""
    signatures = {
        n: extract_page_content_signature(pdf_path, n) for n in range(1, _count_pages(pdf_path) + 1)
    }
    pairs = find_page_pairs_by_content(pdf_path, signatures)
    result = classify_signatures(signatures, pairs)
    result["signatures"] = signatures
    return result


def detect_colour_meaning(pdf_path: str, demo_pages: list, new_work_pages: list) -> dict:
    """Infer colour meanings from how often each annotation colour appears on each page type."""
    counts: dict[str, dict[str, int]] = {}
    by_page: dict[str, list[str]] = {}
    for label, pages in (("demo", demo_pages), ("new_work", new_work_pages)):
        for page in pages:
            colours = extract_page_content_signature(pdf_path, page)["colours"]
            by_page[str(page)] = sorted(set(colours))
            for colour in colours:
                counts.setdefault(colour, {"demo": 0, "new_work": 0})[label] += 1
    meanings = {}
    for colour, c in counts.items():
        total = c["demo"] + c["new_work"]
        if c["demo"] == c["new_work"]:
            meanings[colour] = {"meaning": "unknown", "confidence": 0.0, "counts": c}
            continue
        meaning = "demo" if c["demo"] > c["new_work"] else "new_work"
        share = max(c["demo"], c["new_work"]) / total
        conf = round(share if total >= 2 else min(share, 0.75), 3)
        meanings[colour] = {"meaning": meaning, "confidence": conf, "counts": c}
    resolved = [m["meaning"] for m in meanings.values() if m["meaning"] != "unknown"]
    return {
        "colour_meanings": meanings,
        "colours_by_page": by_page,
        "colours_present": bool(counts),
        "colour_variation": len(counts) > 1,
        "confidence": round(min((m["confidence"] for m in meanings.values()), default=0.0), 3),
        "known": bool(meanings) and len(resolved) == len(meanings),
        "source": "auto",
    }


def extract_legend(pdf_path: str) -> dict:
    """Locate the legend / identification key page by keyword scoring and read its abbreviations."""
    best_page, best_score, best_text = None, 0, ""
    with _pdf_pages(pdf_path) as pdf:
        for n, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            upper = text.upper()
            score = sum(upper.count(k) for k in LEGEND_KEYWORDS)
            if score > best_score:
                best_page, best_score, best_text = n, score, text
    if not best_page or best_score < 2:
        return {"found": False, "page": None, "abbreviations": {}, "confidence": 0.0}
    abbreviations = {}
    for line in best_text.splitlines():
        m = ABBREV_LINE.match(line)
        if m:
            abbreviations[m.group(1)] = m.group(2).strip()
    return {
        "found": True,
        "page": best_page,
        "abbreviations": abbreviations,
        "confidence": round(min(1.0, best_score / 5), 3),
    }


def _page_tags_with_colour(pdf_path: str, page_num: int) -> list[dict]:
    """Tags on a page, each with the colours of annotations covering them (None if uncovered)."""
    with _pdf_pages(pdf_path) as pdf:
        page = pdf.pages[page_num - 1]
        text = page.extract_text() or ""
        words = page.extract_words()
        annots = [
            a for a in (page.annots or [])
            if _annot_subtype(a) not in ("Link", "Popup", "FreeText") and _annot_colour(a)
        ]
        coloured: dict[str, set] = {}
        for annot in annots:
            inside = [
                w["text"] for w in words
                if annot["x0"] <= (w["x0"] + w["x1"]) / 2 <= annot["x1"]
                and annot["top"] <= (w["top"] + w["bottom"]) / 2 <= annot["bottom"]
            ]
            for t in extract_tags_from_text(" ".join(inside)):
                coloured.setdefault(t["tag"], set()).add(_annot_colour(annot))
    result = []
    for t in extract_tags_from_text(text):
        t = dict(t)
        t["page"] = page_num
        t["colours"] = sorted(coloured.get(t["tag"], []))
        result.append(t)
    return result


def _scope_cross_check(scope_text: str, tags: list[dict]) -> dict:
    scope = scope_text or ""
    scope_tags = {t["tag"] for t in extract_tags_from_text(scope)}
    bom_tags = {t["tag"] for t in tags}
    lowered = scope.lower()
    words = {"pump": "pump", "valve": "valve", "tank": "tank", "vent": "vent", "drain": "drain"}
    not_mentioned = []
    for t in tags:
        if t["tag"] in scope_tags:
            continue
        kind = t.get("type", "")
        if any(k in kind and w in lowered for w, k in words.items()):
            continue
        not_mentioned.append(t["tag"])
    return {
        "performed": bool(scope.strip()),
        "scope_tags_not_on_new_work_pages": sorted(scope_tags - bom_tags),
        "bom_tags_not_in_scope": sorted(not_mentioned) if scope.strip() else [],
    }


def _clarification(result: dict, message: str, signatures: dict | None) -> dict:
    out = {
        "status": "needs_clarification",
        "question": "demo_work_pages",
        "message": message,
        "prompt": QUESTION,
        "candidate_pairs": result.get("ambiguous_pairs", []),
        "page_classification": result.get("page_classification", {}),
        "classification_method": result.get("method", "none"),
        "classification_confidence": result.get("confidence", 0.0),
        "detected_tags": {
            str(p): sorted(s["tags"]) for p, s in (signatures or {}).items() if s["tags"]
        },
        "resubmit_with": ["demo_pages", "new_work_pages"],
    }
    return out


def build_scoped_bom(
    pdf_path: str,
    scope_text: str,
    demo_pages: list | None = None,
    new_work_pages: list | None = None,
    highlight_mapping: dict | None = None,
) -> dict:
    legend = extract_legend(pdf_path)

    classification = classify_pages_by_content(pdf_path)
    signatures = classification.pop("signatures")
    user_override = bool(demo_pages or new_work_pages)
    if user_override:
        demo = sorted(set(demo_pages or []))
        new = sorted(set(new_work_pages or classification["new_work_pages"]) - set(demo))
        page_cls = {str(p): {"label": "demo", "method": "user_input", "confidence": 1.0} for p in demo}
        page_cls.update(
            {str(p): {"label": "new_work", "method": "user_input", "confidence": 1.0} for p in new}
        )
        method, confidence = "user_input", 1.0
        ambiguous = []
        total = len(signatures)
        bad = [p for p in demo + new if p < 1 or p > total]
        if bad:
            return _clarification(
                classification, f"Page numbers out of range (document has {total} pages): {bad}", signatures
            )
    else:
        demo, new = classification["demo_pages"], classification["new_work_pages"]
        page_cls = classification["page_classification"]
        method, confidence = classification["method"], classification["confidence"]
        ambiguous = classification["ambiguous_pairs"]
        if ambiguous or not new or not demo or confidence < CONFIDENCE_THRESHOLD:
            return _clarification(
                classification,
                "Could not determine demo and new-work pages with sufficient confidence.",
                signatures,
            )
    if not new:
        return _clarification(classification, "No new-work pages were identified.", signatures)

    demo_tags = set().union(*(signatures[p]["tags"] for p in demo)) if demo else set()
    new_tags = set().union(*(signatures[p]["tags"] for p in new))
    differences = content_differences(demo_tags, new_tags)

    if highlight_mapping:
        meanings = {
            k: {"meaning": v, "confidence": 1.0} for k, v in highlight_mapping.items()
        }
        colour_detection = {
            "colour_meanings": meanings, "colours_present": True, "known": True,
            "confidence": 1.0, "source": "user_input", "colour_variation": len(meanings) > 1,
        }
    else:
        colour_detection = detect_colour_meaning(pdf_path, demo, new)
    colours_known = bool(colour_detection["colour_meanings"]) and (
        colour_detection["confidence"] >= COLOUR_CONFIDENCE_THRESHOLD
        and colour_detection["known"]
    )
    mapping = {k: v["meaning"] for k, v in colour_detection["colour_meanings"].items()}

    tags: dict[str, dict] = {}
    for page in new:
        for t in _page_tags_with_colour(pdf_path, page):
            existing = tags.get(t["tag"])
            if existing:
                existing["pages"].append(page)
                existing["colours"] = sorted(set(existing["colours"]) | set(t["colours"]))
            else:
                t["pages"] = [page]
                tags[t["tag"]] = t

    flags: list[dict] = []

    def flag(kind: str, message: str, pages: list, **extra) -> None:
        flags.append({
            "type": kind, "message": message, "pages": pages,
            "classification_method": method, "classification_confidence": confidence, **extra,
        })

    flag(
        "page_classification",
        f"Demo pages {demo or 'none'}; new-work pages {new} (method: {method}, confidence {confidence:.2f})",
        sorted(demo + new),
    )
    flag(
        "content_differences",
        f"Tags added: {len(differences['added'])}, removed: {len(differences['removed'])}, "
        f"unchanged: {len(differences['unchanged'])}",
        sorted(demo + new),
        differences=differences,
    )
    if not legend["found"]:
        flag("legend_not_found", "Legend / identification key was not found; descriptions are generic.", [])

    included = []
    for t in tags.values():
        meanings = {mapping.get(c, "unknown") for c in t["colours"]}
        if colours_known:
            if t["colours"] and meanings == {"demo"}:
                continue
            if not t["colours"]:
                flag("colour_unknown", f"{t['tag']} has no colour annotation; manual review needed",
                     t["pages"], tag=t["tag"])
            elif len(meanings) > 1:
                flag("mixed_colour", f"{t['tag']} has mixed colours; manual review needed",
                     t["pages"], tag=t["tag"])
            elif meanings != {"new_work"}:
                flag("colour_unknown", f"{t['tag']} colour meaning unknown; manual review needed",
                     t["pages"], tag=t["tag"])
        else:
            flag("colour_unknown", f"{t['tag']}: colour unknown, manual review needed",
                 t["pages"], tag=t["tag"])
        included.append(t)

    if not colours_known:
        flag("colours_unresolved", "Colour meanings are unknown or low confidence; no colour filtering applied.",
             sorted(new))

    cross = _scope_cross_check(scope_text, included)
    for tag in cross["bom_tags_not_in_scope"]:
        flag("scope_mismatch", f"{tag} is on new-work pages but not described in the scope text",
             tags[tag]["pages"], tag=tag)
    for tag in cross["scope_tags_not_on_new_work_pages"]:
        flag("scope_mismatch", f"{tag} is in the scope text but not on the new-work pages", sorted(new), tag=tag)

    untagged = [p for p in new if not signatures[p]["tags"]]
    for p in untagged:
        flag("untagged_page", f"Page {p} has no detectable tags", [p])

    materials = generate_bom_from_tags(included)
    return {
        "status": "ok",
        "legend": legend,
        "demo_pages": demo,
        "new_work_pages": new,
        "page_classification": page_cls,
        "classification_method": method,
        "classification_confidence": confidence,
        "user_override": user_override,
        "content_differences": differences,
        "colour_detection": colour_detection,
        "colour_filtering_applied": colours_known,
        "tags": included,
        "materials": materials,
        "scope_cross_check": cross,
        "flags": flags,
    }
