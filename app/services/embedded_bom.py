"""Read a bill of materials that is printed on the drawing package itself.

Engineering packages often carry their own BOM table (ITEM # / DESCRIPTION /
QTY ...). When present it is the designer's own take-off, so it is read
directly instead of being guessed from tags.
"""
from __future__ import annotations

import re

from app.services.vocabulary import VOCAB

_ITEM = re.compile(r"^\d{1,4}\*?$")

_BULK_ALIASES = {
    "flange": {"FLANGE"},
    "gasket": {"GASKET"},
    "bolting": {"STUD", "BOLT", "NUT"},
    "bolt": {"STUD", "BOLT", "NUT"},
    "fastener": {"STUD", "BOLT", "NUT", "FASTENER"},
    "pipe": {"PIPE"},
    "valve": {"VALVE"},
    "fitting": {"FITTING"},
    "support": {"SUPPORT"},
    "elbow": {"ELBOW"},
    "reducer": {"REDUCER"},
    "tee": {"TEE"},
    "nipple": {"NIPPLE"},
    "strainer": {"STRAINER"},
}


def _clean(v) -> str:
    return re.sub(r"\s+", " ", (v or "").replace("\n", " ")).strip()


def _qty(raw: str):
    """Return (quantity, unit, note) from cells like '9', "+/- 160'" or 'AS REQ.'."""
    s = _clean(raw)
    if re.search(r"\bAS\s+REQ(?:UIRED)?\.?(?=\s|$)|\bBY\s+FIELD\b|\bFIELD\s+(?:VERIFY|MEASURE|DETERMINE)\b"
                 r"|\bTO\s+BE\s+DETERMINED\s+IN\s+FIELD\b", s, re.I):
        return None, "", ""
    m = re.search(r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*('|FT)?", s, re.I)
    if not m:
        return None, "", "Quantity not stated (as required / by field)"
    n = float(m.group(1).replace(",", ""))
    n = int(n) if n == int(n) else n
    if m.group(2):
        return n, "ft", ""
    return n, "ea", ""


def _columns(header: list) -> dict | None:
    names = [_clean(h).upper() for h in header]
    if not names or not names[0].startswith("ITEM"):
        return None
    idx = {"item": 0}
    for i, n in enumerate(names):
        if "DESCRIPTION" in n:
            idx["desc"] = i
        elif n.startswith("MANUF"):
            idx["mfr"] = i
        elif n.startswith("PART"):
            idx["part"] = i
        elif n.startswith(("QTY", "QUANTITY")):
            idx["qty"] = i
        elif n.startswith("SUPPLIED"):
            idx["supplied"] = i
        elif n.startswith("INSTALL"):
            idx["installed"] = i
    return idx if "desc" in idx and "qty" in idx else None


_TYPES = (("OLET", "fitting"), ("O-LET", "fitting"), ("SUPPORT", "support"), ("NU-BOLT", "support"),
          (" PAD", "support"), ("STUD", "fastener"), ("HEX NUT", "fastener"), ("NIPPLE", "fitting"),
          ("FLANGE", "flange"), ("GASKET", "gasket"), ("TRANSMITTER", "instrument"), ("METER", "instrument"),
          ("THERMOWELL", "instrument"), ("VALVE", "valve"))


def _type_of(desc: str) -> str:
    d = " " + desc.upper()
    for key, t in _TYPES:
        if key in d:
            return t
    return "piping" if re.search(r"\bPIPE\b", d) else "fitting"


def _scope_evidence(description: str, scope: str) -> tuple[str, str, str]:
    """Find class terms and a scope excerpt, not a claim that the item is in scope."""
    aliases = dict(_BULK_ALIASES)
    aliases.update({key.lower(): values for key, values in VOCAB["scope_aliases"].items()})
    for phrase, targets in aliases.items():
        scope_hit = re.search(rf"(?<!\w){re.escape(phrase)}(?:s|es)?(?!\w)", scope, re.I)
        if not scope_hit:
            continue
        for target in sorted(targets):
            desc_hit = re.search(rf"(?<!\w){re.escape(target)}(?:s|es)?(?!\w)", description, re.I)
            if desc_hit:
                start = max(scope.rfind("\n", 0, scope_hit.start()) + 1, scope_hit.start() - 100)
                end = scope.find("\n", scope_hit.end())
                end = min(end if end != -1 else len(scope), scope_hit.end() + 100)
                return phrase, desc_hit.group(), _clean(scope[start:end])
    return "", "", ""


def _scope_reference(description: str, scope: str) -> str:
    return _scope_evidence(description, scope)[0]


def _scope_basis(match: str, scope_text: str, target: str = "", excerpt: str = "") -> str:
    if match:
        return (f"Scope mentions '{match}', matching BOM term '{target}'. "
                f"Scope excerpt: \"{excerpt}\". Material-class match only, not confirmation of scope.")
    if scope_text.strip():
        return "No configured scope term matched this description; not proof that the item is out of scope."
    return "No scope was supplied; verify whether this item is required."


def scope_crosscheck_flag(rows: list[dict], scope_text: str) -> dict:
    described = sum(bool(_clean(row.get("description"))) for row in rows)
    label_coverage = (f"{described} of {len(rows)} printed BOM rows have descriptions "
                      f"({described / len(rows):.0%} label completeness).") if rows else \
        "No printed BOM rows were found."
    if scope_text.strip():
        matched = sum(bool(m["scope_match"]) for m in rows)
        message = (f"{label_coverage} Scope terminology matched {matched} of {len(rows)} printed BOM rows. "
                   "Matches are material classes, not proof of scope; all unmatched rows "
                   "remain in the master list and must be reviewed.")
    else:
        message = (f"{label_coverage} No scope was supplied; the printed BOM is a master list "
                   "and every item requires scope review.")
    return {"type": "bom_scope_crosscheck", "severity": "review", "message": message}


def ai_bom_rows(transcription: dict, page: int, scope_text: str) -> list[dict]:
    """Convert validated AI transcription into explicitly provisional BOM rows."""
    rows = []
    for item in transcription["items"]:
        match, target, excerpt = _scope_evidence(item["description"], scope_text)
        reason = _scope_basis(match, scope_text, target, excerpt)
        notes = item["notes"]
        if item["quantity"] is None:
            notes = "; ".join(filter(None, (notes, "Quantity not stated or unreadable")))
        rows.append({
            "item_number": 0, "tag_id": item["item"], "description": item["description"],
            "type": _type_of(item["description"]), "quantity": item["quantity"], "unit": item["unit"],
            "confidence": 0.4, "description_source": "AI transcription of drawing BOM",
            "scope_match": match, "highlighted": False,
            "basis": "AI-transcribed BOM; unverified. " + reason,
            "scope_match_reason": reason,
            "pages": str(page), "page": page, "location": f"BOM page {page}", "locations": [],
            "origin": "drawing_bom_ai", "manufacturer": "", "part_number": "",
            "supplied_by": "", "installed_by": "", "notes": notes,
        })
    return rows


def extract_embedded_bom(pdf, scope_text: str = "", flags: list[dict] | None = None) -> list[dict]:
    """Read native tables and OCR image-only BOM candidates, keeping all master rows."""
    from app.services.drawing_ocr import OCRError, inspect_image_page

    flags = flags if flags is not None else []
    out: list[dict] = []
    seen: set = set()
    for pno, page in enumerate(pdf.pages, 1):
        text = (page.extract_text() or "").upper()
        tables = []
        try:
            if "ITEM" in text and ("QTY" in text or "QUANTITY" in text):
                tables = [(table.extract(), table.rows) for table in page.find_tables()]
        except (ValueError, TypeError) as exc:
            flags.append({"type": "bom_table_error", "severity": "warning",
                          "page": pno,
                          "message": f"Could not read the table on page {pno}: {exc}"})
        native_tables = any(any(_columns(row) for row in table) for table, _ in tables)
        image_coverage = sum(abs(img["x1"] - img["x0"]) * abs(img["bottom"] - img["top"])
                             for img in page.images) / (page.width * page.height)
        if len(text.strip()) < 20 and image_coverage < 0.1:
            flags.append({"type": "no_text_layer", "severity": "warning", "page": pno,
                          "message": f"Page {pno} has no readable text or detected scan image. "
                                     "It may contain vector outlines or other graphical content; "
                                     "check it manually for BOM tables and revision notes."})
        if image_coverage >= 0.1 and (len(text.strip()) < 20 or
                            (not native_tables and ("BILL OF MATERIALS" in text or "BOM-" in text))):
            try:
                table, ocr_flags = inspect_image_page(page, pno)
                flags.extend(ocr_flags)
                if table:
                    tables.append((table, None))
            except OCRError as exc:
                flags.append({"type": "ocr_unavailable", "severity": "warning", "page": pno,
                              "message": f"OCR could not inspect page {pno}: {exc}."})
        for table, geometry in tables:
            cols = None
            for row_index, row in enumerate(table):
                if cols is None:
                    cols = _columns(row)
                    continue
                item = _clean(row[0] if row else "")
                if not _ITEM.match(item) or len(row) <= max(cols.values()):
                    continue
                desc = _clean(row[cols["desc"]])
                if not desc or item in seen:
                    continue
                seen.add(item)
                qty, unit, note = _qty(row[cols["qty"]])

                def get(k):
                    return _clean(row[cols[k]]) if k in cols else ""

                match, target, excerpt = _scope_evidence(desc, scope_text)
                reason = _scope_basis(match, scope_text, target, excerpt)
                locs = []
                if geometry is not None and row_index < len(geometry):
                    cells = geometry[row_index].cells
                    item_box = cells[cols["item"]] if len(cells) > cols["item"] else None
                    if item_box:
                        x0, top, x1, bottom = item_box
                        locs = [{"page": pno, "x": (x0 + x1) / 2, "y": (top + bottom) / 2, "grid": ""}]
                out.append({
                    "item_number": 0, "tag_id": item.rstrip("*"), "description": desc, "type": _type_of(desc),
                    "quantity": qty, "unit": unit, "confidence": 0.95 if native_tables else 0.6,
                    "description_source": "drawing BOM",
                    "scope_match": match, "highlighted": False,
                    "basis": "Printed on drawing BOM. " + reason,
                    "scope_match_reason": reason,
                    "pages": str(pno), "location": f"BOM page {pno}", "locations": locs,
                    "page": pno,
                    "origin": "drawing_bom", "manufacturer": get("mfr").strip("- "),
                    "part_number": get("part").strip("- "), "supplied_by": get("supplied"),
                    "installed_by": get("installed"), "notes": note,
                })
    out.sort(key=lambda m: int(re.sub(r"\D", "", m["tag_id"]) or 0))
    for i, m in enumerate(out, 1):
        m["item_number"] = i
    if out:
        flags.append(scope_crosscheck_flag(out, scope_text))
    return out
