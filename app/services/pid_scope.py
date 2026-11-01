"""Pulls the materials a scope of work says must be installed."""
from __future__ import annotations

import re

# (pattern, name) - more specific patterns first; matched text is consumed
_VOCAB = [
    (r"3-way ball valves?", "3-Way Ball Valve"),
    (r"pneumatic operated (?:\d[\d/\-]*[\"”]\s*)?valves?(?: and operator)?", "Pneumatic Operated Valve w/ Operator"),
    (r"(?:SRC )?ball valves?", "Ball Valve"),
    (r"DBB valves?|double block and bleed valves?", "Double Block & Bleed Valve"),
    (r"thermal relief bypass|TRV[’']?s?", "Thermal Relief Valve / Bypass"),
    (r"check valves?", "Check Valve"),
    (r"fire valves?", "Fire Valve"),
    (r"block valves?", "Block Valve"),
    (r"PRV(?: piping| stack ups?)?", "Pressure Relief Valve (PRV)"),
    (r"diaphragm pump", "Diaphragm Pump"),
    (r"flow switch(?:es)?", "Flow Switch"),
    (r"pressure gauges?", "Pressure Gauge"),
    (r"strainers?", "Strainer"),
    (r"air eliminators?", "Air Eliminator"),
    (r"blind flanges?", "Blind Flange"),
    (r"skillets?", "Skillet (Spectacle Blind)"),
    (r"flanges?", "Flange"),
    (r"camlocks?", "Camlock"),
    (r"nipples?", "Nipple"),
    (r"plugs?", "Plug"),
    (r"reducers?", "Reducer"),
    (r"bleed rings?", "Bleed Ring"),
    (r"insulated union", "Insulated Union"),
    (r"manual air vents?|MAV", "Manual Air Vent"),
    (r"low point drains?|LPD[’']?s?", "Low Point Drain"),
    (r"coupling", "Coupling"),
    (r"angle iron pipe supports?", "Angle Iron Pipe Support"),
    (r"pipe supports?", "Pipe Support"),
    (r"U-bolts?", "U-Bolt"),
    (r"tubing(?: and fittings?| fittings)?", "Tubing & Fittings"),
    (r"spools?", "Pipe Spool"),
]
_INSTALL = re.compile(r"\b(install|fabricate|new|provide|add|replace with|connect)\b", re.I)
_DEMO_ONLY = re.compile(r"^\s*(demolish|remove|use|once|schedule|coordinate|mark|layout|get count)", re.I)
_SIZE = re.compile(r"(\d+(?:-\d+/\d+|\s?\d+/\d+)?|\d/\d|[¼½¾])\s*[\"”″]")
_RATING = re.compile(r"\b(\d{2,4}#)")
_QTY = re.compile(r"\((\d+)\)")


def _clauses(line: str) -> list[str]:
    return [c for c in re.split(r"(?<=[a-z\)\"”])\.\s+|;\s*|\s+and install\s+", line) if c.strip()]


def scope_items(scope_text: str) -> list[dict]:
    """Materials named in installation lines of the scope: [{description, quantity, source}]."""
    items: dict[str, dict] = {}
    in_install = False
    for raw in (scope_text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if re.search(r"\binstallation\b\s*:", line, re.I):
            in_install = True
        elif re.search(r"\bdemo\w*\s*:", line, re.I):
            in_install = False
        for clause in _clauses(line):
            if not _INSTALL.search(clause):
                continue
            if _DEMO_ONLY.match(clause) and not re.search(r"\b(install|replace with|new)\b", clause, re.I):
                continue
            if not in_install and not re.search(r"\binstall\w*\b.*\bnew\b|\bnew\b.*", clause, re.I):
                continue
            # only text after the first install/new verb counts (skip "demolish X and ...")
            start = _INSTALL.search(clause).start()
            text = clause[start:]
            consumed = [False] * len(text)
            for pattern, name in _VOCAB:
                for m in re.finditer(pattern, text, re.I):
                    if any(consumed[m.start():m.end()]):
                        continue
                    for i in range(m.start(), m.end()):
                        consumed[i] = True
                    before = text[max(0, m.start() - 28):m.start()]
                    size = _SIZE.findall(before)
                    rating = _RATING.findall(before)
                    qty = _QTY.findall(before)
                    parts = []
                    if size:
                        parts.append(f'{size[-1].strip()}"')
                    if rating:
                        parts.append(rating[-1])
                    desc = " ".join(parts + [name])
                    item = items.setdefault(desc, {"description": desc, "quantity": 0, "sources": []})
                    item["quantity"] = max(item["quantity"], int(qty[-1]) if qty else 1)
                    if clause.strip() not in item["sources"]:
                        item["sources"].append(clause.strip())
    return list(items.values())
