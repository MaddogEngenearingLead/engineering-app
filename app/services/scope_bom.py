from __future__ import annotations

import re
from pathlib import Path

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

from app.services.pid_extraction import (
    DENYLIST_PREFIXES,
    VALID_PREFIXES,
    infer_equipment_type,
)

LEGEND_PAGE = 0
SCOPE_PAGES = (3, 4)  # pages 4-5 (0-indexed): new installation / fabrication
SCOPE_EXTENSIONS = {".docx", ".pdf", ".txt"}
JOB_NUMBER_RE = re.compile(r"job\s*#?\s*(\d+\s*-\s*\d+)", re.IGNORECASE)
NOTE_KEYWORDS_RE = re.compile(r"\b(PROVIDE|INSTALL|ADD|FUTURE|NEW|REPLACE)\b", re.IGNORECASE)
CLUSTER_PAD = 15.0
TAG_PAD = 6.0
NEARBY_RADIUS = 60.0

_PREFIX_PATTERN = "|".join(
    re.escape(p) for p in sorted(VALID_PREFIXES, key=len, reverse=True)
)
TAG_RE = re.compile(rf"^({_PREFIX_PATTERN})[ \t]*-?[ \t]*(\d{{1,4}})$", re.IGNORECASE)
TAG_IN_TEXT_RE = re.compile(rf"\b({_PREFIX_PATTERN})[ \t]*-?[ \t]*(\d{{1,4}})\b", re.IGNORECASE)
LEGEND_DASH_RE = re.compile(
    r"^\s*([A-Z]{1,5})(?:[ -]?(\d{1,4}))?\s*[-–:=]+\s*([A-Za-z][A-Za-z0-9 /&.,()'\"-]{2,})\s*$"
)
LEGEND_SPACE_RE = re.compile(r"^\s*([A-Z]{1,5})(?:-(\d{1,4})\s+|\s{2,})([A-Z][A-Za-z0-9 /&.,()'\"-]{2,})\s*$")


# ---------------------------------------------------------------- scope doc

def find_scope_document(scope_dir: str | Path) -> Path | None:
    """Return the most recently modified scope document in scope_dir, if any."""
    directory = Path(scope_dir)
    if not directory.is_dir():
        return None
    candidates = [
        p for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() in SCOPE_EXTENSIONS and not p.name.startswith(("~$", "."))
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def extract_job_number(filename: str) -> str | None:
    """Extract a job number such as 'Job#26-117' from a filename."""
    match = JOB_NUMBER_RE.search(filename)
    if not match:
        return None
    return "Job#" + re.sub(r"\s+", "", match.group(1))


def read_scope_text(path: str | Path) -> str:
    """Best-effort plain-text extraction of a scope document."""
    path = Path(path)
    suffix = path.suffix.lower()
    try:
        if suffix == ".txt":
            return path.read_text(errors="ignore")
        if suffix == ".docx":
            import docx  # python-docx
            return "\n".join(p.text for p in docx.Document(str(path)).paragraphs if p.text.strip())
        if suffix == ".pdf" and HAS_PDFPLUMBER:
            with pdfplumber.open(str(path)) as pdf:
                return "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception as e:
        print(f"Error reading scope document {path}: {e}")
    return ""


# ------------------------------------------------------------------ colours

def _to_rgb(color) -> tuple[float, float, float] | None:
    if color is None:
        return None
    if isinstance(color, (int, float)):
        color = (color,)
    try:
        vals = [float(c) for c in color]
    except (TypeError, ValueError):
        return None
    if len(vals) == 1:
        return (vals[0],) * 3
    if len(vals) == 3:
        return tuple(vals)  # type: ignore[return-value]
    if len(vals) == 4:
        c, m, y, k = vals
        return ((1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k))
    return None


def classify_color(color) -> str | None:
    """Classify a PDF colour as red/green/blue/other, or None for black/white/grey."""
    rgb = _to_rgb(color)
    if rgb is None:
        return None
    r, g, b = rgb
    mx, mn = max(rgb), min(rgb)
    if mx - mn < 0.25:
        return None  # grey scale (black, white, grey)
    if r >= 0.6 and g <= 0.45 and b <= 0.45:
        return "red"
    if g >= 0.5 and r <= 0.55 and b <= 0.55 and g - max(r, b) >= 0.2:
        return "green"
    if b >= 0.6 and r <= 0.45 and g <= 0.45:
        return "blue"
    return "other"


def _describe_color(color) -> str:
    rgb = _to_rgb(color)
    if rgb is None:
        return "unknown"
    r, g, b = rgb
    if r >= 0.6 and g >= 0.6 and b <= 0.4:
        return "yellow"
    if r >= 0.6 and b >= 0.5 and g <= 0.6:
        return "pink/magenta"
    if g >= 0.5 and b >= 0.5 and r <= 0.4:
        return "cyan"
    if r >= 0.6 and 0.3 <= g <= 0.7 and b <= 0.3:
        return "orange"
    return f"RGB({r:.2f},{g:.2f},{b:.2f})"


# ----------------------------------------------------------------- geometry

def _overlaps(a: dict, b: dict, pad: float = 0.0) -> bool:
    return not (
        a["x1"] + pad < b["x0"] or b["x1"] + pad < a["x0"]
        or a["bottom"] + pad < b["top"] or b["bottom"] + pad < a["top"]
    )


def _contains_center(region: dict, box: dict, pad: float = 0.0) -> bool:
    cx = (box["x0"] + box["x1"]) / 2
    cy = (box["top"] + box["bottom"]) / 2
    return (
        region["x0"] - pad <= cx <= region["x1"] + pad
        and region["top"] - pad <= cy <= region["bottom"] + pad
    )


def _cluster(regions: list[dict], pad: float = CLUSTER_PAD) -> list[dict]:
    clusters = [dict(r) for r in regions]
    merged = True
    while merged:
        merged = False
        out: list[dict] = []
        for region in clusters:
            for existing in out:
                if _overlaps(existing, region, pad):
                    existing["x0"] = min(existing["x0"], region["x0"])
                    existing["x1"] = max(existing["x1"], region["x1"])
                    existing["top"] = min(existing["top"], region["top"])
                    existing["bottom"] = max(existing["bottom"], region["bottom"])
                    merged = True
                    break
            else:
                out.append(region)
        clusters = out
    return clusters


def _box(obj: dict) -> dict | None:
    try:
        return {
            "x0": float(obj["x0"]), "x1": float(obj["x1"]),
            "top": float(obj["top"]), "bottom": float(obj["bottom"]),
        }
    except (KeyError, TypeError, ValueError):
        return None


# ------------------------------------------------------------------- legend

def _title(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip(" -–:=.")
    return text.title() if text.isupper() else text


def extract_legend(page_text: str) -> dict[str, str]:
    """
    Build a tag/abbreviation -> description mapping from the legend page text.
    Keys are full tags (e.g. 'TK-1') or bare prefixes (e.g. 'POV').
    """
    legend: dict[str, str] = {}
    for line in page_text.splitlines():
        match = LEGEND_DASH_RE.match(line) or LEGEND_SPACE_RE.match(line)
        if not match:
            continue
        prefix, number, description = match.groups()
        if prefix in DENYLIST_PREFIXES:
            continue
        key = f"{prefix}-{number}" if number else prefix
        legend.setdefault(key, _title(description))
    return legend


def describe_tag(tag: str, legend: dict[str, str], fallback_type: str | None = None) -> str:
    prefix = tag.split("-")[0]
    return (
        legend.get(tag)
        or legend.get(prefix)
        or (fallback_type or infer_equipment_type(prefix)).replace("_", " ").title()
    )


# --------------------------------------------------------------- extraction

def _normalize_tag(prefix: str, number: str) -> str:
    prefix = prefix.upper()
    if prefix == "MOV" and len(number) < 3:
        number = number.zfill(3)
    return f"{prefix}-{number}"


def _find_tag_words(words: list[dict]) -> list[dict]:
    """Find tag occurrences in words (single words or adjacent word pairs)."""
    found = []
    i = 0
    while i < len(words):
        w = words[i]
        match = TAG_RE.match(w["text"])
        span = 1
        if not match and i + 1 < len(words):
            nxt = words[i + 1]
            if abs(nxt["top"] - w["top"]) < 5:
                match = TAG_RE.match(f"{w['text']}{nxt['text']}")
                span = 2
        if match and match.group(1).upper() not in DENYLIST_PREFIXES:
            group = words[i:i + span]
            found.append({
                "tag": _normalize_tag(match.group(1), match.group(2)),
                "x0": min(g["x0"] for g in group), "x1": max(g["x1"] for g in group),
                "top": min(g["top"] for g in group), "bottom": max(g["bottom"] for g in group),
            })
            i += span
        else:
            i += 1
    return found


def _collect_color_regions(page) -> list[dict]:
    """Collect coloured regions: annotations, vector paths and coloured text."""
    regions: list[dict] = []

    def add(box, color, source):
        kind = classify_color(color)
        if kind and box:
            regions.append({**box, "color": kind, "detail": _describe_color(color), "source": source})

    for annot in page.annots or []:
        data = annot.get("data", {}) or {}
        subtype = str(data.get("Subtype", annot.get("subtype", ""))).strip("/' ")
        if subtype in ("FreeText", "Link", "Popup", "Text"):
            continue
        color = data.get("C", annot.get("color"))
        add(_box(annot), color, f"annotation:{subtype}")

    for name in ("rects", "lines", "curves"):
        for obj in getattr(page, name, []) or []:
            box = _box(obj)
            add(box, obj.get("stroking_color"), "path")
            if obj.get("fill"):
                add(box, obj.get("non_stroking_color"), "path")

    for char in page.chars or []:
        add(_box(char), char.get("non_stroking_color"), "text")

    return regions


def _freetext_notes(page) -> list[str]:
    notes = []
    for annot in page.annots or []:
        data = annot.get("data", {}) or {}
        subtype = str(data.get("Subtype", annot.get("subtype", ""))).strip("/' ")
        if subtype != "FreeText":
            continue
        text = annot.get("contents") or data.get("Contents") or ""
        if isinstance(text, bytes):
            text = text.decode("utf-8", errors="ignore")
        text = str(text).strip()
        if text:
            notes.append(text)
    return notes


def _nearby_text(words: list[dict], cluster: dict, limit: int = 8) -> str:
    near = [
        w for w in words
        if _overlaps(w, cluster, NEARBY_RADIUS)
    ]
    cx = (cluster["x0"] + cluster["x1"]) / 2
    cy = (cluster["top"] + cluster["bottom"]) / 2
    near.sort(key=lambda w: (((w["x0"] + w["x1"]) / 2 - cx) ** 2 + ((w["top"] + w["bottom"]) / 2 - cy) ** 2))
    return " ".join(w["text"] for w in near[:limit])


def analyze_scope_pages(file_path: str, scope_pages: tuple[int, ...] = SCOPE_PAGES) -> dict:
    """
    Analyze the P&ID: build legend from page 1 and collect green-highlighted
    tags (new work) from the scope pages, plus review flags.
    """
    result = {
        "legend": {}, "green_tags": [], "untagged_green": [],
        "freetext_untagged": [], "mixed_colors": [], "scope_pages_found": False,
    }
    if not HAS_PDFPLUMBER:
        return result

    try:
        with pdfplumber.open(file_path) as pdf:
            if len(pdf.pages) > LEGEND_PAGE:
                result["legend"] = extract_legend(pdf.pages[LEGEND_PAGE].extract_text() or "")

            seen_tags: dict[str, dict] = {}
            for page_index in scope_pages:
                if page_index >= len(pdf.pages):
                    continue
                result["scope_pages_found"] = True
                page = pdf.pages[page_index]
                page_no = page_index + 1
                words = page.extract_words()
                tag_words = _find_tag_words(words)
                regions = _collect_color_regions(page)
                greens = [r for r in regions if r["color"] == "green"]
                reds = [r for r in regions if r["color"] == "red"]
                blues = [r for r in regions if r["color"] == "blue"]
                others = [r for r in regions if r["color"] == "other"]

                for tw in tag_words:
                    in_green = any(_contains_center(r, tw, TAG_PAD) for r in greens)
                    in_other = any(_contains_center(r, tw, TAG_PAD) for r in reds + blues + others)
                    if not in_green:
                        continue
                    if in_other:
                        result["mixed_colors"].append({
                            "page": page_no, "color": "green + non-green overlap",
                            "x": round(tw["x0"], 1), "y": round(tw["top"], 1),
                            "nearby_text": tw["tag"],
                        })
                        continue
                    seen_tags.setdefault(tw["tag"], {"tag": tw["tag"], "page": page_no})

                for cluster in _cluster(greens):
                    if any(_contains_center(cluster, tw, TAG_PAD) for tw in tag_words):
                        continue
                    result["untagged_green"].append({
                        "page": page_no,
                        "x": round(cluster["x0"], 1), "y": round(cluster["top"], 1),
                        "nearby_text": _nearby_text(words, cluster),
                    })

                for cluster in _cluster(others):
                    result["mixed_colors"].append({
                        "page": page_no, "color": cluster_color(others, cluster),
                        "x": round(cluster["x0"], 1), "y": round(cluster["top"], 1),
                        "nearby_text": _nearby_text(words, cluster),
                    })
                for g in _cluster(greens):
                    for r in _cluster(reds):
                        if _overlaps(g, r):
                            result["mixed_colors"].append({
                                "page": page_no, "color": "red/green overlap",
                                "x": round(max(g["x0"], r["x0"]), 1),
                                "y": round(max(g["top"], r["top"]), 1),
                                "nearby_text": _nearby_text(words, g),
                            })

                for note in _freetext_notes(page):
                    if NOTE_KEYWORDS_RE.search(note) and not TAG_IN_TEXT_RE.search(note):
                        result["freetext_untagged"].append({"page": page_no, "note": note})

            result["green_tags"] = list(seen_tags.values())
    except Exception as e:
        print(f"Error analysing scope pages: {e}")
    return result


def cluster_color(regions: list[dict], cluster: dict) -> str:
    for r in regions:
        if _overlaps(r, cluster):
            return r["detail"]
    return "other"


def build_scoped_bom(file_path: str) -> dict:
    """Analyse the P&ID and return scope-filtered materials plus review flags."""
    analysis = analyze_scope_pages(file_path)
    legend = analysis["legend"]
    materials = []
    for i, entry in enumerate(sorted(analysis["green_tags"], key=lambda t: t["tag"]), 1):
        prefix = entry["tag"].split("-")[0]
        eq_type = infer_equipment_type(prefix)
        materials.append({
            "item_number": i,
            "tag_id": entry["tag"],
            "description": describe_tag(entry["tag"], legend, eq_type),
            "type": eq_type,
            "quantity": 1,
            "unit": "ea",
            "confidence": 0.85,
        })
    return {
        "materials": materials,
        "flags": {
            "untagged_green": analysis["untagged_green"],
            "freetext_untagged": analysis["freetext_untagged"],
            "mixed_colors": analysis["mixed_colors"],
        },
        "legend": legend,
        "scope_pages_found": analysis["scope_pages_found"],
    }
