"""Decide which items belong on the BOM: what the new-work pages add and the scope of work requires."""
from __future__ import annotations

import math
import re
from collections import defaultdict

from app.services.pid_extraction import DENYLIST_PREFIXES, VALID_PREFIXES, infer_equipment_type
from app.services.pid_labels import LABEL_CODES, LABEL_NAMES, scan_page_labels
from app.services.pid_markup import _pipe_labels, _segments, markup_items
from app.services.pid_scope import scope_items

from app.services.vocabulary import VOCAB

# scope item name -> drawing codes that satisfy it (common synonyms; extend via vocabulary.json).
# Anything else is matched by name against the legend, symbol legend and code names.
SCOPE_ALIASES = {
    "Pressure Gauge": {"PG", "PI"},
    "Flow Switch": {"FS"},
    "Manual Air Vent": {"MAV"},
    "Low Point Drain": {"LPD"},
    "Air Eliminator": {"AE"},
    "Strainer": {"S"},
}
SCOPE_ALIASES.update(VOCAB["scope_aliases"])


def _name_words(text: str) -> frozenset:
    return frozenset(re.sub(r"(es|s)$", "", w) for w in re.findall(r"[a-z]{3,}", (text or "").lower()))


def _codes_for_scope_name(name: str, code_names: dict) -> set:
    """Drawing codes that satisfy a scope item: known synonyms, else codes whose name equals the
    scope wording (or is fully contained in a multi-word scope name)."""
    if name in SCOPE_ALIASES:
        return set(SCOPE_ALIASES[name])
    nw = _name_words(name)
    return {c for c, d in code_names.items()
            if (dw := _name_words(d)) and (dw == nw or (len(dw) >= 2 and dw <= nw))}


_DASHED_TAG = re.compile(r"\b([A-Z]{2,6})\s?-\s?(\d{1,4}[A-Z]?)\b")


def _learned_prefixes(by_page: dict, pages: list, scope_text: str, exclude: set) -> set:
    """Letter prefixes this drawing set uses for tags: repeated across several numbers, or written as
    a tag in the scope. Lets unfamiliar equipment classes be recognised without a built-in list."""
    numbers: dict = defaultdict(set)
    for p in pages:
        for pre, num in _DASHED_TAG.findall((by_page.get(p) or {}).get("text", "")):
            numbers[pre].add(num)
    learned = {pre for pre, nums in numbers.items() if len(nums) >= 2}
    learned |= {pre for pre, _ in _DASHED_TAG.findall((scope_text or "").upper())}
    return learned - exclude


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


_EQUIPMENT_NOUNS = ("surge", "filter", "separator", "strainer", "vessel", "heater", "exchanger",
                    "compressor", "drum", "pump")


def _anchors(sources: list, scans: dict, page_words: dict, page: int, locate) -> list[dict]:
    """Equipment the scope sentence refers to ('tank 1', 'filter'), located on the section's page."""
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
    # equipment nouns in the scope sentence ("surge tank", "filter separator") found as words on the drawing
    for noun in sorted(set(re.findall(r"\b(" + "|".join(_EQUIPMENT_NOUNS) + r")\w*", text))):
        for w in page_words.get(page, []):
            if w["text"].lower().startswith(noun):
                out.append({"page": page, "x": round(w["x0"], 1), "y": round(w["top"], 1),
                            "grid": locate(w["x0"], w["top"]), "tag": w["text"].title()})
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


_SUPPLY = r"(?:install|provide|furnish|supply|replace|add|fabricate|erect|relocate|reinstall|new)"
_PREPS = {"at", "on", "to", "from", "between", "into", "of", "in", "around", "near", "for", "by", "with",
          "up", "onto", "off", "over", "under", "through", "w/", "per", "against", "beside"}


def _acted_on(scope_text: str, m: dict) -> bool:
    """Is the item itself installed/provided/replaced (a supply verb directly followed by it),
    rather than only named as a place or reference ("at tank 1", "to both tanks")?
    Scopes with no supply verbs at all (plain lists) are not filtered."""
    if not re.search(rf"\b{_SUPPLY}\b", scope_text, re.I):
        return True
    tag = m["tag_id"] or ""
    parts = re.match(r"([A-Za-z]+)[\s-]*(\d.*)$", tag)
    names = []
    if parts:
        names.append(rf"{re.escape(parts.group(1))}[\s-]*{re.escape(parts.group(2))}")
    code = re.sub(r"[-\d].*$", "", tag)
    if len(code) > 2:
        names.append(re.escape(code))
    words = re.findall(r"[A-Za-z]{3,}", m["description"] or "")
    if words:
        names.append(rf"{re.escape(words[-1])}(?:e?s)?")
    if not names:
        return True
    mention = re.compile(rf"(?<![A-Za-z0-9])(?:{'|'.join(names)})(?![A-Za-z0-9])", re.I)
    for sentence in re.split(r"[.;\n]", scope_text):
        for v in re.finditer(rf"\b{_SUPPLY}\b", sentence, re.I):
            tokens = sentence[v.end():].split()
            for i, tok in enumerate(tokens[:6]):
                if tok.lower().strip(",()") in _PREPS:
                    break
                if re.fullmatch(rf"(?:{'|'.join(names)})[,)]*", tok.strip("(").strip(), re.I):
                    return True
    return False


def _referenced(scope_text: str, m: dict) -> bool:
    """Is the item called for by the scope: named by tag/code/name AND installed, provided or
    replaced (not merely used as a location or reference)?"""
    return _mentioned(scope_text, m) and _acted_on(scope_text, m)


def _mentioned(scope_text: str, m: dict) -> bool:
    """Does the scope mention this item by tag, by its code, or by most words of its name?"""
    low = scope_text.lower()
    code = re.sub(r"[-\d].*$", "", m["tag_id"] or "").lower()
    parts = re.match(r"([A-Za-z]+)[\s-]*(\d.*)$", m["tag_id"] or "")
    tagged = bool(parts and re.search(
        rf"(?<![A-Za-z0-9]){re.escape(parts.group(1))}[\s-]*{re.escape(parts.group(2))}(?![0-9A-Za-z])",
        scope_text, re.I))
    if tagged or (len(code) > 2 and re.search(rf"\b{re.escape(code)}s?\b", low)):
        return True
    words = sorted(set(re.findall(r"[a-z]{3,}", (m["description"] or "").lower())))
    if m.get("description_source") == "default" or not words:
        return False
    hit = sum(1 for w in words if re.search(rf"\b{re.escape(w)}(e?s)?\b", low))
    return hit / len(words) >= 0.75


def select_items(pdf, by_page, demo, new, *, legend, abbreviations, symbol_legend, colour_scheme,
                 scope_text, describe_tag, legend_prefixes, meaning_of, new_work, scope_match,
                 embedded_scope: str = "") -> dict:
    first = legend["instrument_key"]["first_letters"]
    succ = legend["instrument_key"]["succeeding_letters"]
    not_tags = {"SCH", "NPS", "DWG", "REV", "PSI", "GPM", "ASME", "ANSI", "API", "NFPA", "AWS", "ASTM", "SHEET",
                "NOTE", "ISO", "TYP", "MAX", "MIN", "DIA"}
    symbol_codes = {k for k in symbol_legend if 2 <= len(k) <= 5 and k.isalpha()}
    learned = _learned_prefixes(by_page, demo + new, scope_text, not_tags | DENYLIST_PREFIXES)
    allowed = (VALID_PREFIXES | legend_prefixes(abbreviations) | symbol_codes | learned) - DENYLIST_PREFIXES
    code_names = {**LABEL_NAMES, **{k.upper(): v for k, v in (abbreviations or {}).items()}, **symbol_legend}
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

    def _describe(prefix, number, tag):
        d = describe_tag(tag if number else f"{prefix}-0", legend)
        description, source, conf = d["description"], d["source"], d["confidence"]
        if source != "legend":
            if prefix in LABEL_NAMES:
                description, source, conf = LABEL_NAMES[prefix], "standard_code", 0.8
            elif prefix in symbol_legend:
                description, source, conf = symbol_legend[prefix], "legend_symbol", 0.85
            elif source == "instrument_letters" and "Unclassified" in description:
                description, source, conf = f"Instrument {prefix}", "default", 0.3
        return d, description, source, conf

    def _entry(key, locs):
        tag = _display(key[0], key[1], 0)
        return {"tag": tag, "description": _describe(key[0], key[1], tag)[1], "quantity": len(_dedupe(locs)),
                "pages": sorted({l["page"] for l in locs}), "location": location_text(locs),
                "locations": _dedupe(locs), "type": infer_equipment_type(key[0])}

    materials, tag_infos = [], []
    for key, g in groups.items():
        prefix, number = g["prefix"], g["number"]
        tag = _display(prefix, number, g["width"])
        locs = _dedupe(g["occ"])
        d, description, source, conf = _describe(prefix, number, tag)
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
        flags.append({"type": "markup_note", "severity": "review", "page": n["page"], "text": n["text"],
                      "x": n["x"], "y": n["y"], "grid": n.get("grid", ""),
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
    for si in scope_items(scope_text or embedded_scope or ""):
        name = re.sub(r'^[\d\-/"½¼¾# ]+', "", si["description"]).strip()
        codes = _codes_for_scope_name(name, code_names)
        on_drawing = sum(drawing_by_code.get(c, 0) for c in codes) if codes else 0
        if on_drawing:
            if si.get("explicit") and on_drawing != si["quantity"]:
                flags.append({"type": "count_mismatch", "severity": "review", "item": name,
                              "scope_qty": si["quantity"], "drawing_qty": on_drawing, "codes": sorted(codes),
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

    # Drawn as new work but never mentioned in the scope (by tag or item type): not needed
    # for this job unless the user says so.
    unreferenced = []
    if (scope_text or "").strip():
        unreferenced = [m for m in materials
                        if m["origin"] == "drawing" and m["type"] != "piping"
                        and not _referenced(scope_text, m)]
        materials = [m for m in materials if m not in unreferenced]
        tag_infos = [t for t in tag_infos if t["tag"] not in {m["tag_id"] for m in unreferenced}]
    for i, m in enumerate(materials, 1):
        m["item_number"] = i
    if unreferenced:
        flags.append({"type": "new_work_not_in_scope", "severity": "review",
                      "items": [{"tag": m["tag_id"], "description": m["description"], "quantity": m["quantity"],
                                 "pages": [int(x) for x in m["pages"].split(",") if x], "location": m["location"],
                                 "locations": m["locations"], "type": m["type"]} for m in unreferenced],
                      "message": f"{len(unreferenced)} item type(s) are marked as new work on the drawing but "
                                 "are not called for by the scope (not mentioned, or only used as a location or reference), so they were left off the BOM: "
                                 + ", ".join(m["tag_id"] for m in unreferenced[:15]) + "."})

    # unidentified tag-like items + items named in scope but drawn as existing
    unrecognised = sorted({t for p in new for t in scans[p]["unrecognised"]})
    if unrecognised:
        flags.append({"type": "unidentified_tags", "severity": "review", "tags": unrecognised[:20],
                      "message": "Tag-like items not recognised by the legend or instrument key: "
                                 + ", ".join(unrecognised[:10]) + "."})
    for key, tag in existing_named.items():
        flags.append({"type": "named_in_scope_but_existing", "severity": "review", "tag": tag,
                      "items": [_entry(key, existing[key])],
                      "location": location_text(existing[key]),
                      "message": f"{tag} is named in the scope but drawn as existing (grey). Is work required on it?"})

    excluded = [{"tag": _display(k[0], k[1], 0), "pages": sorted({l["page"] for l in v}),
                 "location": location_text(v), "reason": "existing (grey) - not part of the new work" if convention
                 else "on demo and new-work pages, not highlighted, not in scope",
                 "quantity": len(_dedupe(v))} for k, v in existing.items()]
    future_items = [{"tag": _display(k[0], k[1], 0), "location": location_text(v), "quantity": len(v)}
                    for k, v in future.items()]
    if excluded:
        flags.append({"type": "unchanged_items_excluded", "severity": "info",
                      "items": [_entry(k, v) for k, v in existing.items()],
                      "message": f"{len(excluded)} existing item type(s) left out of the BOM: "
                                 + ", ".join(e["tag"] for e in excluded[:15]) + "."})
    if future_items:
        flags.append({"type": "future_items_excluded", "severity": "info",
                      "items": [_entry(k, v) for k, v in future.items()],
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
