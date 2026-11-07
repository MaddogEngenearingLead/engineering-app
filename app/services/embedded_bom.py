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
}


def _clean(v) -> str:
    return re.sub(r"\s+", " ", (v or "").replace("\n", " ")).strip()


def _qty(raw: str):
    """Return (quantity, unit, note) from cells like '9', "+/- 160'" or 'AS REQ.'."""
    s = _clean(raw)
    m = re.search(r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*('|FT)?", s, re.I)
    if not m:
        return None, "", "Quantity not stated (as required / by field)"
    n = float(m.group(1).replace(",", ""))
    n = int(n) if n == int(n) else n
    if m.group(2):
        return n, "ft", "Approximate length" if "+/-" in s else ""
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


def _scope_reference(description: str, scope: str) -> str:
    """Find a material class reference, not a claim that the item is in scope."""
    aliases = dict(_BULK_ALIASES)
    aliases.update({key.lower(): values for key, values in VOCAB["scope_aliases"].items()})
    for phrase, targets in aliases.items():
        if (re.search(rf"(?<!\w){re.escape(phrase)}(?:s|es)?(?!\w)", scope, re.I)
                and any(re.search(rf"(?<!\w){re.escape(target)}(?:s|es)?(?!\w)", description, re.I)
                        for target in targets)):
            return phrase
    return ""


def ai_bom_rows(transcription: dict, page: int, scope_text: str) -> list[dict]:
    """Convert validated AI transcription into explicitly provisional BOM rows."""
    rows = []
    for item in transcription["items"]:
        match = _scope_reference(item["description"], scope_text)
        notes = item["notes"]
        if item["quantity"] is None:
            notes = "; ".join(filter(None, (notes, "Quantity not stated or unreadable")))
        rows.append({
            "item_number": 0, "tag_id": item["item"], "description": item["description"],
            "type": _type_of(item["description"]), "quantity": item["quantity"], "unit": item["unit"],
            "confidence": 0.4, "description_source": "AI transcription of drawing BOM",
            "scope_match": match, "highlighted": False,
            "basis": "AI-transcribed BOM; unverified" + (f"; scope mentions {match} (review)" if match else ""),
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
                tables = page.extract_tables()
        except (ValueError, TypeError) as exc:
            flags.append({"type": "bom_table_error", "severity": "warning",
                          "message": f"Could not read the table on page {pno}: {exc}"})
        native_tables = any(any(_columns(row) for row in table) for table in tables)
        image_coverage = sum(abs(img["x1"] - img["x0"]) * abs(img["bottom"] - img["top"])
                             for img in page.images) / (page.width * page.height)
        if len(text.strip()) < 20 and image_coverage < 0.1:
            flags.append({"type": "no_text_layer", "severity": "warning", "page": pno,
                          "message": f"Page {pno} has no readable text or detected scan image. "
                                     "Check it manually for BOM tables and revision notes."})
        if image_coverage >= 0.1 and (len(text.strip()) < 20 or
                            (not native_tables and ("BILL OF MATERIALS" in text or "BOM-" in text))):
            try:
                table, ocr_flags = inspect_image_page(page, pno)
                flags.extend(ocr_flags)
                if table:
                    tables.append(table)
            except OCRError as exc:
                flags.append({"type": "ocr_unavailable", "severity": "warning", "page": pno,
                              "message": f"OCR could not inspect page {pno}: {exc}."})
        for table in tables:
            cols = None
            for row in table:
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

                match = _scope_reference(desc, scope_text)
                out.append({
                    "item_number": 0, "tag_id": item.rstrip("*"), "description": desc, "type": _type_of(desc),
                    "quantity": qty, "unit": unit, "confidence": 0.95 if native_tables else 0.6,
                    "description_source": "drawing BOM",
                    "scope_match": match, "highlighted": False,
                    "basis": "printed on drawing BOM" + (f"; scope mentions {match} (review)" if match else ""),
                    "pages": str(pno), "location": f"BOM page {pno}", "locations": [],
                    "page": pno,
                    "origin": "drawing_bom", "manufacturer": get("mfr").strip("- "),
                    "part_number": get("part").strip("- "), "supplied_by": get("supplied"),
                    "installed_by": get("installed"), "notes": note,
                })
    out.sort(key=lambda m: int(re.sub(r"\D", "", m["tag_id"]) or 0))
    for i, m in enumerate(out, 1):
        m["item_number"] = i
    if out:
        if scope_text.strip():
            matched = sum(bool(m["scope_match"]) for m in out)
            message = (f"Scope terminology matched {matched} of {len(out)} printed BOM rows. "
                       "Matches are material classes, not proof of scope; all unmatched rows "
                       "remain in the master list and must be reviewed.")
        else:
            message = "No scope was supplied; the printed BOM is a master list and every item requires scope review."
        flags.append({"type": "bom_scope_crosscheck", "severity": "review", "message": message})
    return out
