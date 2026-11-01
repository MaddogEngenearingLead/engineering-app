"""Decide which items belong on the BOM: what the new-work pages add and the scope of work requires."""
from __future__ import annotations

import math
import re
from collections import defaultdict

from app.services.pid_extraction import DENYLIST_PREFIXES, VALID_PREFIXES, infer_equipment_type
from app.services.pid_labels import LABEL_CODES, LABEL_NAMES, scan_page_labels
from app.services.pid_markup import _pipe_labels, _segments, markup_items
from app.services.pid_scope import scope_items

# scope item name -> drawing codes that satisfy it
SCOPE_ALIASES = {
    "Pressure Gauge": {"PG", "PI"},
    "Flow Switch": {"FS"},
    "Manual Air Vent": {"MAV"},
    "Low Point Drain": {"LPD"},
    "Pneumatic Operated Valve w/ Operator": {"POV"},
    "Air Eliminator": {"AE"},
    "Strainer": {"S"},
}


def _key(prefix: str, number: str):
    m = re.match(r"(\d+)(\D*)$", number or "")
    return (prefix, str(int(m.group(1))) + m.group(2) if m else number)


def _display(prefix: str, number: str, width: int) -> str:
    if not number:
        return prefix
    m = re.match(r"(\d+)(\D*)$", number)
    return f"{prefix}-{m.group(1).zfill(width)}{m.group(2)}" if m else f"{prefix}-{number}"


def _loc(o: dict, page_no: int) -> dict:
    return {"page": page_no, "grid": o.get("grid", ""), "x": o["x"], "y": o["y"]}


def location_text(locations: list[dict], limit: int = 6, prefix: str = "") -> str:
    seen, parts = set(), []
    for loc in locations:
        label = f"p{loc['page']} {loc['grid']}".strip() if loc.get("grid") else f"p{loc['page']} ({loc['x']:.0f},{loc['y']:.0f})"
        if prefix and loc.get("tag"):
            label = f"{loc['tag']} at {label}"
        if label not in seen:
            seen.add(label)
            parts.append(label)
    text = prefix + "; ".join(parts[:limit])
    return text + (f" (+{len(parts) - limit} more)" if len(parts) > limit else "")


def _dedupe(occs: list[dict]) -> list[dict]:
    kept = []
    for o in occs:
        if not any(k["page"] == o["page"] and abs(k["x"] - o["x"]) < 6 and abs(k["y"] - o["y"]) < 6 for k in kept):
            kept.append(o)
    return kept


def _page_text(page, sig) -> str:
    text = (sig or {}).get("text") or page.extract_text() or ""
    for a in page.annots or []:
        c = (a.get("data") or {}).get("Contents")
        if c:
            text += " " + (c.decode("utf-8", "ignore") if isinstance(c, bytes) else str(c))
    return re.sub(r"\s+", " ", text.upper())


def _section_page(section: str, page_text: dict, new: list, page_title: dict):
    """New-work page whose title matches the scope section (e.g. 'Equipment PAD')."""
    if re.search(r"\band\b", section, re.I):
        return None  # section covers several areas
    words = re.findall(r"[A-Za-z]+", section.upper())
    for texts in (page_title, page_text):
        for n in (3, 2, 1):
            phrase = " ".join(words[-n:])
            if len(phrase) < 3:
                continue
            counts = {p: texts[p].count(phrase) for p in new}
            best = max(counts.values(), default=0)
            hits = [p for p, c in counts.items() if c == best and c]
            if len(hits) == 1:
                return hits[0]
    return None


def _anchors(sources: list, scans: dict, page_words: dict, page: int, locate) -> list[dict]:
    """Equipment the scope sentence refers to ('tank 1', 'surge tank'), located on the section's page."""
    text = " ".join(sources).lower()
    out = []
    for m in re.finditer(r"\b([a-z]{1,5})-?(\d{1,4})\b", text):
        for o in scans[page]["occurrences"]:
            if o["number"] and o["prefix"].lower() == m.group(1) and o["number"].lstrip("0") == m.group(2).lstrip("0"):
                out.append({**_loc(o, page), "tag": _display(o["prefix"], o["number"], 0)})
    for m in re.finditer(r"tank\s*(\d)", text):
        for o in scans[page]["occurrences"]:
            if o["prefix"] == "TK" and o["number"].lstrip("0") == m.group(1):
                out.append({**_loc(o, page), "tag": f"TK-{m.group(1)}"})
    for pattern, word in ((r"surge|serge", "SURGE"), (r"filter", "FILTER")):
        if re.search(pattern, text):
            for w in page_words.get(page, []):
                if w["text"].upper().startswith(word):
                    out.append({"page": page, "x": round(w["x0"], 1), "y": round(w["top"], 1),
                                "grid": locate(w["x0"], w["top"]), "tag": word.title()})
                    break
    return out


def _note_context(n: dict, occs: list, words: list, symbol_legend: dict, scope_text: str,
                  describe_tag, legend) -> str:
    """What a bare markup note (e.g. REPLACE) refers to: nearest equipment, pipe and scope sentence."""
    def dist(o):
        return math.hypot(o["x"] - n["x"], o["y"] - n["y"])
    near, seen = [], set()
    for o in sorted(occs, key=dist):
        if dist(o) > 400:
            break
        tag = _display(o["prefix"], o["number"], 0)
        if tag in seen:
            continue
        seen.add(tag)
        name = (LABEL_NAMES.get(o["prefix"]) or symbol_legend.get(o["prefix"])
                or describe_tag(tag if o["number"] else f"{o['prefix']}-0", legend)["description"])
        near.append(f"{tag} {name}")
        if len(near) == 3:
            break
    parts = []
    if near:
        parts.append("nearest equipment: " + "; ".join(near))
    labs = _pipe_labels(words)
    if labs:
        lab = min(labs, key=lambda l: math.hypot(l["x"] - n["x"], l["y"] - n["y"]))
        if math.hypot(lab["x"] - n["x"], lab["y"] - n["y"]) < 400:
            parts.append(f"pipe {lab['spec']}")
    verb = re.match(r"\w+", n["text"])
    if verb and near:
        key = near[0].split(" ", 1)[1].split()[-1].lower()
        for line in re.split(r"[\n.]", scope_text):
            if verb.group(0).lower() in line.lower() and key in line.lower():
                parts.append(f'scope: "{line.strip()[:120]}"')
                break
    return "; ".join(parts)


def select_items(pdf, by_page, demo, new, *, legend, abbreviations, symbol_legend, colour_scheme,
                 scope_text, describe_tag, legend_prefixes, meaning_of, new_work, scope_match) -> dict:
    first = legend["instrument_key"]["first_letters"]
    succ = legend["instrument_key"]["succeeding_letters"]
    not_tags = {"SCH", "NPS", "DWG", "REV", "PSI", "GPM", "ASME", "ANSI", "API", "NFPA", "AWS", "ASTM", "SHEET",
                "NOTE", "ISO", "TYP", "MAX", "MIN", "DIA"}
    symbol_codes = {k for k in symbol_legend if 2 <= len(k) <= 5 and k.isalpha()}
    allowed = (VALID_PREFIXES | legend_prefixes(abbreviations) | symbol_codes) - DENYLIST_PREFIXES
    label_codes = LABEL_CODES | symbol_codes
    decode_ok = lambda pre: (len(pre) >= 2 and pre not in not_tags and pre[0] in first
                             and all(c in succ for c in pre[1:]))
    from app.services.scope_bom import _normalise_colour
    new_colours = {_normalise_colour(tuple(float(v) for v in k.strip("[]").split(",")))
                   for k, v in colour_scheme.items() if meaning_of(v) == new_work}
    new_colours.discard(None)

    scans: dict[int, dict] = {}
    for p in demo + new:
        page = pdf.pages[p - 1]
        segs = _segments(page, new_colours) if p in new else []
        scans[p] = scan_page_labels(page, allowed_prefixes=allowed, label_codes=label_codes,
                                    decode_ok=decode_ok, new_colours=new_colours if p in new else set(),
                                    segments=segs)

    mix = {"black": 0, "grey": 0, "other": 0}
    for p in new:
        for k, v in scans[p]["colour_mix"].items():
            mix[k] += v
    total = sum(mix.values()) or 1
    convention = mix["black"] / total > 0.1 and mix["grey"] / total > 0.1  # bold = scope, grey = existing

    demo_keys = {_key(o["prefix"], o["number"]) for p in demo for o in scans[p]["occurrences"]}
    groups: dict = defaultdict(lambda: {"occ": [], "width": 0, "basis": set(), "prefix": "", "number": ""})
    existing: dict = defaultdict(list)
    future: dict = defaultdict(list)
    existing_named: dict = {}
    for p in new:
        for o in scans[p]["occurrences"]:
            key = _key(o["prefix"], o["number"])
            tag = _display(o["prefix"], o["number"], 0)
            if o["region"] == "future":
                future[key].append(_loc(o, p) | {"tag": tag})
                continue
            named = bool(o["number"]) and scope_match(scope_text or "", tag, None) == "tag"
            if convention:
                if o["region"] == "highlighted":
                    basis = "highlighted as new work"
                elif o["text_colour"] == "black":
                    basis = "bold on new-work page (in scope)"
                else:
                    existing[key].append(_loc(o, p) | {"tag": tag})
                    if named:
                        existing_named[key] = tag
                    continue
            else:
                if o["region"] == "highlighted":
                    basis = "highlighted as new work"
                elif named:
                    basis = "named in scope"
                elif key not in demo_keys:
                    basis = "new on new-work page (not on demo page)"
                else:
                    existing[key].append(_loc(o, p) | {"tag": tag})
                    continue
            g = groups[key]
            g["occ"].append(_loc(o, p))
            g["prefix"], g["number"] = o["prefix"], o["number"]
            g["basis"].add(basis)
            m = re.match(r"\d+", o["number"] or "")
            g["width"] = max(g["width"], len(m.group(0)) if m else 0)

    materials, tag_infos = [], []
    for key, g in groups.items():
        prefix, number = g["prefix"], g["number"]
        tag = _display(prefix, number, g["width"])
        locs = _dedupe(g["occ"])
        d = describe_tag(tag if number else f"{prefix}-0", legend)
        description, source, conf = d["description"], d["source"], d["confidence"]
        if source != "legend":
            if prefix in LABEL_NAMES:
                description, source, conf = LABEL_NAMES[prefix], "standard_code", 0.8
            elif prefix in symbol_legend:
                description, source, conf = symbol_legend[prefix], "legend_symbol", 0.85
            elif source == "instrument_letters" and "Unclassified" in description:
                description, source, conf = f"Instrument {prefix}", "default", 0.3
        etype = infer_equipment_type(prefix)
        qty = 1 if number else len(locs)
        materials.append({
            "item_number": 0, "tag_id": tag, "description": description, "type": etype, "quantity": qty,
            "unit": "ea", "confidence": conf, "description_source": source,
            "scope_match": scope_match(scope_text or "", tag, d) or "",
            "highlighted": "highlighted as new work" in g["basis"], "basis": "; ".join(sorted(g["basis"])),
            "pages": ",".join(str(x) for x in sorted({l["page"] for l in locs})),
            "location": location_text(locs), "locations": locs, "origin": "drawing",
        })
        tag_infos.append({"tag": tag, "type": etype, "confidence": conf, "source": source, "prefix": prefix})

    flags: list[dict] = []
    # piping + notes (highlighted runs)
    pipe_groups: dict = defaultdict(list)
    notes: list[dict] = []
    for p in new:
        found = markup_items(pdf.pages[p - 1], new_colours)
        for r in found["pipes"]:
            pipe_groups[r["spec"]].append({"page": p, "grid": r["grid"], "x": r["x"], "y": r["y"]})
        notes += [{**n, "page": p} for n in found["notes"]]
    for spec, locs in pipe_groups.items():
        known = spec != "unidentified"
        materials.append({
            "item_number": 0, "tag_id": "-",
            "description": f"Piping {spec} (highlighted new run)" if known else "Piping, size not determined (highlighted new run)",
            "type": "piping", "quantity": len(locs), "unit": "run", "confidence": 0.4 if known else 0.2,
            "description_source": "markup", "scope_match": "", "highlighted": True,
            "basis": "highlighted pipe run (size from nearest label)",
            "pages": ",".join(str(x) for x in sorted({l["page"] for l in locs})),
            "location": location_text(locs), "locations": locs, "origin": "drawing"})
    if pipe_groups:
        flags.append({"type": "piping_runs", "severity": "review",
                      "message": "Highlighted piping is listed as runs with the nearest size label; "
                                 "lengths and fittings must be taken off the drawing manually."})
    page_words = {p: pdf.pages[p - 1].extract_words() for p in new}
    for n in notes:
        ctx = _note_context(n, scans[n["page"]]["occurrences"], page_words[n["page"]], symbol_legend,
                            scope_text or "", describe_tag, legend)
        flags.append({"type": "markup_note", "severity": "review", "page": n["page"],
                      "location": location_text([{**n, "page": n["page"]}]), "context": ctx,
                      "message": f"Markup note ({location_text([{**n, 'page': n['page']}])}): {n['text']}"
                                 + (f" - {ctx}" if ctx else "")})

    # scope of work: items it asks for that the drawing may not show
    drawing_by_code = defaultdict(int)
    for m in materials:
        if m["origin"] == "drawing" and m["type"] != "piping":
            drawing_by_code[m["tag_id"].split("-")[0]] += m["quantity"]
    from app.services.pid_labels import grid_locator
    locators = {p: grid_locator(pdf.pages[p - 1]) for p in new}
    page_text = {p: _page_text(pdf.pages[p - 1], by_page.get(p)) for p in new}
    page_title = {p: (page_text[p].split("INSTALLATION DRAWING", 1) + [""])[1][:80] for p in new}
    for si in scope_items(scope_text or ""):
        name = re.sub(r'^[\d\-/"½¼¾# ]+', "", si["description"]).strip()
        codes = SCOPE_ALIASES.get(name)
        on_drawing = sum(drawing_by_code.get(c, 0) for c in codes) if codes else 0
        if on_drawing:
            if si.get("explicit") and on_drawing != si["quantity"]:
                flags.append({"type": "count_mismatch", "severity": "review",
                              "message": f"Scope asks for {si['quantity']} x {name}; the drawing shows {on_drawing}. "
                                         "Confirm which is right."})
            continue
        page = _section_page(si.get("section", ""), page_text, new, page_title)
        anchors = []
        for pg in ([page] if page else new):
            anchors = _anchors(si.get("lines") or si["sources"], scans, page_words, pg, locators[pg])
            if anchors:
                page = page or pg
                break
        where = f"{si['drg']} {si['section']}".strip()
        clause = (si["sources"][0] if si["sources"] else "")[:140]
        materials.append({
            "item_number": 0, "tag_id": "-", "description": si["description"], "type": "scope_item",
            "quantity": si["quantity"], "unit": "ea", "confidence": 0.5, "description_source": "scope_of_work",
            "scope_match": "scope", "highlighted": False,
            "basis": f'Scope ({where}): "{clause}". Valve/fitting symbols have no text label, so the '
                     f'quantity comes from the scope - confirm on the drawing' + (f" (page {page})." if page else "."),
            "pages": str(page or ""),
            "location": (location_text(anchors, prefix="near ") if anchors else
                         (f"p{page} (page only, {si['section'] or 'see drawing'})" if page else "")),
            "locations": anchors, "page": page, "origin": "scope"})

    for i, m in enumerate(materials, 1):
        m["item_number"] = i

    # unidentified tag-like items + items named in scope but drawn as existing
    unrecognised = sorted({t for p in new for t in scans[p]["unrecognised"]})
    if unrecognised:
        flags.append({"type": "unidentified_tags", "severity": "review", "tags": unrecognised[:20],
                      "message": "Tag-like items not recognised by the legend or instrument key: "
                                 + ", ".join(unrecognised[:10]) + "."})
    for key, tag in existing_named.items():
        flags.append({"type": "named_in_scope_but_existing", "severity": "review", "tag": tag,
                      "location": location_text(existing[key]),
                      "message": f"{tag} is named in the scope but drawn as existing (grey). Is work required on it?"})

    excluded = [{"tag": _display(k[0], k[1], 0), "pages": sorted({l["page"] for l in v}),
                 "location": location_text(v), "reason": "existing (grey) - not part of the new work" if convention
                 else "on demo and new-work pages, not highlighted, not in scope",
                 "quantity": len(_dedupe(v))} for k, v in existing.items()]
    future_items = [{"tag": _display(k[0], k[1], 0), "location": location_text(v), "quantity": len(v)}
                    for k, v in future.items()]
    if excluded:
        flags.append({"type": "unchanged_items_excluded", "severity": "info", "items": excluded,
                      "message": f"{len(excluded)} existing item type(s) left out of the BOM: "
                                 + ", ".join(e["tag"] for e in excluded[:15]) + "."})
    if future_items:
        flags.append({"type": "future_items_excluded", "severity": "info", "items": future_items,
                      "message": f"{len(future_items)} item type(s) inside blue 'future work' clouds left out: "
                                 + ", ".join(e["tag"] for e in future_items[:15]) + "."})

    demolished = []
    if convention or demo:
        dem: dict = defaultdict(list)
        for p in demo:
            for o in scans[p]["occurrences"]:
                if o["region"] == "future" or (convention and o["text_colour"] != "black"):
                    continue
                dem[_key(o["prefix"], o["number"])].append(_loc(o, p))
        demolished = [{"tag": _display(k[0], k[1], 0), "quantity": len(_dedupe(v)), "location": location_text(v)}
                      for k, v in dem.items()]

    summary = {
        "new_work_pages": list(new), "demo_pages": list(demo),
        "bold_grey_convention": convention,
        "drawing_items": sum(1 for m in materials if m["origin"] == "drawing"),
        "drawing_item_count": sum(m["quantity"] for m in materials if m["origin"] == "drawing"),
        "scope_only_items": sum(1 for m in materials if m["origin"] == "scope"),
        "existing_excluded": len(excluded), "future_excluded": len(future_items), "demolition_items": len(demolished),
    }
    return {"materials": materials, "flags": flags, "tag_infos": tag_infos, "excluded": excluded,
            "demolished": demolished, "summary": summary}
