"""Reads reviewer markup (coloured annotations) and symbol legends from P&ID pages."""
from __future__ import annotations

import math
import re
from app.services.size_labels import sizes_in

_BOILERPLATE = re.compile(
    r"^(future work|draft\b|.*\bdrawing\b|\d+(\.\d+)?( psig)?$)", re.I)
_ACTION = re.compile(r"\b(replace|reinstall|repair|install|provide|add|relocate|new|remove|demo\w*|"
                     r"re-?use|extend)\b", re.I)
_PIPE_MATERIAL = {"CS", "SS", "CSO", "PVC", "CU", "AL"}
_NOISE = {"PSIG", "NC", "NO", "ON", "CN", "OFF", "CS", "SS", "CSO", "B", "FOR", "OPERATION", "HG", "TEST",
          "XX", "SC", "OSC", "TANK", "LPD", "MAV", "S", "N2", "NPT"}


def _num(v):
    return float(v) if v is not None else 0.0


def _colour(data) -> tuple | None:
    from app.services.scope_bom import _normalise_colour
    return _normalise_colour(data.get("C"))


def _annot_text(annot) -> str:
    raw = (annot.get("data") or {}).get("Contents") or annot.get("contents") or ""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "ignore")
    return re.sub(r"\s+", " ", str(raw).replace("\r", " ")).strip()


def parse_symbol_legend(page) -> dict:
    """Symbol letters -> name from a legend page, e.g. ``{'F/S': 'Filter/Separator, Horizontal'}``.

    Legend symbols often have letters drawn inside them (S, AE, F/S ...) with the
    name written in the next column on the same row.
    """
    words = page.extract_words(keep_blank_chars=False)
    rows: dict[int, list] = {}
    for w in words:
        rows.setdefault(round(w["top"] / 5), []).append(w)
    lines = []
    for key in sorted(rows):
        ws = sorted(rows[key], key=lambda w: w["x0"])
        cur = [ws[0]]
        for w in ws[1:]:
            if w["x0"] - cur[-1]["x1"] > 14:
                lines.append(cur)
                cur = [w]
            else:
                cur.append(w)
        lines.append(cur)
    lines = [ln for ln in lines if ln[0]["x0"] < page.width * 0.5]  # right half holds the instrument key
    segs = [{"x0": s[0]["x0"], "x1": s[-1]["x1"], "top": s[0]["top"],
             "text": " ".join(w["text"] for w in s)} for s in lines]
    legend: dict = {}
    for s in segs:
        if not re.fullmatch(r"[A-Z]{1,3}(/[A-Z])?", s["text"]):
            continue
        right = [t for t in segs if abs(t["top"] - s["top"]) < 12 and 0 < t["x0"] - s["x1"] < 80]
        if not right:
            continue
        name = min(right, key=lambda t: (abs(t["top"] - s["top"]) > 6, t["x0"]))
        text = name["text"]
        for t in sorted(segs, key=lambda t: t["top"]):
            if 0 < t["top"] - name["top"] < 22 and abs(t["x0"] - name["x0"]) < 6 and t["top"] > name["top"]:
                text += " " + t["text"]
                break
        if re.fullmatch(r"[A-Z][A-Z ,/()&\-.]+", text) and s["text"] not in legend:
            legend[s["text"]] = text.title()
    return legend


def _to_display(a, rot: int, height: float, xr: float, yr: float) -> tuple[float, float]:
    """Map a raw PDF point to pdfplumber's display space using the annotation's own Rect as anchor."""
    r0, r1 = (float(v) for v in a["data"]["Rect"][:2])
    if rot == 270:
        return a["x0"] + (yr - r1), a["top"] + (xr - r0)
    if rot == 90:
        return a["x1"] - (yr - r1), a["bottom"] - (xr - r0)
    if rot == 180:
        return a["x1"] - (xr - r0), a["top"] + (yr - r1)
    return a["x0"] + (xr - r0), a["bottom"] - (yr - r1)


def _segments(page, colours: set) -> list[tuple]:
    segs = []
    rot = int(getattr(page, "rotation", 0) or 0) % 360
    for a in page.annots or []:
        d = a.get("data") or {}
        if "Line" not in str(d.get("Subtype")) or "PolyLine" in str(d.get("Subtype")):
            continue
        if _colour(d) not in colours or not d.get("L") or not d.get("Rect"):
            continue
        x1, y1, x2, y2 = (float(v) for v in d["L"])
        p1 = _to_display(a, rot, page.height, x1, y1)
        p2 = _to_display(a, rot, page.height, x2, y2)
        segs.append((p1[0], p1[1], p2[0], p2[1]))
    return segs


def _runs(segs: list[tuple], tol: float = 20.0) -> list[list[tuple]]:
    parent = list(range(len(segs)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    ends = [((s[0], s[1]), (s[2], s[3])) for s in segs]
    for i in range(len(segs)):
        for j in range(i + 1, len(segs)):
            if any(math.dist(p, q) < tol for p in ends[i] for q in ends[j]):
                parent[find(i)] = find(j)
    groups: dict[int, list] = {}
    for i, s in enumerate(segs):
        groups.setdefault(find(i), []).append(s)
    return list(groups.values())


def closed_regions(segs: list[tuple]) -> list[dict]:
    """Bounding boxes of closed loops (revision clouds) drawn from line markup."""
    out = []
    for run in _runs(segs):
        if len(run) < 6:
            continue
        pts = [(s[0], s[1]) for s in run] + [(s[2], s[3]) for s in run]
        free = sum(1 for i, e in enumerate(pts) if not any(j != i and math.dist(e, q) < 20 for j, q in enumerate(pts)))
        if free <= 2:
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            out.append({"x0": min(xs), "x1": max(xs), "top": min(ys), "bottom": max(ys)})
    return out


def _pipe_labels(words) -> list[dict]:
    labels = []
    for i, w in enumerate(words):
        sizes = sizes_in(w["text"])
        if len(sizes) != 1 or sizes[0] != w["text"].replace("\u201d", '"').replace("″", '"'):
            continue
        mat = ""
        for n in words[i + 1:i + 3]:
            if abs(n["top"] - w["top"]) < 4 and n["text"].upper() in _PIPE_MATERIAL:
                mat = n["text"].upper()
                break
        if mat:
            labels.append({"spec": f'{sizes[0]} {mat}', "x": (w["x0"] + w["x1"]) / 2,
                           "y": (w["top"] + w["bottom"]) / 2})
    return labels


def _seg_dist(p, s) -> float:
    (x1, y1, x2, y2), (px, py) = s, p
    dx, dy = x2 - x1, y2 - y1
    t = 0 if dx == dy == 0 else max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    return math.dist(p, (x1 + t * dx, y1 + t * dy))


def _bubble_code(text_words) -> tuple[str, str]:
    letters, number = [], ""
    for w in text_words:
        t = w["text"].strip()
        if re.fullmatch(r"[A-Z]{1,5}(/[A-Z])?", t) and t not in _NOISE:
            letters.append(t)
        elif re.fullmatch(r"\d{3}", t) and not number:
            number = t
    return (letters[0] if letters else ""), number


def markup_items(page, new_colours: set, symbol_legend: dict | None = None) -> dict:
    """New-work markup on a page: piping runs and callout notes, each with a location."""
    from app.services.pid_labels import grid_locator
    locate = grid_locator(page)
    words = page.extract_words()
    pipes, notes = [], []
    for a in page.annots or []:
        d = a.get("data") or {}
        if "FreeText" in str(d.get("Subtype")):
            text = _annot_text(a)
            if text and not _BOILERPLATE.match(text) and _ACTION.search(text):
                notes.append({"text": text, "x": round(a["x0"], 1), "y": round(a["top"], 1),
                              "grid": locate(a["x0"], a["top"])})
    seen = {n["text"].upper() for n in notes}
    try:
        lines = page.extract_text_lines()
    except Exception:
        lines = []
    for ln in lines:
        text = ln["text"].strip()
        if (re.match(r"^(REPLACE|REINSTALL|REPAIR|RELOCATE|ADD|INSTALL|PROVIDE)\b", text)
                and text.upper() not in seen and ln["x0"] < page.width * 0.88):
            notes.append({"text": text, "x": round(ln["x0"], 1), "y": round(ln["top"], 1),
                          "grid": locate(ln["x0"], ln["top"])})
            seen.add(text.upper())

    labels = _pipe_labels(words)
    for run in _runs(_segments(page, new_colours)):
        best, best_d = None, 120.0
        for lab in labels:
            dist = min(_seg_dist((lab["x"], lab["y"]), s) for s in run)
            if dist < best_d:
                best, best_d = lab["spec"], dist
        longest = max(run, key=lambda s: math.dist(s[:2], s[2:]))
        cx, cy = (longest[0] + longest[2]) / 2, (longest[1] + longest[3]) / 2
        pipes.append({"spec": best or "unidentified", "segments": len(run),
                      "length_pts": round(sum(math.dist(s[:2], s[2:]) for s in run), 1),
                      "x": round(cx, 1), "y": round(cy, 1), "grid": locate(cx, cy)})
    return {"pipes": pipes, "notes": notes}
