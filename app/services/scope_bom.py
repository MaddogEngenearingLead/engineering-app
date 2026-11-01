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
from app.services.pid_scope import scope_items
from app.services.pid_markup import markup_items, parse_symbol_legend

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


_SPACE_ENTRY = re.compile(r"^([A-Z]{2,5})\s+([A-Z][A-Z0-9 ,/&\-.()']{2,})$")
_LETTER_DASH = re.compile(r"^([A-Z])\s*[-–:=]\s*([A-Za-z][A-Za-z0-9 ,/&\-.()']{2,})$")
_LETTER_SPACE = re.compile(r"^([A-Z])\s+([A-Z][A-Z0-9 ,/&\-.()']{2,})$")
_LEGEND_STOPWORDS = {
    "THE", "AND", "FOR", "SEE", "NOTE", "NOTES", "WITH", "TYPE", "ALL", "ANY", "NOT", "ARE",
    "FROM", "THIS", "THAT", "SHALL", "SHEET", "DWG", "REV", "SCALE", "DATE", "JOB", "NO",
}


def _title_case(desc: str) -> str:
    desc = re.sub(r"\s+", " ", desc).strip(" .-:=")
    return desc.title() if desc.isupper() else desc


def parse_legend(text: str) -> dict:
    """Abbreviation -> description map, e.g. ``{'TK': 'Storage Tank'}``.

    Understands ``TK - Storage Tank`` / ``TK = ...`` style entries and the plain
    ``TK STORAGE TANK`` table style (also several columns per line).
    """
    entries = {}
    for abbr, desc in _LEGEND_ENTRY.findall(text or ""):
        desc = desc.strip(" .")
        if desc and abbr not in entries:
            entries[abbr] = desc
    for raw in (text or "").splitlines():
        for chunk in re.split(r"\s{4,}|\t", raw.strip()):
            m = _SPACE_ENTRY.match(chunk.strip())
            if m and m.group(1) not in _LEGEND_STOPWORDS and m.group(1) not in entries:
                entries[m.group(1)] = _title_case(m.group(2))
    return entries


def parse_instrument_key(text: str) -> dict:
    """First/succeeding letter meanings; ISA defaults overridden by key text.

    Lines are assigned to the FIRST LETTER or SUCCEEDING LETTERS section that precedes them.
    """
    first = dict(ISA_FIRST_LETTERS)
    succeeding = dict(ISA_SUCCEEDING_LETTERS)
    found = 0
    section, in_key = "first", False
    for raw in (text or "").splitlines():
        upper = raw.upper()
        if "SUCCEEDING" in upper:
            section, in_key = "succeeding", True
        elif "FIRST LETTER" in upper or "INITIATING" in upper:
            section, in_key = "first", True
        for chunk in re.split(r"\s{6,}|\t", raw.strip()):
            m = _LETTER_DASH.match(chunk.strip()) or (in_key and _LETTER_SPACE.match(chunk.strip()))
            if not m:
                continue
            (first if section == "first" else succeeding)[m.group(1)] = _title_case(m.group(2))
            found += 1
    return {"first_letters": first, "succeeding_letters": succeeding, "entries_found": found}


def find_key_page(pdf, fallback: int | None) -> int | None:
    """1-based page holding the instrument identification key, else ``fallback``."""
    best_page, best = fallback, 0
    for n, page in enumerate(pdf.pages, start=1):
        lowered = (page.extract_text() or "").lower()
        score = sum(lowered.count(k) for k in ("first letter", "succeeding letter", "instrument identification", "instrument key"))
        if score > best:
            best_page, best = n, score
    return best_page


def legend_prefixes(abbreviations: dict) -> set:
    """Abbreviations that can be used as tag prefixes (2-6 letters)."""
    return {a.upper() for a in abbreviations if 2 <= len(a) <= 6 and a.isalpha()
            and a.upper() not in _LEGEND_STOPWORDS}


_KEY_TAG = re.compile(r"\b([A-Z]{2,5})[ \t]*-[ \t]*(\d{1,4}[A-Z]?)\b")
_NOT_TAGS = {"SCH", "NPS", "DWG", "REV", "PSI", "GPM", "ASME", "ANSI", "API", "NFPA", "AWS", "ASTM",
             "SHEET", "NOTE", "ISO", "TYP", "MAX", "MIN", "DIA"}


def find_key_tags(text: str, legend: dict, known: set) -> list[dict]:
    """Dashed tags (e.g. ``PAH-2``) whose letters decode through the instrument key.

    Catches instruments that are not in the equipment allowlist or legend abbreviations.
    """
    from app.services.pid_extraction import DENYLIST_PREFIXES, pad_number
    key = legend.get("instrument_key") or {}
    first, succeeding = key.get("first_letters", {}), key.get("succeeding_letters", {})
    found = []
    for m in _KEY_TAG.finditer(text or ""):
        prefix, number = m.group(1), pad_number(m.group(1), m.group(2))
        tag = f"{prefix}-{number}"
        if tag in known or prefix in DENYLIST_PREFIXES or prefix in _NOT_TAGS:
            continue
        if prefix[0] in first and all(c in succeeding for c in prefix[1:]):
            known = known | {tag}
            found.append({"tag": tag, "type": "equipment", "confidence": 0.6,
                          "source": "instrument_key", "prefix": prefix})
    return found


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
# Markup: which tags / items are highlighted as new work
# --------------------------------------------------------------------------

_TOKEN_TAG = re.compile(r"([A-Za-z]{1,6})[-–]?(\d{1,4}[A-Za-z]?)")
_SKIP_ANNOTS = ("FreeText", "Link", "Popup", "Text")


def _token_to_tag(token: str) -> str | None:
    from app.services.pid_extraction import pad_number
    m = _TOKEN_TAG.fullmatch(token.strip())
    if not m:
        return None
    prefix = m.group(1).upper()
    return f"{prefix}-{pad_number(prefix, m.group(2).upper())}"


def _centre_in(box: dict, region: dict, pad: float = 2.0) -> bool:
    cx, cy = (box["x0"] + box["x1"]) / 2, (box["top"] + box["bottom"]) / 2
    return region["x0"] - pad <= cx <= region["x1"] + pad and region["top"] - pad <= cy <= region["bottom"] + pad


def _meaning_for(colour, meanings: dict) -> str | None:
    c = _normalise_colour(colour)
    return _meaning_of(meanings.get(colour_key(c))) if c else None


def analyze_page_markup(page, tags: set, meanings: dict) -> dict:
    """Find which of ``tags`` sit inside (or are drawn in) a new-work colour, and
    new-work highlights that contain no tag at all.

    ``meanings`` is the colour scheme ``{colour_key: meaning | {"meaning": ...}}``.
    """
    page_area = float(page.width * page.height) or 1.0
    regions = []
    for annot in getattr(page, "annots", None) or []:
        data = annot.get("data") or {}
        subtype = str(data.get("Subtype", annot.get("subtype", "")))
        if any(s in subtype for s in _SKIP_ANNOTS):
            continue
        if "Line" in subtype:
            continue  # piping runs are read from the line endpoints (pid_markup)
        meaning = _meaning_for(annot.get("color") or data.get("C"), meanings)
        if meaning:
            regions.append({"x0": annot["x0"], "x1": annot["x1"], "top": annot["top"],
                            "bottom": annot["bottom"], "meaning": meaning,
                            "itemised": any(k in subtype for k in ("Circle", "Square"))})
    for rect in getattr(page, "rects", None) or []:
        if not rect.get("fill"):
            continue
        meaning = _meaning_for(rect.get("non_stroking_color"), meanings)
        if meaning:
            regions.append({"x0": rect["x0"], "x1": rect["x1"], "top": rect["top"],
                            "bottom": rect["bottom"], "meaning": meaning})
    regions = [r for r in regions
               if (r["x1"] - r["x0"]) * (r["bottom"] - r["top"]) < 0.5 * page_area]

    try:
        words = page.extract_words(extra_attrs=["non_stroking_color"])
    except Exception:
        words = page.extract_words()

    highlighted: set = set()
    tag_boxes = []
    for i, w in enumerate(words):
        candidates = [(w["text"], [w])]
        if i + 1 < len(words) and abs(words[i + 1]["top"] - w["top"]) < 3:
            candidates.append((w["text"] + words[i + 1]["text"], [w, words[i + 1]]))
        for text, group in candidates:
            tag = _token_to_tag(text)
            if not tag or tag not in tags:
                continue
            box = {"x0": min(g["x0"] for g in group), "x1": max(g["x1"] for g in group),
                   "top": min(g["top"] for g in group), "bottom": max(g["bottom"] for g in group)}
            tag_boxes.append(box)
            meaning_set = {_meaning_for(w.get("non_stroking_color"), meanings)}
            meaning_set |= {r["meaning"] for r in regions if _centre_in(box, r)}
            if NEW_WORK in meaning_set:
                highlighted.add(tag)
            break

    untagged = []
    for r in regions:
        if r["meaning"] != NEW_WORK or r.get("itemised") or any(_centre_in(b, r) for b in tag_boxes):
            continue
        inside = [w for w in words if _centre_in(w, r, pad=4.0)]
        inside.sort(key=lambda w: (round(w["top"] / 4), w["x0"]))
        text = " ".join(w["text"] for w in inside).strip()
        untagged.append({"text": text[:80], "x": round(r["x0"], 1), "y": round(r["top"], 1)})
    return {"highlighted": highlighted, "untagged": untagged}


# --------------------------------------------------------------------------
# Scope matching
# --------------------------------------------------------------------------

def scope_match(scope_text: str, tag: str, description: dict | None) -> str | None:
    """``'tag'`` if the scope names the tag, ``'description'`` if it names the item type."""
    if not scope_text or not scope_text.strip():
        return None
    norm = lambda t: re.sub(r"[\s-]+", "", t.upper())
    if norm(tag) in norm(scope_text):
        return "tag"
    desc = description or {}
    if desc.get("source") in (None, "default"):
        return None
    lowered = scope_text.lower()
    words = [w for w in re.findall(r"[a-z]{4,}", (desc.get("description") or "").lower())]
    if any(re.search(rf"\b{re.escape(w)}s?\b", lowered) for w in words):
        return "description"
    return None


_MARKUP_NOISE = {"XX", "B", "PSIG", "NC", "NO", "ON", "CS", "SS", "CSO", "SC", "OSC", "CN", "FOR", "OPERATION", "PG", "TEST"}


def _no_text_pages(sigs: list[dict]) -> list[int]:
    return [s["page"] for s in sigs if len((s.get("text") or "").strip()) < 20]


_TAGLIKE = re.compile(r"\b([A-Z]{1,5})-(\d{1,4}[A-Z]?)\b")


def unidentified_tags(text: str, known: set) -> list[str]:
    """Dashed tag-like tokens on a page that nothing (allowlist, legend, key) explains."""
    from app.services.pid_extraction import DENYLIST_PREFIXES
    out = []
    for m in _TAGLIKE.finditer(text or ""):
        prefix = m.group(1)
        tag = _token_to_tag(m.group(0)) or m.group(0)
        if (tag in known or prefix in DENYLIST_PREFIXES or prefix in _NOT_TAGS
                or re.fullmatch(r"[A-Z]{1,2}-\d{3,}", tag) or tag in out):
            continue
        out.append(tag)
    return out


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
        for page_no in _no_text_pages(sigs):
            flags.append({"type": "no_text_layer", "severity": "warning", "page": page_no,
                          "message": f"Page {page_no} has no readable text (scanned image?). "
                                     "Tags and legend on it cannot be read; OCR is not supported."})
        legend_pg = legend_page if legend_page and 1 <= legend_page <= n_pages else find_legend_page(pdf)
        abbreviations: dict = {}
        if legend_pg:
            abbreviations = parse_legend(by_page[legend_pg]["text"])
        if key_page and 1 <= key_page <= n_pages:
            key_pg = key_page
        else:
            key_pg = find_key_page(pdf, legend_pg)
        key_text = by_page[key_pg]["text"] if key_pg else ""
        instrument_key = parse_instrument_key(key_text)
        if not instrument_key["entries_found"] and legend_pg:
            instrument_key = parse_instrument_key(by_page[legend_pg]["text"])
        symbol_legend = parse_symbol_legend(pdf.pages[legend_pg - 1]) if legend_pg else {}
        for k, v in list(symbol_legend.items()):
            symbol_legend.setdefault(k.replace("/", ""), v)
        if "PI" in symbol_legend:
            symbol_legend.setdefault("PG", symbol_legend["PI"])
        if len(symbol_legend) >= 5:
            # symbol-style legend: text rows are names, not abbreviations; keep only explicit "XX - name" entries
            abbreviations = {k: v for k, v in abbreviations.items()
                             if re.search(rf"\b{re.escape(k)}\s*[-–:=]\s", by_page[legend_pg]["text"])}
        legend = {"abbreviations": abbreviations, "instrument_key": instrument_key}
        if not legend_pg or not (abbreviations or symbol_legend):
            flags.append({"type": "legend_not_parsed", "severity": "warning",
                          "message": "Legend could not be found/parsed; pass legend_page to override."})

        # 3. colour meanings (page roles are known now); user mapping wins
        colour_scheme = detect_colour_meaning([by_page[p] for p in demo], [by_page[p] for p in new])
        for key, meaning in mapping.items():
            colour_scheme[key] = {"meaning": meaning, "confidence": 1.0}

        # 4. tags: built-in allowlist + legend abbreviations + instrument-key decoding
        extra = legend_prefixes(abbreviations)

        def page_tag_infos(page_no: int) -> list[dict]:
            text = by_page[page_no]["text"]
            infos = extract_tags_from_text(text, extra)
            infos += find_key_tags(text, legend, {t["tag"] for t in infos})
            return infos

        tag_infos: list[dict] = []
        tag_pages: dict[str, list[int]] = {}
        for p in new:
            for t in page_tag_infos(p):
                if t["tag"] not in tag_pages:
                    tag_infos.append(t)
                tag_pages.setdefault(t["tag"], []).append(p)
        demo_tags = {t["tag"] for p in demo for t in page_tag_infos(p)}
        all_tags = [t["tag"] for t in tag_infos]

        highlighted: set = set()
        untagged_items: list[dict] = []
        for p in new:
            on_page = {t["tag"] for t in page_tag_infos(p)}
            markup = analyze_page_markup(pdf.pages[p - 1], on_page, colour_scheme)
            highlighted |= markup["highlighted"]
            untagged_items += [{**u, "page": p} for u in markup["untagged"]]

        # reviewer markup: instrument bubbles, piping runs and callout notes in new-work colours
        new_colours = {tuple(json.loads(k)) for k, v in colour_scheme.items()
                       if _meaning_of(v) == NEW_WORK}
        markup = {"bubbles": [], "pipes": [], "notes": []}
        for p in new:
            found = markup_items(pdf.pages[p - 1], new_colours, symbol_legend)
            for kind in markup:
                markup[kind] += [{**i, "page": p} for i in found[kind]]

        known = set(all_tags) | demo_tags
        for p in new:
            missing = unidentified_tags(by_page[p]["text"], known)
            if missing:
                flags.append({"type": "unidentified_tags", "severity": "review", "page": p, "tags": missing[:20],
                              "message": f"Page {p}: tag-like items not recognised by the legend or "
                                         f"instrument key: {', '.join(missing[:10])}."})

        # 5. compare the new-work pages with the scope and decide what is needed
        descriptions = {t: describe_tag(t, legend) for t in all_tags}
        needed, excluded = [], []
        for info in tag_infos:
            tag = info["tag"]
            match = scope_match(scope_text or "", tag, descriptions[tag])
            is_hl = tag in highlighted
            unchanged = bool(demo) and tag in demo_tags
            if is_hl:
                basis = "highlighted as new work"
            elif match == "tag":
                basis = "named in scope"
            elif match == "description":
                basis = "item type named in scope"
            elif not unchanged:
                basis = "new on new-work page"
            else:
                excluded.append({"tag": tag, "pages": tag_pages[tag],
                                 "reason": "on demo and new-work pages, not highlighted, not in scope"})
                continue
            needed.append((info, match, is_hl, basis))
        tags = [info["tag"] for info, *_ in needed]
        flags.extend(cross_check_scope(scope_text, tags, descriptions))
        if excluded:
            flags.append({"type": "unchanged_items_excluded", "severity": "info", "items": excluded,
                          "message": f"{len(excluded)} existing item(s) left out of the BOM (on both demo and "
                                     f"new-work pages, not highlighted, not in scope): "
                                     f"{', '.join(e['tag'] for e in excluded[:15])}."})

        # 6. BOM
        materials = []
        for info, match, is_hl, basis in needed:
            tag = info["tag"]
            d = descriptions[tag]
            row = generate_bom_from_tags([info])[0]
            row.update({"item_number": len(materials) + 1, "description": d["description"],
                        "description_source": d["source"], "confidence": d["confidence"],
                        "scope_match": match or "", "highlighted": is_hl, "basis": basis,
                        "pages": ",".join(str(p) for p in tag_pages[tag])})
            materials.append(row)

        # highlighted new-work markup that has no tag (e.g. "NEW 4in FLANGE")
        grouped: dict[str, dict] = {}
        for u in untagged_items:
            if u["text"] and all(w.upper() in _MARKUP_NOISE for w in u["text"].split()):
                continue
            if not u["text"]:
                flags.append({"type": "untagged_highlight", "severity": "review", "page": u["page"],
                              "message": f"Highlighted new-work item with no text on page {u['page']} "
                                         f"near ({u['x']}, {u['y']}); identify manually."})
                continue
            g = grouped.setdefault(u["text"].lower(), {"text": u["text"], "pages": set(), "qty": 0})
            g["pages"].add(u["page"])
            g["qty"] += 1
        for g in grouped.values():
            materials.append({
                "item_number": len(materials) + 1, "tag_id": "-", "description": _title_case(g["text"]),
                "type": "highlighted_item", "quantity": g["qty"], "unit": "ea", "confidence": 0.4,
                "description_source": "highlight_text",
                "scope_match": "" if not scope_text else (
                    "description" if scope_match(scope_text, "-", {"description": g["text"], "source": "highlight"})
                    else ""),
                "highlighted": True, "basis": "highlighted as new work (no tag)",
                "pages": ",".join(str(p) for p in sorted(g["pages"])),
            })
            flags.append({"type": "untagged_highlight", "severity": "review",
                          "message": f"Highlighted item without a tag added to the BOM: '{g['text']}' - verify."})
        by_tag = {m["tag_id"]: m for m in materials if m["tag_id"] != "-"}
        bubble_groups: dict[str, dict] = {}
        for b in markup["bubbles"]:
            tag = f"{b['code']}-{b['number']}" if b["number"] else b["code"]
            g = bubble_groups.setdefault(tag, {"code": b["code"], "qty": 0, "pages": set()})
            g["qty"] += 1
            g["pages"].add(b["page"])
        for tag, g in bubble_groups.items():
            if tag in by_tag:
                by_tag[tag]["highlighted"] = True
                continue
            d = describe_tag(f"{tag}", legend)
            name = symbol_legend.get(g["code"]) or (d["description"] if d["source"] != "default" else "Instrument")
            materials.append({
                "item_number": len(materials) + 1, "tag_id": tag, "description": name,
                "type": "instrument", "quantity": g["qty"], "unit": "ea",
                "confidence": 0.8 if g["code"] in symbol_legend else 0.5,
                "description_source": "legend_symbol" if g["code"] in symbol_legend else d["source"],
                "scope_match": "", "highlighted": True, "basis": "highlighted instrument/symbol",
                "pages": ",".join(str(p) for p in sorted(g["pages"]))})
        pipe_groups: dict[str, dict] = {}
        for pp in markup["pipes"]:
            g = pipe_groups.setdefault(pp["spec"], {"runs": 0, "segments": 0, "pages": set()})
            g["runs"] += 1
            g["segments"] += pp["segments"]
            g["pages"].add(pp["page"])
        for spec, g in pipe_groups.items():
            known_spec = spec != "unidentified"
            materials.append({
                "item_number": len(materials) + 1, "tag_id": "-",
                "description": f"Piping {spec} (highlighted new run)" if known_spec else "Piping, size not determined (highlighted new run)",
                "type": "piping", "quantity": g["runs"], "unit": "run", "confidence": 0.4 if known_spec else 0.2,
                "description_source": "markup", "scope_match": "", "highlighted": True,
                "basis": "highlighted pipe run (size from nearest label)",
                "pages": ",".join(str(p) for p in sorted(g["pages"]))})
        if pipe_groups:
            flags.append({"type": "piping_runs", "severity": "review",
                          "message": "Highlighted piping is listed as runs with the nearest size label; "
                                     "lengths and fittings must be taken off the drawing manually."})
        seen_notes = set()
        for n in markup["notes"]:
            key = n["text"].upper()
            if key in seen_notes:
                continue
            seen_notes.add(key)
            flags.append({"type": "markup_note", "severity": "review", "page": n["page"],
                          "message": f"Markup note on page {n['page']}: {n['text']}"})
        for si in scope_items(scope_text or ""):
            materials.append({
                "item_number": len(materials) + 1, "tag_id": "-", "description": si["description"],
                "type": "scope_item", "quantity": si["quantity"], "unit": "ea", "confidence": 0.5,
                "description_source": "scope_of_work", "scope_match": "scope", "highlighted": False,
                "basis": "named in scope of work (quantity from scope text; verify against P&ID)",
                "pages": ""})
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
        "legend": {
            "page": legend_pg,
            "key_page": key_pg,
            "found": bool(abbreviations or symbol_legend),
            "entries_found": len(abbreviations),
            "abbreviations": abbreviations,
            "symbol_legend": symbol_legend,
            "instrument_key_entries": instrument_key["entries_found"],
        },
        "colour_scheme": colour_scheme,
        "detected_assets": tag_infos,
        "excluded_items": excluded,
        "materials": materials,
        "flags": flags,
        "bom_pdf": bom_pdf,
        "bom_json": bom_json,
        "bom_csv": bom_csv,
    }
