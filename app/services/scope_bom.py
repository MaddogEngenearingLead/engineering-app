"""
Scope-aware BOM generation.

Works autonomously from a P&ID PDF and a scope-of-work document and only asks
the user for input (``status: "needs_clarification"``) when something cannot be
determined automatically:

1. Legend / instrument identification key are located by keyword scoring.
2. Markup colours and demo/new-work page pairing are inferred from annotation
   colours, FreeText notes and drawing titles.
3. Green (new work) items are cross-checked against the scope text.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    try:
        import fitz  # type: ignore
    except ImportError:
        fitz = None

try:
    import docx
except ImportError:  # pragma: no cover
    docx = None

LEGEND_KEYWORDS = [
    "LEGEND", "ABBREVIATION", "IDENTIFICATION", "SYMBOLS",
    "FIRST LETTER", "SUCCEEDING LETTERS",
]
KEY_KEYWORDS = ["IDENTIFICATION", "FIRST LETTER", "SUCCEEDING LETTERS"]
MIN_KEYWORD_SCORE = 3
MIN_LEGEND_ENTRIES = 10

# Colours that are part of the markup scheme (RGB, 0-1)
SCHEME_COLOURS = {
    "red": (1.0, 0.0, 0.0),
    "green": (0.0, 1.0, 0.0),
    "blue": (0.0, 0.0, 1.0),
}
NAMED_COLOURS = {
    **SCHEME_COLOURS,
    "yellow": (1.0, 1.0, 0.0),
    "pink": (1.0, 0.5, 1.0),
    "lime": (0.0, 1.0, 0.25),
    "orange": (1.0, 0.5, 0.0),
    "cyan": (0.0, 1.0, 1.0),
    "magenta": (1.0, 0.0, 1.0),
    "purple": (0.5, 0.0, 0.5),
    "black": (0.0, 0.0, 0.0),
}
COLOUR_TOLERANCE = 0.12
COLOUR_ROLES = {"demo", "new", "ignore"}
SCHEME_ROLE = {"red": "demo", "green": "new", "blue": "ignore"}
MARKUP_SUBTYPES = {
    "Highlight", "Square", "Circle", "Ink", "Polygon", "PolyLine", "Line",
}

FALSE_TAGS = {"N2", "O2", "H2", "CO2", "N-2"}
DRAWING_NUMBER = re.compile(r"^[A-Z]{1,2}-?\d{3,}$")
TAG_PATTERN = re.compile(r"\b([A-Z]{2,5})[ \t]*-?[ \t]*(\d{1,4})\b")
DENY_PREFIXES = {
    "MD", "CS", "CSO", "CN", "NO", "ON", "OIL", "ROOM", "RM", "FILL", "SS",
    "OSC", "PSIG", "PLC", "JY", "MFXX", "UL", "MP", "DPL", "GAL", "PG", "POT",
    "XXX", "GY", "NC", "NPS", "SCH", "DWG", "REV", "SHEET", "NOTE",
}

DEMO_NOTE = re.compile(r"\bDEMO(?:LITION)?\b", re.I)
NEW_NOTE = re.compile(r"\bNEW\s+(?:INSTALLATION|WORK)\b|\bIS\s+IN\s+SCOPE\b", re.I)
TITLE_PATTERN = re.compile(
    r"\b(DEMO(?:LITION)?|NEW\s+INSTALLATION|NEW\s+WORK)\s+DRAWING\s+([A-Z0-9 /&\-]+)", re.I
)


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #

def load_pid(file_path: str) -> list[dict]:
    """Read a P&ID PDF into plain page dicts (1-based ``page`` numbers)."""
    if fitz is None:
        raise RuntimeError("PyMuPDF is required to read P&ID PDFs.")
    pages = []
    with fitz.open(file_path) as pdf:
        for index, page in enumerate(pdf, start=1):
            words = [
                {"x0": w[0], "y0": w[1], "x1": w[2], "y1": w[3], "text": w[4]}
                for w in page.get_text("words")
            ]
            annots = []
            for annot in page.annots() or []:
                colors = annot.colors or {}
                colour = colors.get("stroke") or colors.get("fill")
                rect = annot.rect
                annots.append({
                    "type": annot.type[1],
                    "color": tuple(colour) if colour else None,
                    "rect": (rect.x0, rect.y0, rect.x1, rect.y1),
                    "content": (annot.info or {}).get("content", "") or "",
                })
            pages.append({
                "page": index,
                "text": page.get_text("text"),
                "words": words,
                "annots": annots,
            })
    return pages


def load_scope_text(file_path: str) -> str:
    """Read a scope-of-work document (.docx, or plain text)."""
    path = Path(file_path)
    if path.suffix.lower() == ".docx":
        if docx is None:
            raise RuntimeError("python-docx is required to read scope documents.")
        document = docx.Document(str(path))
        parts = [p.text for p in document.paragraphs]
        for table in document.tables:
            for row in table.rows:
                parts.extend(cell.text for cell in row.cells)
        return "\n".join(parts)
    return path.read_text(errors="ignore")


# --------------------------------------------------------------------------- #
# 1. Legend and instrument identification key
# --------------------------------------------------------------------------- #

def _title(text: str) -> str:
    small = {"and", "of", "to", "for", "in"}
    words = text.lower().split()
    return " ".join(w if (i and w in small) else w.capitalize() for i, w in enumerate(words))


def _keyword_score(text: str, keywords: list[str]) -> int:
    upper = text.upper()
    return sum(1 for k in keywords if k in upper)


def score_pages(pages: list[dict]) -> list[dict]:
    """Score each page for legend/key content; best candidate first."""
    scored = []
    for page in pages:
        tags = {m.group(0) for m in TAG_PATTERN.finditer(page["text"].upper())}
        scored.append({
            "page": page["page"],
            "score": _keyword_score(page["text"], LEGEND_KEYWORDS),
            "key_score": _keyword_score(page["text"], KEY_KEYWORDS),
            "tag_count": len(tags),
        })
    scored.sort(key=lambda s: (-s["score"], s["tag_count"], s["page"]))
    return scored


ENTRY = re.compile(r"^([A-Z]{1,5})\s+([A-Z][A-Z0-9 ,/&\-\.\(\)']{2,})$")


def parse_legend_entries(text: str) -> tuple[dict, dict, dict]:
    """
    Parse legend text into (abbreviations, first_letters, succeeding_letters).

    Lines such as ``LPD LOW POINT DRAIN`` become abbreviations; single-letter
    lines are assigned to the FIRST LETTER / SUCCEEDING LETTERS section that
    precedes them. Multi-column lines separated by 6+ spaces are split.
    """
    abbreviations: dict[str, str] = {}
    first: dict[str, str] = {}
    succeeding: dict[str, str] = {}
    section = "first"
    for raw in text.splitlines():
        line = raw.strip()
        upper = line.upper()
        if "SUCCEEDING" in upper:
            section = "succeeding"
        elif "FIRST LETTER" in upper or "INITIATING" in upper:
            section = "first"
        for chunk in re.split(r"\s{6,}|\t", line):
            match = ENTRY.match(chunk.strip())
            if not match:
                continue
            code, desc = match.group(1), match.group(2).strip()
            if len(code) == 1:
                target = first if section == "first" else succeeding
                target.setdefault(code, _title(desc))
            else:
                abbreviations.setdefault(code, _title(desc))
    return abbreviations, first, succeeding


def detect_legend(pages: list[dict], legend_page: int | None = None,
                  key_page: int | None = None) -> dict:
    """Locate the legend and key pages and build the decoding structures."""
    scored = score_pages(pages)
    by_page = {p["page"]: p for p in pages}
    asks = []

    if legend_page is not None and legend_page in by_page:
        legend = legend_page
    elif scored and scored[0]["score"] >= MIN_KEYWORD_SCORE:
        legend = scored[0]["page"]
    else:
        legend = None
        asks.append({
            "issue": "legend_page_not_identified",
            "message": f"No page scored at least {MIN_KEYWORD_SCORE} legend keywords. "
                       "Please re-submit with legend_page.",
            "candidates": scored,
        })

    key = None
    if key_page is not None and key_page in by_page:
        key = key_page
    elif legend is not None:
        best_key = max(scored, key=lambda s: (s["key_score"], s["page"] == legend))
        key = best_key["page"] if best_key["key_score"] >= 2 else legend

    abbreviations: dict[str, str] = {}
    first: dict[str, str] = {}
    succeeding: dict[str, str] = {}
    for number in dict.fromkeys(n for n in (legend, key) if n is not None):
        abbr, f, s = parse_legend_entries(by_page[number]["text"])
        abbreviations.update({k: v for k, v in abbr.items() if k not in abbreviations})
        first.update({k: v for k, v in f.items() if k not in first})
        succeeding.update({k: v for k, v in s.items() if k not in succeeding})

    total = len(abbreviations) + len(first) + len(succeeding)
    if legend is not None and total < MIN_LEGEND_ENTRIES:
        asks.append({
            "issue": "instrument_key_not_parsed",
            "message": f"Only {total} legend entries parsed (need {MIN_LEGEND_ENTRIES}). "
                       "Please re-submit with legend_page and/or key_page.",
            "candidates": scored,
        })

    return {
        "legend_page": legend,
        "key_page": key,
        "page_scores": scored,
        "abbreviations": abbreviations,
        "first_letters": first,
        "succeeding_letters": succeeding,
        "ask_user": asks,
    }


def describe_tag(tag: str, legend: dict) -> dict:
    """Describe a tag using the legend: exact match, decoded letters, or fallback."""
    match = re.match(r"^([A-Z]+)-?(\d+)?$", tag.upper())
    prefix, number = (match.group(1), match.group(2)) if match else (tag.upper(), None)
    suffix = f" - {number}" if number else ""
    abbreviations = legend["abbreviations"]
    if prefix in abbreviations:
        return {"description": abbreviations[prefix] + suffix, "confidence": 0.95,
                "match": "exact", "source": f"legend abbreviation {prefix}"}
    decoded = _decode_letters(prefix, legend)
    if decoded:
        return {"description": decoded + suffix, "confidence": 0.7,
                "match": "decoded", "source": "instrument identification key"}
    return {"description": f"Unidentified ({prefix}){suffix}", "confidence": 0.3,
            "match": "fallback", "source": "no legend entry"}


def _decode_letters(prefix: str, legend: dict) -> str | None:
    first, succeeding = legend["first_letters"], legend["succeeding_letters"]
    if len(prefix) < 2 or prefix[0] not in first:
        return None
    parts = [first[prefix[0]]]
    for letter in prefix[1:]:
        if letter not in succeeding:
            return None
        parts.append(succeeding[letter])
    return " ".join(parts)


def find_tags(text: str, legend: dict) -> list[str]:
    """Find equipment tags whose prefix the legend can explain."""
    tags = []
    for match in TAG_PATTERN.finditer(text.upper()):
        prefix, number = match.group(1), match.group(2)
        tag = f"{prefix}-{number}"
        if (tag in FALSE_TAGS or prefix in DENY_PREFIXES
                or DRAWING_NUMBER.match(match.group(0).replace(" ", ""))):
            continue
        if describe_tag(tag, legend)["match"] == "fallback":
            continue
        if tag not in tags:
            tags.append(tag)
    return tags


# --------------------------------------------------------------------------- #
# 2. Colours, page roles and pairing
# --------------------------------------------------------------------------- #

def classify_colour(colour) -> tuple[str, bool]:
    """Return (colour name, in_scheme)."""
    if not colour:
        return "none", False
    rgb = tuple(colour) if len(colour) == 3 else (
        (colour[0],) * 3 if len(colour) == 1 else None)
    if rgb is None:
        return "cmyk", False
    for name, ref in NAMED_COLOURS.items():
        if max(abs(a - b) for a, b in zip(rgb, ref)) <= COLOUR_TOLERANCE:
            return name, name in SCHEME_COLOURS
    return "rgb({:.2f},{:.2f},{:.2f})".format(*rgb), False


def _near_text(page: dict, rect: tuple, margin: float = 12.0, limit: int = 160) -> str:
    x0, y0, x1, y1 = rect
    hits = []
    for w in page["words"]:
        cx, cy = (w["x0"] + w["x1"]) / 2, (w["y0"] + w["y1"]) / 2
        if x0 - margin <= cx <= x1 + margin and y0 - margin <= cy <= y1 + margin:
            hits.append(w)
    hits.sort(key=lambda w: (round(w["y0"] / 6), w["x0"]))
    return " ".join(w["text"] for w in hits)[:limit]


def _markup(page: dict) -> list[dict]:
    """Colour-classified markup annotations on a page."""
    items = []
    for annot in page["annots"]:
        if annot["type"] not in MARKUP_SUBTYPES:
            continue
        name, in_scheme = classify_colour(annot["color"])
        if name == "none":
            continue
        if name == "blue" and annot["type"] != "Polygon":
            in_scheme = False
        items.append({**annot, "colour": name, "in_scheme": in_scheme})
    return items


def _freetext(page: dict) -> list[str]:
    notes = [a["content"].strip() for a in page["annots"]
             if a["type"] == "FreeText" and a["content"].strip()]
    return notes


def _is_role_note(note: str) -> bool:
    return bool(DEMO_NOTE.search(note) or NEW_NOTE.search(note)) and (
        "SCOPE" in note.upper() or "DRAWING" in note.upper())


def _area(page_text: str, notes: list[str]) -> dict:
    """Extract drawing titles: {'demo'|'new': normalised area}."""
    areas: dict[str, set] = {"demo": set(), "new": set()}
    for blob in [page_text, *notes]:
        for line in blob.splitlines():
            for m in TITLE_PATTERN.finditer(line):
                role = "demo" if m.group(1).upper().startswith("DEMO") else "new"
                areas[role].add(re.sub(r"\s+", " ", m.group(2)).strip().upper())
    return areas


def detect_highlights(pages: list[dict], legend_page: int | None,
                      highlight_mapping: dict | None = None) -> dict:
    """Infer colour meanings, page roles (demo/new) and demo<->new pairing."""
    mapping = highlight_mapping or {}
    colour_roles = {k.lower(): v for k, v in (mapping.get("colours") or {}).items()}
    page_roles = {int(k): v for k, v in (mapping.get("pages") or {}).items()}
    explicit_pairs = [tuple(p) for p in (mapping.get("pairs") or [])]

    inventory = []
    out_of_scheme = []
    asks = []
    roles: dict[int, str] = {}
    page_info: dict[int, dict] = {}
    for page in pages:
        counts: dict[str, int] = defaultdict(int)
        for m in _markup(page):
            counts[m["colour"]] += 1
            if not m["in_scheme"] and m["colour"] not in colour_roles:
                out_of_scheme.append({
                    "page": page["page"], "colour": m["colour"], "type": m["type"],
                    "location": [round(v, 1) for v in m["rect"]],
                    "nearby_text": _near_text(page, m["rect"]) or m["content"],
                })
        notes = _freetext(page)
        role_notes = [n for n in notes if _is_role_note(n)]
        demo_hits = sum(1 for n in role_notes if DEMO_NOTE.search(n) and not NEW_NOTE.search(n))
        new_hits = sum(1 for n in role_notes if NEW_NOTE.search(n) and not DEMO_NOTE.search(n))
        areas = _area(page["text"], notes)
        demo_hits += len(areas["demo"])
        new_hits += len(areas["new"])
        red, green = counts.get("red", 0), counts.get("green", 0)
        marked = red + green
        demo_score = 2.0 * demo_hits + (red / marked if marked else 0)
        new_score = 2.0 * new_hits + (green / marked if marked else 0)
        if page["page"] == legend_page:
            role = "reference"
        elif demo_score == 0 and new_score == 0:
            role = "reference"
        elif abs(demo_score - new_score) >= 1.0:
            role = "demo" if demo_score > new_score else "new"
        else:
            role = "ambiguous"
        if page["page"] in page_roles:
            role = page_roles[page["page"]]
        roles[page["page"]] = role
        page_info[page["page"]] = {"areas": areas, "notes": notes}
        inventory.append({
            "page": page["page"],
            "role": role,
            "colours": [
                {"colour": c, "count": n, "meaning": colour_roles.get(c, SCHEME_ROLE.get(c, "unknown"))}
                for c, n in sorted(counts.items())
            ],
            "notes": notes,
        })

    for page_no, role in roles.items():
        if role == "ambiguous":
            asks.append({"issue": "page_role_ambiguous", "page": page_no,
                         "message": f"Cannot tell whether page {page_no} is demo or new work."})

    pairs = [list(p) for p in explicit_pairs] or _pair_pages(roles, page_info)
    if pairs is None:
        asks.append({
            "issue": "pages_not_paired",
            "message": "Could not pair demo pages with new-work pages by drawing title.",
        })
        pairs = []

    if out_of_scheme:
        asks.append({
            "issue": "out_of_scheme_colours",
            "message": "Markup colours outside the red/green/blue scheme were found. "
                       "Confirm their meaning via highlight_mapping.colours "
                       "(demo / new / ignore).",
            "items": out_of_scheme,
        })

    return {
        "page_roles": roles,
        "pairs": pairs,
        "colour_roles": colour_roles,
        "detected_highlights": inventory,
        "out_of_scheme": out_of_scheme,
        "ask_user": asks,
    }


def _pair_pages(roles: dict, info: dict) -> list | None:
    """Pair demo and new pages by drawing-title area; None if ambiguous."""
    demo = [p for p, r in roles.items() if r == "demo"]
    new = [p for p, r in roles.items() if r == "new"]
    if not demo and not new:
        return []
    pairs, unused = [], set(new)
    for d in demo:
        keys = info[d]["areas"]["demo"]
        matches = [n for n in unused if keys & info[n]["areas"]["new"]]
        if len(matches) == 1:
            pairs.append([d, matches[0]])
            unused.discard(matches[0])
        elif not matches and len(demo) == 1 and len(new) == 1:
            pairs.append([d, new[0]])
            unused.clear()
        else:
            return None
    return pairs


# --------------------------------------------------------------------------- #
# 3. Scope cross-check
# --------------------------------------------------------------------------- #

# Ordered (key, regex); matched spans are consumed so "surge tank" is not "tank".
# Spelled-out words are case-insensitive, abbreviations (LPD, AE...) are not.
VOCAB = [
    ("surge tank", r"(?i:\bsurge\s+tanks?\b)"),
    ("tank #", r"(?i:\btanks?[\s\-]*#?(\d+)\b)"),
    ("tank", r"(?i:\btanks?\b)"),
    ("sight glass", r"(?i:\bsight\s+glass(?:es)?\b)"),
    ("low point drain", r"(?i:\blow[\s\-]+point\s+drains?\b)|\bLPDs?\b"),
    ("high point vent", r"(?i:\bhigh[\s\-]+point\s+vents?\b)|\bHPVs?\b"),
    ("fire valve", r"(?i:\bfire\s+valves?\b)"),
    ("dbb valve", r"\bDBB\b|(?i:\bdouble\s+block\s+(?:and|&)\s+bleed\b)"),
    ("relief valve", r"\b[PT]RVs?\b|(?i:\b(?:pressure|thermal|temperature)\s+relief\s+valves?\b)"),
    ("pressure gauge", r"(?i:\bpressure\s+gauges?\b|\bgauges?\b)"),
    ("flow switch", r"(?i:\bflow\s+switch(?:es)?\b)"),
    ("air eliminator", r"(?i:\bair\s+eliminators?\b)|\bAE\b"),
    ("filter separator", r"(?i:\bfilter[\s/\-]+separators?\b)"),
    ("manway", r"(?i:\bman[\s\-]?ways?\b)"),
    ("coupling", r"(?i:\bcouplings?\b)"),
    ("strainer", r"(?i:\bstrainers?\b)"),
    ("ball valve", r"(?i:\bball\s+valves?\b)"),
    ("check valve", r"(?i:\bcheck\s+valves?\b)"),
    ("gate valve", r"(?i:\bgate\s+valves?\b)"),
    ("butterfly valve", r"(?i:\bbutterfly\s+valves?\b)"),
    ("globe valve", r"(?i:\bglobe\s+valves?\b)"),
    ("pump", r"(?i:\bpumps?\b)"),
    ("flange", r"(?i:\bflanges?\b)"),
    ("tee", r"(?i:\btees?\b)"),
]
_VOCAB_RE = [(key, re.compile(pattern)) for key, pattern in VOCAB]


def _static_terms(text: str) -> set[str]:
    terms: set[str] = set()
    remaining = text
    for key, regex in _VOCAB_RE:
        for m in list(regex.finditer(remaining)):
            terms.add(f"tank {m.group(1)}" if key == "tank #" else key)
            remaining = remaining[:m.start()] + " " * len(m.group(0)) + remaining[m.end():]
    return terms


def extract_terms(text: str, legend: dict, for_item: bool = False) -> set[str]:
    """Equipment terms in text, including legend abbreviations."""
    terms = _static_terms(text)
    for code, desc in legend["abbreviations"].items():
        if re.search(rf"\b{re.escape(code)}\b", text):
            terms |= _static_terms(desc) or {desc.lower()}
    if for_item and any(t.startswith("tank ") for t in terms):
        terms.add("tank")
    return terms


def split_scope(text: str) -> list[str]:
    sentences = []
    for line in re.split(r"[\r\n]+", text):
        for part in re.split(r"(?<=[.;])\s+", line):
            part = part.strip(" \t-•*")
            if len(part) > 3:
                sentences.append(part)
    return sentences


def _clip(text: str, n: int = 120) -> str:
    return text if len(text) <= n else text[:n - 1] + "…"


def build_scope_bom(pages: list[dict], scope_text: str, legend: dict,
                    highlights: dict) -> dict:
    """Build the BOM from green items and cross-check with the scope text."""
    roles = highlights["page_roles"]
    colour_roles = highlights["colour_roles"]
    page_by_no = {p["page"]: p for p in pages}
    demo_tags: dict[int, set] = defaultdict(set)
    pair_of_new = {n: d for d, n in highlights["pairs"]}

    items = []
    for number, role in roles.items():
        if role not in ("demo", "new"):
            continue
        page = page_by_no[number]
        for m in _markup(page):
            meaning = colour_roles.get(m["colour"], SCHEME_ROLE.get(m["colour"]))
            if meaning == "ignore" or meaning is None:
                continue
            if meaning == "demo" and role == "new":
                continue  # demo marker (e.g. red circle) on a new-work drawing
            if meaning == "new" and role == "demo":
                continue
            text = (_near_text(page, m["rect"], margin=20.0) + " " + m["content"]).strip()
            tags = find_tags(text, legend)
            if meaning == "demo":
                demo_tags[number].update(tags)
                continue
            items.append({"page": number, "text": text, "tags": tags,
                          "colour": m["colour"], "rect": [round(v, 1) for v in m["rect"]]})

    flags = []
    for page in pages:
        for note in _freetext(page):
            if not _is_role_note(note):
                flags.append({"page": page["page"], "type": "instruction", "text": note})
    for o in highlights["out_of_scheme"]:
        flags.append({"page": o["page"], "type": "out_of_scheme_colour",
                      "text": f"{o['colour']} markup near: {o['nearby_text']}"})

    scope_sentences = split_scope(scope_text)
    scope_terms = [(s, extract_terms(s, legend)) for s in scope_sentences]
    scope_terms = [(s, t) for s, t in scope_terms if t]

    rows: dict[str, dict] = {}
    for item in items:
        terms = extract_terms(item["text"], legend, for_item=True)
        descs = []
        for tag in item["tags"]:
            d = describe_tag(tag, legend)
            descs.append((tag, d))
            terms |= extract_terms(d["description"], legend, for_item=True)
        item["terms"] = terms
        if descs:
            for tag, d in descs:
                key = tag
                row = rows.setdefault(key, {
                    "tag_id": tag, "description": d["description"],
                    "type": d["match"], "quantity": 0, "unit": "ea",
                    "confidence": d["confidence"], "source": d["source"],
                    "pages": [], "terms": set(), "notes": [],
                })
                row["quantity"] = 1  # a tag is a unique identifier: one per BOM row
                row["pages"] = sorted(set(row["pages"]) | {item["page"]})
                row["terms"] |= terms
                src = pair_of_new.get(item["page"])
                if src and tag in demo_tags.get(src, ()):
                    note = f"replaces demolished {tag} on page {src}"
                    if note not in row["notes"]:
                        row["notes"].append(note)
        else:
            specific = sorted(t for t in terms if t != "tank" or len(terms) == 1)
            key = specific[0] if specific else f"unidentified-{item['page']}-{item['rect']}"
            label = _title(key) if specific else f"Unidentified highlighted item (page {item['page']})"
            row = rows.setdefault(key, {
                "tag_id": "-", "description": label,
                "type": "legend_term" if specific else "fallback",
                "quantity": 0, "unit": "ea",
                "confidence": 0.6 if specific else 0.3,
                "source": "text near green markup" if specific else "no text near markup",
                "pages": [], "terms": set(), "notes": [],
            })
            row["quantity"] += 1
            row["pages"] = sorted(set(row["pages"]) | {item["page"]})
            row["terms"] |= terms

    pid_terms = set().union(*(r["terms"] for r in rows.values())) if rows else set()
    scope_not_on_pid = []
    matched_scope: dict[str, list[str]] = defaultdict(list)
    for sentence, terms in scope_terms:
        missing = sorted(t for t in terms if t not in pid_terms)
        for t in terms - set(missing):
            matched_scope[t].append(sentence)
        for t in missing:
            scope_not_on_pid.append({
                "flag": "scope item not on P&ID", "term": t, "scope_text": sentence,
                "confidence": 0.5,
            })

    pid_not_in_scope = []
    scope_all_terms = set().union(*(t for _, t in scope_terms)) if scope_terms else set()
    materials = []
    for number, row in enumerate(rows.values(), start=1):
        hits = sorted(row["terms"] & scope_all_terms)
        matches = [s for t in hits for s in matched_scope.get(t, [])]
        row_flags = list(row["notes"])
        confidence = row["confidence"]
        if matches:
            quote = _clip(matches[0])
            row_flags.append(f'matches scope text: "{quote}"')
            confidence = min(1.0, confidence + 0.05)
        else:
            row_flags.append("P&ID item not in scope")
            confidence = round(confidence * 0.7, 2)
            pid_not_in_scope.append({
                "flag": "P&ID item not in scope", "tag_id": row["tag_id"],
                "description": row["description"], "pages": row["pages"],
                "confidence": confidence,
            })
        materials.append({
            "item_number": number, "tag_id": row["tag_id"],
            "description": row["description"], "type": row["type"],
            "quantity": row["quantity"], "unit": row["unit"],
            "confidence": confidence, "source": row["source"],
            "pages": row["pages"], "notes": row_flags,
        })

    return {
        "materials": materials,
        "scope_items_not_on_pid": scope_not_on_pid,
        "pid_items_not_in_scope": pid_not_in_scope,
        "flags": flags,
    }


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

def parse_highlight_mapping(raw) -> dict | None:
    if raw in (None, ""):
        return None
    mapping = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(mapping, dict):
        raise ValueError("highlight_mapping must be a JSON object.")
    for colour, role in (mapping.get("colours") or {}).items():
        if role not in COLOUR_ROLES:
            raise ValueError(f"Invalid role '{role}' for colour '{colour}'.")
    for page, role in (mapping.get("pages") or {}).items():
        if role not in COLOUR_ROLES | {"reference"}:
            raise ValueError(f"Invalid role '{role}' for page '{page}'.")
    for pair in mapping.get("pairs") or []:
        if not (isinstance(pair, (list, tuple)) and len(pair) == 2
                and all(isinstance(n, int) for n in pair)):
            raise ValueError("Each entry in 'pairs' must be [demo_page, new_page].")
    return mapping


def run_scope_bom(pages: list[dict], scope_text: str, legend_page: int | None = None,
                  key_page: int | None = None, highlight_mapping: dict | None = None) -> dict:
    """Run the full autonomous pipeline; ask the user only when needed."""
    legend = detect_legend(pages, legend_page, key_page)
    highlights = detect_highlights(pages, legend["legend_page"], highlight_mapping)
    legend_summary = {
        "legend_page": legend["legend_page"], "key_page": legend["key_page"],
        "page_scores": legend["page_scores"],
        "abbreviation_count": len(legend["abbreviations"]),
        "abbreviations": legend["abbreviations"],
        "first_letters": legend["first_letters"],
        "succeeding_letters": legend["succeeding_letters"],
    }
    asks = legend["ask_user"] + highlights["ask_user"]
    if asks:
        return {
            "status": "needs_clarification",
            "ask_user": asks,
            "legend": legend_summary,
            "detected_highlights": highlights["detected_highlights"],
            "page_roles": highlights["page_roles"],
            "pairs": highlights["pairs"],
        }
    result = build_scope_bom(pages, scope_text, legend, highlights)
    return {
        "status": "completed",
        "legend": legend_summary,
        "detected_highlights": highlights["detected_highlights"],
        "page_roles": highlights["page_roles"],
        "pairs": highlights["pairs"],
        **result,
        "total_items": len(result["materials"]),
    }
