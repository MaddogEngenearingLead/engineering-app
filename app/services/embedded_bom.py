"""Read a bill of materials that is printed on the drawing package itself.

Engineering packages often carry their own BOM table (ITEM # / DESCRIPTION /
QTY ...). When present it is the designer's own take-off, so it is read
directly instead of being guessed from tags.
"""
from __future__ import annotations

import re

_ITEM = re.compile(r"^\d{1,4}\*?$")


def _clean(v) -> str:
    return re.sub(r"\s+", " ", (v or "").replace("\n", " ")).strip()


def _qty(raw: str):
    """Return (quantity, unit, note) from cells like '9', "+/- 160'" or 'AS REQ.'."""
    s = _clean(raw)
    m = re.search(r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*('|FT)?", s, re.I)
    if not m:
        return 1, "ea", "Quantity not stated (as required / by field)"
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
        elif n.startswith("QTY"):
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


def extract_embedded_bom(pdf) -> list[dict]:
    """Return material rows from BOM tables found in ``pdf`` (pdfplumber), or []."""
    out: list[dict] = []
    seen: set = set()
    for pno, page in enumerate(pdf.pages, 1):
        try:
            text = (page.extract_text() or "").upper()
            if "ITEM #" not in text or "QTY" not in text:
                continue
            tables = page.extract_tables()
        except Exception:
            continue
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

                out.append({
                    "item_number": 0, "tag_id": item.rstrip("*"), "description": desc, "type": _type_of(desc),
                    "quantity": qty, "unit": unit, "confidence": 0.95, "description_source": "drawing BOM",
                    "scope_match": "", "highlighted": False, "basis": "printed on drawing BOM",
                    "pages": str(pno), "location": f"BOM page {pno}", "locations": [{"page": pno}],
                    "origin": "drawing_bom", "manufacturer": get("mfr").strip("- "),
                    "part_number": get("part").strip("- "), "supplied_by": get("supplied"),
                    "installed_by": get("installed"), "notes": note,
                })
    out.sort(key=lambda m: int(re.sub(r"\D", "", m["tag_id"]) or 0))
    for i, m in enumerate(out, 1):
        m["item_number"] = i
    return out
