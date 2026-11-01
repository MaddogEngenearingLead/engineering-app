"""Optional user vocabulary so the scan is not tied to any one set of drawings.

Create ``vocabulary.json`` next to the program (or point ``VOCABULARY_FILE`` at one) to add
company- or project-specific vocabulary without changing code::

    {
      "codes": {"XYZ": "Custom Device Name"},          # drawing codes and what they are called
      "ignore_prefixes": ["DWG", "MD"],                 # letters that are never equipment tags
      "scope_aliases": {"Pneumatic Valve": ["POV"]}     # scope wording -> drawing codes
    }

The built-in lists are common P&ID/ISA vocabulary; everything on a drawing's own legend,
instrument key and repeated tag prefixes is learned from the drawing at scan time.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _candidates() -> list[Path]:
    env = os.environ.get("VOCABULARY_FILE")
    out = [Path(env)] if env else []
    if getattr(sys, "frozen", False):
        out.append(Path(sys.executable).resolve().parent / "vocabulary.json")
    out.append(Path.cwd() / "vocabulary.json")
    return out


def load_vocabulary() -> dict:
    for path in _candidates():
        try:
            if path.is_file():
                data = json.loads(path.read_text(encoding="utf-8"))
                return {
                    "codes": {str(k).upper(): str(v) for k, v in (data.get("codes") or {}).items()},
                    "ignore_prefixes": {str(p).upper() for p in data.get("ignore_prefixes") or []},
                    "scope_aliases": {str(k): {str(c).upper() for c in v}
                                      for k, v in (data.get("scope_aliases") or {}).items()},
                }
        except (OSError, ValueError, AttributeError):
            continue
    return {"codes": {}, "ignore_prefixes": set(), "scope_aliases": {}}


VOCAB = load_vocabulary()
