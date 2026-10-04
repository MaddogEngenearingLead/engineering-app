"""Unified scope-aware BOM generation.

Single pipeline (see ``build_scoped_bom``):
  1. classify pages (FreeText -> title -> Jaccard content pairing -> colour tiebreak)
  2. detect and parse the legend / instrument key
  3. extract tags from new-work pages
  4. detect colour meanings (only once page roles are known)
  5. cross-check against the scope text
  6. build BOM, flags and BOM PDF/JSON/CSV
  7. return ``completed`` or ``needs_clarification``
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:  # pragma: no cover
    HAS_PDFPLUMBER = False

from app.services.bom_export import export_bom_to_pdf, export_bom_to_json, export_bom_to_csv
from app.services.pid_extraction import (
    extract_tags_from_text,
    generate_bom_from_tags,
    infer_equipment_type,
)

DEMO = "demo"
NEW_WORK = "new_work"

JACCARD_PAIR_THRESHOLD = 0.4

DEMO_FREETEXT_KEYWORDS = ("demo drawing", "demolition", "to be removed", "remove existing", "demo")
NEW_FREETEXT_KEYWORDS = ("new installation", "new work", "new construction", "to be installed", "install new")
DEMO_TITLE_KEYWORDS = ("demo", "demolition", "removal", "existing")
NEW_TITLE_KEYWORDS = ("new installation", "new work", "proposed", "new")

LEGEND_KEYWORDS = ("legend", "abbreviation", "symbols", "general notes", "instrument identification", "instrument key")

COLOUR_NAMES = {
    "red": (1.0, 0.0, 0.0),
    "green": (0.0, 1.0, 0.0),
    "blue": (0.0, 0.0, 1.0),
    "yellow": (1.0, 1.0, 0.0),
    "pink": (1.0, 0.0, 1.0),
    "magenta": (1.0, 0.0, 1.0),
    "cyan": (0.0, 1.0, 1.0),
    "orange": (1.0, 0.5, 0.0),
}

ISA_FIRST_LETTERS = {
    "A": "Analysis", "B": "Burner", "C": "Conductivity", "D": "Density", "E": "Voltage",
    "F": "Flow", "G": "Gauging", "H": "Hand", "I": "Current", "J": "Power", "K": "Time",
    "L": "Level", "M": "Moisture", "P": "Pressure", "Q": "Quantity", "R": "Radiation",
    "S": "Speed", "T": "Temperature", "V": "Vibration", "W": "Weight", "Y": "Event", "Z": "Position",
}
ISA_SUCCEEDING_LETTERS = {
    "A": "Alarm", "C": "Controller", "E": "Element", "G": "Glass", "H": "High", "I": "Indicator",
    "L": "Low", "R": "Recorder", "S": "Switch", "T": "Transmitter", "V": "Valve", "Y": "Relay",
}

SCOPE_KEYWORDS = ("tank", "pump", "valve", "gauge", "filter", "vent", "switch", "sensor", "indicator", "relief")


# --------------------------------------------------------------------------
# Page scoring
# --------------------------------------------------------------------------

def _score_text(text: str, demo_kw: tuple, new_kw: tuple) -> dict:
    lowered = (text or "").lower()
    demo_hits = sum(1 for k in demo_kw if k in lowered)
    new_hits = sum(1 for k in new_kw if k in lowered)
    if demo_hits and new_hits:
        # Longer, more specific phrases decide; tie is ambiguous
        demo_len = max(len(k) for k in demo_kw if k in lowered)
        new_len = max(len(k) for k in new_kw if k in lowered)
        if demo_len == new_len:
            return {"role": None, "score": 0.0, "demo_hits": demo_hits, "new_work_hits": new_hits}
        role = DEMO if demo_len > new_len else NEW_WORK
        return {"role": role, "score": 0.5, "demo_hits": demo_hits, "new_work_hits": new_hits}
    if demo_hits:
        return {"role": DEMO, "score": 1.0, "demo_hits": demo_hits, "new_work_hits": 0}
    if new_hits:
        return {"role": NEW_WORK, "score": 1.0, "demo_hits": 0, "new_work_hits": new_hits}
    return {"role": None, "score": 0.0, "demo_hits": 0, "new_work_hits": 0}


def score_page_by_freetext(text: str) -> dict:
    """Score FreeText annotation text such as 'DEMO DRAWING' / 'NEW INSTALLATION DRAWING'."""
    return _score_text(text, DEMO_FREETEXT_KEYWORDS, NEW_FREETEXT_KEYWORDS)


def score_page_by_title(text: str) -> dict:
    """Score the title/title-block text of a page."""
    return _score_text(text, DEMO_TITLE_KEYWORDS, NEW_TITLE_KEYWORDS)


# --------------------------------------------------------------------------
# Content signatures and pairing
# --------------------------------------------------------------------------

def _normalise_colour(value) -> tuple | None:
    """Return a rounded RGB tuple for coloured (non grey) values, else None."""
    if value is None:
        return None
    try:
        vals = [float(v) for v in value]
    except (TypeError, ValueError):
        return None
    if len(vals) == 3:
        r, g, b = vals
    elif len(vals) == 4:
        c, m, y, k = vals
        r, g, b = (1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k)
    else:
        return None
    if max(r, g, b) - min(r, g, b) < 0.15:
        return None
    return (round(r, 1), round(g, 1), round(b, 1))


def colour_key(rgb) -> str:
    return "[" + ",".join(f"{v:g}" for v in rgb) + "]"


def _freetext_from_page(page) -> str:
    texts = []
    for annot in getattr(page, "annots", None) or []:
        data = annot.get("data") or {}
        subtype = str(data.get("Subtype", annot.get("subtype", "")))
        if "FreeText" not in subtype:
            continue
        contents = annot.get("contents") or data.get("Contents") or ""
        if isinstance(contents, bytes):
            contents = contents.decode("utf-8", "ignore")
        texts.append(str(contents))
    return "\n".join(texts)


def extract_page_content_signature(pdf, page_num: int) -> dict:
    """Signature for a page (``page_num`` is 1-based): tags, colours, words, FreeText."""
    page = pdf.pages[page_num - 1]
    text = page.extract_text() or ""
    tags = {t["tag"] for t in extract_tags_from_text(text)}
    colours: Counter = Counter()
    for char in page.chars:
        c = _normalise_colour(char.get("non_stroking_color"))
        if c:
            colours[c] += 1
    for kind in ("rects", "lines", "curves"):
        for obj in getattr(page, kind, []) or []:
            for field in ("stroking_color", "non_stroking_color"):
                c = _normalise_colour(obj.get(field))
                if c:
                    colours[c] += 1
    for annot in getattr(page, "annots", None) or []:
        c = _normalise_colour(annot.get("color") or (annot.get("data") or {}).get("C"))
        if c:
            colours[c] += 1
    words = {w.upper() for w in re.findall(r"[A-Za-z]{3,}", text)}
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return {
        "page": page_num,
        "text": text,
        "title_text": "\n".join(lines[-5:]),
        "freetext": _freetext_from_page(page),
        "tags": tags,
        "words": words,
        "colours": colours,
    }


def _jaccard(a: set, b: set) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def find_page_pairs_by_content(sigs: list[dict]) -> list[tuple]:
    """Mutually-best page pairs by Jaccard similarity: ``(page_a, page_b, score)``."""
    scored = []
    for i, a in enumerate(sigs):
        for b in sigs[i + 1:]:
            score = _jaccard(a["tags"] | a["words"], b["tags"] | b["words"])
            if a["tags"] and b["tags"]:
                score = max(score, _jaccard(a["tags"], b["tags"]))
            if score >= JACCARD_PAIR_THRESHOLD:
                scored.append((a["page"], b["page"], round(score, 3)))
    scored.sort(key=lambda p: -p[2])
    used: set = set()
    pairs = []
    for pa, pb, score in scored:
        if pa in used or pb in used:
            continue
        used.update((pa, pb))
        pairs.append((pa, pb, score))
    return pairs


# --------------------------------------------------------------------------
# Colour meaning
# --------------------------------------------------------------------------

def _meaning_of(value) -> str | None:
    return value.get("meaning") if isinstance(value, dict) else value


def normalise_highlight_mapping(mapping: dict | None) -> dict:
    """Accept colour names or '[r,g,b]' keys; return ``{colour_key: meaning}``."""
    out = {}
    for key, value in (mapping or {}).items():
        meaning = _meaning_of(value)
        k = str(key).strip().lower()
        if k in COLOUR_NAMES:
            out[colour_key(COLOUR_NAMES[k])] = meaning
            continue
        try:
            rgb = tuple(float(x) for x in json.loads(k))
            out[colour_key(_normalise_colour(rgb) or rgb)] = meaning
        except (ValueError, TypeError):
            continue
    return out


def detect_colour_meaning(demo_pages: list[dict], new_work_pages: list[dict]) -> dict:
    """Infer colour meaning from signatures of pages already classified.

    Colours only on demo pages -> demo; only on new-work pages -> new_work;
    colours on both -> shared/unknown.
    """
    demo: Counter = Counter()
    new: Counter = Counter()
    for s in demo_pages:
        demo.update(s["colours"])
    for s in new_work_pages:
        new.update(s["colours"])
    result = {}
    for colour in set(demo) | set(new):
        d, n = demo.get(colour, 0), new.get(colour, 0)
        total = d + n
        if d and not n:
            meaning, conf = DEMO, 0.9
        elif n and not d:
            meaning, conf = NEW_WORK, 0.9
        else:
            share = max(d, n) / total
            meaning = (DEMO if d > n else NEW_WORK) if share >= 0.8 else "unknown"
            conf = round(share * 0.7, 2) if meaning != "unknown" else 0.3
        result[colour_key(colour)] = {"meaning": meaning, "confidence": conf}
    return result


# --------------------------------------------------------------------------
# Page classification
# --------------------------------------------------------------------------

def _dominant_colour_role(sig: dict, mapping: dict) -> str | None:
    votes: Counter = Counter()
    for colour, count in sig["colours"].items():
        meaning = _meaning_of(mapping.get(colour_key(colour)))
        if meaning in (DEMO, NEW_WORK):
            votes[meaning] += count
    if not votes:
        return None
    ranked = votes.most_common(2)
    if len(ranked) == 2 and ranked[0][1] == ranked[1][1]:
        return None
    return ranked[0][0]


def classify_signatures(sigs: list[dict], colour_meanings: dict | None = None) -> dict:
    """Classify pages: FreeText -> title -> Jaccard pairing -> colour tiebreak."""
    mapping = normalise_highlight_mapping(colour_meanings)
    roles: dict[int, tuple[str, str, float]] = {}  # page -> (role, method, confidence)

    for s in sigs:
        r = score_page_by_freetext(s.get("freetext", ""))
        if r["role"]:
            roles[s["page"]] = (r["role"], "freetext", 0.95)
    for s in sigs:
        if s["page"] in roles:
            continue
        r = score_page_by_title(s.get("title_text", s.get("text", "")))
        if r["role"]:
            roles[s["page"]] = (r["role"], "title", 0.85)

    by_page = {s["page"]: s for s in sigs}
    candidate_pairs = []
    pairs = find_page_pairs_by_content(sigs)
    for pa, pb, score in pairs:
        ra, rb = roles.get(pa), roles.get(pb)
        if ra and rb:
            continue
        if ra or rb:
            known, other = (pa, pb) if ra else (pb, pa)
            opposite = NEW_WORK if roles[known][0] == DEMO else DEMO
            roles[other] = (opposite, "jaccard_pairing", round(min(0.8, 0.5 + score / 2), 2))
            continue
        ca = _dominant_colour_role(by_page[pa], mapping)
        cb = _dominant_colour_role(by_page[pb], mapping)
        if ca and cb and ca != cb:
            roles[pa] = (ca, "colour_tiebreak", 0.7)
            roles[pb] = (cb, "colour_tiebreak", 0.7)
        elif ca and not cb:
            roles[pa] = (ca, "colour_tiebreak", 0.65)
            roles[pb] = (NEW_WORK if ca == DEMO else DEMO, "colour_tiebreak", 0.65)
        elif cb and not ca:
            roles[pb] = (cb, "colour_tiebreak", 0.65)
            roles[pa] = (NEW_WORK if cb == DEMO else DEMO, "colour_tiebreak", 0.65)
        else:
            candidate_pairs.append({"pages": [pa, pb], "similarity": score})

    demo = sorted(p for p, v in roles.items() if v[0] == DEMO)
    new = sorted(p for p, v in roles.items() if v[0] == NEW_WORK)
    method_rank = ["freetext", "title", "jaccard_pairing", "colour_tiebreak"]
    methods = {v[1] for v in roles.values()}
    method = next((m for m in method_rank if m in methods), None)
    confidence = round(min((v[2] for v in roles.values()), default=0.0), 2)
    ambiguous = bool(candidate_pairs) or not demo or not new
    return {
        "demo_pages": demo,
        "new_work_pages": new,
        "classification_method": method,
        "classification_confidence": confidence,
        "candidate_pairs": candidate_pairs,
        "ambiguous": ambiguous,
    }


def classify_pages_by_content(pdf, colour_meanings: dict | None = None) -> dict:
    """Classify every page of an open pdfplumber PDF by its content."""
    sigs = [extract_page_content_signature(pdf, n) for n in range(1, len(pdf.pages) + 1)]
    result = classify_signatures(sigs, colour_meanings)
    result["signatures"] = sigs
    return result


# --------------------------------------------------------------------------
# Legend / instrument key
# --------------------------------------------------------------------------

def find_legend_page(pdf) -> int | None:
    """1-based legend page chosen by keyword scoring, or None."""
    best_page, best = None, 0
    for n, page in enumerate(pdf.pages, start=1):
        lowered = (page.extract_text() or "").lower()
        score = sum(lowered.count(k) for k in LEGEND_KEYWORDS)
        score += min(len(re.findall(r"\b[A-Z]{2,6}\s*[-–=]\s*[A-Za-z]", page.extract_text() or "")), 10) * 0.3
        if score > best:
            best_page, best = n, score
    return best_page if best >= 1 else None


_LEGEND_ENTRY = re.compile(
    r"\b([A-Z][A-Z0-9/&.]{1,6})\s*[-–:=]\s+([A-Za-z][^\n]*?)(?=\s+[A-Z][A-Z0-9/&.]{1,6}\s*[-–:=]\s+[A-Za-z]|\s{3,}|\n|$)"
)


def parse_legend(text: str) -> dict:
    """Abbreviation -> description map, e.g. ``{'TK': 'Storage Tank'}``."""
    entries = {}
    for abbr, desc in _LEGEND_ENTRY.findall(text or ""):
        desc = desc.strip(" .")
        if desc and abbr not in entries:
            entries[abbr] = desc
    return entries


def parse_instrument_key(text: str) -> dict:
    """First/succeeding letter meanings; ISA defaults overridden by key text."""
    first = dict(ISA_FIRST_LETTERS)
    succeeding = dict(ISA_SUCCEEDING_LETTERS)
    found = 0
    for letter, desc in re.findall(r"(?m)^\s*([A-Z])\s*[-–:=]\s*([A-Za-z][^\n]*)$", text or ""):
        first[letter] = desc.strip()
        found += 1
    return {"first_letters": first, "succeeding_letters": succeeding, "entries_found": found}


def describe_tag(tag_id: str, legend: dict) -> dict:
    """Describe a tag. ``legend`` = ``{'abbreviations': {...}, 'instrument_key': {...}}``."""
    prefix = tag_id.split("-")[0].upper()
    abbreviations = {k.upper(): v for k, v in (legend.get("abbreviations") or {}).items()}
    if prefix in abbreviations:
        return {"tag": tag_id, "description": abbreviations[prefix], "source": "legend", "confidence": 0.95}
    equipment_type = infer_equipment_type(prefix)
    if equipment_type != "equipment":
        return {"tag": tag_id, "description": equipment_type.replace("_", " ").title(),
                "source": "prefix_map", "confidence": 0.7}
    key = legend.get("instrument_key") or {}
    first, succeeding = key.get("first_letters", {}), key.get("succeeding_letters", {})
    if len(prefix) >= 2 and prefix[0] in first and all(c in succeeding for c in prefix[1:]):
        parts = [first[prefix[0]]] + [succeeding[c] for c in prefix[1:]]
        return {"tag": tag_id, "description": " ".join(parts), "source": "instrument_letters", "confidence": 0.5}
    return {"tag": tag_id, "description": "Equipment", "source": "default", "confidence": 0.3}


# --------------------------------------------------------------------------
# Scope cross-check
# --------------------------------------------------------------------------

def cross_check_scope(scope_text: str | None, tags: list[str], descriptions: dict) -> list[dict]:
    """Flag mismatches between scope text and tags found on new-work pages."""
    if not scope_text or not scope_text.strip():
        return [{"type": "no_scope_text", "severity": "info",
                 "message": "No scope of work supplied; scope cross-check skipped."}]
    flags = []
    scope_lower = scope_text.lower()
    tag_set = set(tags)
    norm = lambda t: re.sub(r"[\s-]+", "", t.upper())
    scope_norm = norm(scope_text)
    for tag in tags:
        desc = (descriptions.get(tag) or {}).get("description", "").lower()
        in_scope = norm(tag) in scope_norm or (desc and any(w in scope_lower for w in desc.split() if len(w) > 3))
        if not in_scope:
            flags.append({"type": "tag_not_in_scope", "severity": "warning", "tag": tag,
                          "message": f"{tag} appears on new-work pages but is not mentioned in the scope."})
    for mentioned in sorted({t["tag"] for t in extract_tags_from_text(scope_text)} - tag_set):
        flags.append({"type": "scope_tag_not_found", "severity": "warning", "tag": mentioned,
                      "message": f"{mentioned} is in the scope but not on any new-work page."})
    for kw in SCOPE_KEYWORDS:
        if re.search(rf"\b{kw}s?\b", scope_lower) and not any(
            kw in (d.get("description", "").lower()) for d in descriptions.values()
        ):
            flags.append({"type": "scope_item_without_tag", "severity": "review", "item": kw,
                          "message": f"Scope mentions '{kw}' but no tagged item matches; manual review needed."})
    return flags


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def _clarification(questions: list[dict]) -> dict:
    return {"status": "needs_clarification", "questions": questions}


def _pages_in_range(pages, n: int) -> list[int]:
    return sorted({p for p in (pages or []) if 1 <= p <= n})


def build_scoped_bom(
    pdf_path: str,
    scope_text: str | None = None,
    demo_pages: list[int] | None = None,
    new_work_pages: list[int] | None = None,
    highlight_mapping: dict | None = None,
    legend_page: int | None = None,
    key_page: int | None = None,
    review_notes: list[str] | None = None,
    job_id: str | None = None,
    source_file: str | None = None,
    output_dir: str = "bom_exports",
) -> dict:
    """Run the full scope-aware BOM pipeline. Page numbers are 1-based.
    
    Generates BOM in three formats (PDF, JSON, CSV) in the output_dir.
    """
    if not HAS_PDFPLUMBER:
        raise RuntimeError("pdfplumber is required")
    with pdfplumber.open(pdf_path) as pdf:
        n_pages = len(pdf.pages)
        sigs = [extract_page_content_signature(pdf, n) for n in range(1, n_pages + 1)]
        by_page = {s["page"]: s for s in sigs}

        # 1. page classification (overrides win)
        mapping = normalise_highlight_mapping(highlight_mapping)
        auto = classify_signatures(sigs, mapping)
        if demo_pages or new_work_pages:
            demo = _pages_in_range(demo_pages, n_pages)
            new = _pages_in_range(new_work_pages, n_pages)
            if not demo:
                demo = [p for p in auto["demo_pages"] if p not in new]
            if not new:
                new = [p for p in auto["new_work_pages"] if p not in demo]
            method, confidence = "user_override", 1.0
        else:
            demo, new = auto["demo_pages"], auto["new_work_pages"]
            method, confidence = auto["classification_method"], auto["classification_confidence"]
            if auto["ambiguous"]:
                return _clarification([{
                    "type": "demo_work_pages_ambiguous",
                    "message": "Could not determine which pages are demo and which are new work.",
                    "candidate_pairs": auto["candidate_pairs"],
                    "pages": list(range(1, n_pages + 1)),
                    "accept_parameter": "demo_pages / new_work_pages",
                }])
        if not new:
            return _clarification([{
                "type": "demo_work_pages_ambiguous",
                "message": "No new-work pages identified.",
                "candidate_pairs": auto["candidate_pairs"],
                "accept_parameter": "demo_pages / new_work_pages",
            }])

        # 2. legend / instrument key
        flags: list[dict] = []
        legend_pg = legend_page if legend_page and 1 <= legend_page <= n_pages else find_legend_page(pdf)
        abbreviations: dict = {}
        if legend_pg:
            abbreviations = parse_legend(by_page[legend_pg]["text"])
        key_text = by_page[key_page]["text"] if key_page and 1 <= key_page <= n_pages else (
            by_page[legend_pg]["text"] if legend_pg else "")
        instrument_key = parse_instrument_key(key_text)
        legend = {"abbreviations": abbreviations, "instrument_key": instrument_key}
        if not legend_pg or not abbreviations:
            flags.append({"type": "legend_not_parsed", "severity": "warning",
                          "message": "Legend could not be found/parsed; pass legend_page to override."})

        # 3. tags from new-work pages
        tag_infos: list[dict] = []
        seen: set = set()
        for p in new:
            for t in extract_tags_from_text(by_page[p]["text"]):
                if t["tag"] not in seen:
                    seen.add(t["tag"])
                    tag_infos.append(t)
        tags = [t["tag"] for t in tag_infos]

        # 4. colour meanings (page roles are known now)
        colour_scheme = detect_colour_meaning([by_page[p] for p in demo], [by_page[p] for p in new])
        for key, meaning in mapping.items():
            colour_scheme[key] = {"meaning": meaning, "confidence": 1.0}

        # 5. scope cross-check
        descriptions = {t: describe_tag(t, legend) for t in tags}
        flags.extend(cross_check_scope(scope_text, tags, descriptions))

        # 6. BOM
        materials = generate_bom_from_tags(tag_infos)
        for m in materials:
            d = descriptions[m["tag_id"]]
            m["description"], m["description_source"] = d["description"], d["source"]
            m["confidence"] = d["confidence"]
        if not materials:
            flags.append({"type": "no_tags_found", "severity": "warning",
                          "message": "No equipment tags found on new-work pages."})

        job_match = re.search(r"Job\s*#\s*\d+-\d+", " ".join([scope_text or "", by_page[1]["text"] if by_page else ""]), re.I)
        job_number = re.sub(r"\s+", "", job_match.group(0)) if job_match else None

    notes = list(review_notes or []) + [f["message"] for f in flags if f["severity"] in ("warning", "review")]
    
    # Export BOM in all three formats
    bom_pdf = None
    bom_json = None
    bom_csv = None
    
    try:
        bom_pdf = export_bom_to_pdf(
            job_id=job_id or job_number or "job",
            source_file=source_file or Path(pdf_path).name,
            materials=materials,
            scope_of_work=scope_text or "",
            review_notes=notes,
            output_dir=output_dir,
        )
    except Exception as exc:
        flags.append({"type": "bom_pdf_failed", "severity": "warning", "message": f"BOM PDF export failed: {exc}"})

    try:
        bom_json = export_bom_to_json(
            job_id=job_id or job_number or "job",
            source_file=source_file or Path(pdf_path).name,
            materials=materials,
            scope_of_work=scope_text or "",
            review_notes=notes,
            detected_assets=tag_infos,
            output_dir=output_dir,
        )
    except Exception as exc:
        flags.append({"type": "bom_json_failed", "severity": "warning", "message": f"BOM JSON export failed: {exc}"})

    try:
        bom_csv = export_bom_to_csv(
            job_id=job_id or job_number or "job",
            materials=materials,
            output_dir=output_dir,
        )
    except Exception as exc:
        flags.append({"type": "bom_csv_failed", "severity": "warning", "message": f"BOM CSV export failed: {exc}"})

    return {
        "status": "completed",
        "job_number": job_number,
        "demo_pages": demo,
        "new_work_pages": new,
        "classification_method": method,
        "classification_confidence": confidence,
        "legend": {"page": legend_pg, "found": bool(abbreviations), "entries_found": len(abbreviations)},
        "colour_scheme": colour_scheme,
        "detected_assets": tag_infos,
        "materials": materials,
        "flags": flags,
        "bom_pdf": bom_pdf,
        "bom_json": bom_json,
        "bom_csv": bom_csv,
    }
