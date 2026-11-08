"""Reads equipment/instrument labels from a P&ID page with their drawing location and status.

Status comes from how the drawing is marked up:
  * ``future``       - inside a blue cloud (by others / future work)
  * ``highlighted``  - in a new-work colour (green) markup
  * text colour      - black = bold (in scope), grey = existing background
"""
from __future__ import annotations

import math
import re

# Common ISA / P&ID instrument and device codes printed inside symbols (not tagged with a dash).
LABEL_CODES = {
    "LPD", "MAV", "HPV", "LI", "LS", "LAL", "LALL", "LAH", "LAHH", "LIT", "LT", "PT", "PI", "PG", "PIT",
    "PSV", "PRV", "PCV", "FS", "FT", "FE", "FI", "TT", "TE", "TI", "PE", "AE", "ATG", "CG", "UT", "LE", "DE",
    "HS", "XC", "JY", "MOV", "POV", "TRV", "PSH", "PSL", "PAH", "PAL", "TSH", "FSL", "FSH",
}
LABEL_NAMES = {
    "LPD": "Low Point Drain", "MAV": "Manual Air Vent", "HPV": "High Point Vent", "PLC": "PLC Interface",
    "LI": "Level Indicator", "LS": "Level Switch", "LAL": "Level Alarm Low", "LALL": "Level Alarm Low-Low",
    "LAH": "Level Alarm High", "LAHH": "Level Alarm High-High", "LIT": "Level Indicating Transmitter",
    "LT": "Level Transmitter", "PT": "Pressure Transmitter", "PI": "Pressure Indicator", "PG": "Pressure Gauge",
    "PIT": "Pressure Indicating Transmitter", "PSV": "Pressure Safety Valve", "PRV": "Pressure Relief Valve",
    "PCV": "Pressure Control Valve", "FS": "Flow Switch", "FT": "Flow Transmitter", "FE": "Flow Element",
    "FI": "Flow Indicator", "TT": "Temperature Transmitter", "TE": "Temperature Element",
    "TI": "Temperature Indicator", "PE": "Pressure Element", "AE": "Bulk Air Eliminator",
    "ATG": "Automatic Tank Gauge", "CG": "Level Gauge", "UT": "Ultrasonic Transmitter", "LE": "Level Element",
    "DE": "Density Element", "HS": "Hand Switch", "XC": "Auxiliary Control Device", "JY": "Solenoid Actuator",
    "MOV": "Motor Operated Valve", "POV": "Pilot Operated Valve", "TRV": "Thermal Relief Valve",
    "PSH": "Pressure Switch High", "PSL": "Pressure Switch Low", "PAH": "Pressure Alarm High",
    "PAL": "Pressure Alarm Low", "TSH": "Temperature Switch High", "FSL": "Flow Switch Low",
    "FSH": "Flow Switch High",
}
from app.services.vocabulary import VOCAB  # noqa: E402

LABEL_CODES |= set(VOCAB["codes"])
LABEL_NAMES.update(VOCAB["codes"])
NOISE = {"PSIG", "NC", "NO", "ON", "CN", "OFF", "CS", "SS", "CSO", "B", "FOR", "OPERATION", "HG", "TEST",
         "XX", "SC", "OSC", "TANK", "NPT", "UL", "GAL", "OIL", "ROOM", "RM", "XXX"} | VOCAB["ignore_prefixes"]
_NOT_TAGS = {"SCH", "NPS", "DWG", "REV", "PSI", "GPM", "ASME", "ANSI", "API", "NFPA", "AWS", "ASTM", "SHEET",
             "RPM", "TDH", "HP", "KW", "NPSH", "BHP", "CFM", "GPH", "PSIG", "NOTE", "ISO", "TYP", "MAX", "MIN", "DIA", "SIZE", "PAGE", "ITEM", "LINE", "TAG", "NO", "DATE"}
_DASHED = re.compile(r"^([A-Z]{1,6})-(\d{1,4}[A-Z]?)$")
_CODE = re.compile(r"^[A-Z]{2,5}$")
_NUM = re.compile(r"^\d{1,4}[A-Z]?$")


def _num(v):
    return float(v) if v is not None else 0.0


def colour_state(value) -> str:
    """``black`` (bold), ``grey`` (existing background) or ``other``."""
    if not value:
        return "other"
    try:
        vals = [float(v) for v in value]
    except (TypeError, ValueError):
        return "other"
    if len(vals) == 1:
        vals = vals * 3
    if len(vals) == 4:
        vals = [(1 - vals[0]) * (1 - vals[3]), (1 - vals[1]) * (1 - vals[3]), (1 - vals[2]) * (1 - vals[3])]
    if len(vals) != 3 or max(vals) - min(vals) > 0.1:
        return "other"
    if max(vals) < 0.3:
        return "black"
    if 0.4 <= max(vals) <= 0.8:
        return "grey"
    return "other"


def grid_locator(page):
    """Return ``f(x, y) -> 'E-13'`` from the sheet's border labels (letters down the side, numbers across the top)."""
    words = page.extract_words()
    cols = [((w["x0"] + w["x1"]) / 2, w["text"]) for w in words
            if w["text"].isdigit() and 1 <= int(w["text"]) <= 40 and w["top"] < page.height * 0.03]
    rows = [((w["top"] + w["bottom"]) / 2, w["text"]) for w in words
            if re.fullmatch(r"[A-Z]", w["text"]) and w["x0"] > page.width * 0.985]
    if len(cols) < 3 or len(rows) < 3:
        return lambda x, y: ""

    def locate(x, y):
        col = min(cols, key=lambda c: abs(c[0] - x))[1]
        row = min(rows, key=lambda r: abs(r[0] - y))[1]
        return f"{row}-{col}"
    return locate


def _annot_regions(page, want_colour) -> list[dict]:
    regions = []
    area = float(page.width * page.height) or 1.0
    for a in page.annots or []:
        d = a.get("data") or {}
        st = str(d.get("Subtype"))
        if any(k in st for k in ("Line", "FreeText", "Popup", "Link", "Text")) and "Polygon" not in st:
            continue
        c = d.get("C")
        ic = d.get("IC")
        if not want_colour(c, ic):
            continue
        box = {"x0": a["x0"], "x1": a["x1"], "top": a["top"], "bottom": a["bottom"]}
        if (box["x1"] - box["x0"]) * (box["bottom"] - box["top"]) < 0.4 * area:
            regions.append(box)
    return regions


def _inside(x, y, r, pad=3.0) -> bool:
    return r["x0"] - pad <= x <= r["x1"] + pad and r["top"] - pad <= y <= r["bottom"] + pad


def _is_blue(c) -> bool:
    return len(c) == 3 and c[2] > 0.7 and c[0] < 0.3 and c[1] < 0.3


def _is_new(c, new_colours) -> bool:
    from app.services.scope_bom import _normalise_colour
    return _normalise_colour(c) in new_colours


def _seg_dist(px, py, s) -> float:
    x1, y1, x2, y2 = s
    dx, dy = x2 - x1, y2 - y1
    t = 0 if dx == dy == 0 else max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def scan_page_labels(page, *, allowed_prefixes: set, label_codes: set, decode_ok, new_colours: set,
                     segments: list[tuple]) -> dict:
    """Find tags and device labels on a page.

    ``decode_ok(prefix)`` says whether letters decode through the instrument key.
    Returns recognised occurrences and unrecognised tags with their locations.
    """
    from app.services.pid_extraction import DENYLIST_PREFIXES
    locate = grid_locator(page)
    try:
        words = page.extract_words(extra_attrs=["non_stroking_color"])
    except Exception:
        words = page.extract_words()
    left, right = page.width * 0.02, page.width * 0.88  # keep out of the title block
    top, bottom = page.height * 0.03, page.height * 0.96
    from app.services.pid_markup import closed_regions
    # a blue-outlined polygon filled green is highlighted new work, not a future cloud
    future = _annot_regions(page, lambda c, ic: bool(c) and _is_blue(c) and not (ic and _is_new(ic, new_colours)))
    green = _annot_regions(
        page, lambda c, ic: bool(c and _is_new(c, new_colours)) or bool(ic and _is_new(ic, new_colours))
    ) + closed_regions(segments)

    words = [w for w in words if left < w["x0"] < right and top < w["top"] < bottom]
    words.sort(key=lambda w: (round(w["top"] / 6), w["x0"]))
    out, unrecognised, unrecognised_locations, mix = [], [], [], {"black": 0, "grey": 0, "other": 0}

    def unknown(tag, first, last):
        cx = (first["x0"] + last["x1"]) / 2
        cy = (min(first["top"], last["top"]) + max(first["bottom"], last["bottom"])) / 2
        unrecognised.append(tag)
        unrecognised_locations.append({"tag": tag, "x": round(cx, 1), "y": round(cy, 1),
                                       "grid": locate(cx, cy)})

    skip_next = False
    used: set = set()
    for i, w in enumerate(words):
        mix[colour_state(w.get("non_stroking_color"))] += 1
        if skip_next or id(w) in used:
            skip_next = False
            continue
        text = w["text"].strip(".,;:()")
        prefix = number = None
        last_word = w
        m = _DASHED.match(text)
        if m:
            prefix, number = m.group(1), m.group(2)
        elif _CODE.match(text) and text not in NOISE and (text in label_codes or text not in DENYLIST_PREFIXES):
            nxt = words[i + 1] if i + 1 < len(words) else None
            if (nxt and _NUM.match(nxt["text"]) and abs(nxt["top"] - w["top"]) < 6
                    and 0 <= nxt["x0"] - w["x1"] < 25 and (text in allowed_prefixes or text in label_codes)):
                prefix, number = text, nxt["text"]
                last_word = nxt
                skip_next = True
            elif (nxt and len(nxt["text"]) >= 3 and _NUM.match(nxt["text"]) and abs(nxt["top"] - w["top"]) < 6
                  and 0 <= nxt["x0"] - w["x1"] < 25 and text not in allowed_prefixes
                  and text not in label_codes and text not in _NOT_TAGS and not decode_ok(text)):
                unknown(f"{text}-{nxt['text']}", w, nxt)
            elif text in label_codes or text in allowed_prefixes:
                below = [x for x in words if _NUM.match(x["text"]) and 0 < x["top"] - w["bottom"] < 14
                         and abs((x["x0"] + x["x1"]) / 2 - (w["x0"] + w["x1"]) / 2) < 14 and len(x["text"]) >= 3]
                if below:
                    prefix, number = text, below[0]["text"]
                    last_word = below[0]
                    used.add(id(below[0]))
                elif text in label_codes:
                    prefix, number = text, ""
        if not prefix:
            continue
        if m and prefix not in allowed_prefixes and prefix not in label_codes and not decode_ok(prefix):
            if len(prefix) >= 2 and prefix not in NOISE and prefix not in DENYLIST_PREFIXES:
                unknown(f"{prefix}-{number}", w, w)
            continue
        if prefix in DENYLIST_PREFIXES and prefix not in label_codes:
            continue
        cx = (min(w["x0"], last_word["x0"]) + max(w["x1"], last_word["x1"])) / 2
        cy = (min(w["top"], last_word["top"]) + max(w["bottom"], last_word["bottom"])) / 2
        state = colour_state(w.get("non_stroking_color"))
        region = "none"
        if any(_inside(cx, cy, r) for r in green) or any(_seg_dist(cx, cy, s) < 12 for s in segments):
            region = "highlighted"
        elif any(_inside(cx, cy, r, 0) for r in future):
            region = "future"
        out.append({"prefix": prefix, "number": number, "x": round(cx, 1), "y": round(cy, 1),
                    "text_colour": state, "region": region, "grid": locate(cx, cy)})
    return {"occurrences": out, "unrecognised": sorted(set(unrecognised)),
            "unrecognised_locations": unrecognised_locations, "colour_mix": mix, "locate": locate}
