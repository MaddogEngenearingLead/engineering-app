"""Local OCR of image-based BOM sheets and revision areas."""
from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pdfplumber


class OCRError(RuntimeError):
    pass


def _tesseract() -> tuple[str | None, dict]:
    env = os.environ.copy()
    if getattr(sys, "frozen", False):
        if sys.platform.startswith("linux"):
            original = env.get("LD_LIBRARY_PATH_ORIG")
            if original is None:
                env.pop("LD_LIBRARY_PATH", None)
            else:
                env["LD_LIBRARY_PATH"] = original
        root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "tesseract"
        name = "tesseract.exe" if sys.platform.startswith("win") else "tesseract"
        for binary in (root / "bin" / name, root / name):
            if binary.is_file():
                env["TESSDATA_PREFIX"] = str(root / "tessdata")
                if sys.platform.startswith("linux"):
                    env["LD_LIBRARY_PATH"] = os.pathsep.join(
                        filter(None, (str(root / "lib"), str(root), env.get("LD_LIBRARY_PATH"))))
                return str(binary), env
    return shutil.which("tesseract"), env


def _searchable_page(image, dpi: int):
    """Create an in-memory searchable PDF before extracting OCR words."""
    data = io.BytesIO()
    image.save(data, format="PNG")
    binary, env = _tesseract()
    if not binary:
        raise OCRError("Tesseract is not installed or is not on PATH")
    try:
        result = subprocess.run(
            [binary, "stdin", "stdout", "--dpi", str(dpi), "--psm", "6", "-c", "tessedit_create_pdf=1"],
            input=data.getvalue(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=True, timeout=180, env=env,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise OCRError(f"Tesseract failed: {exc}") from exc
    if not result.stdout.startswith(b"%PDF-"):
        raise OCRError("Tesseract did not produce a searchable PDF; check its language and PDF data files.")
    with pdfplumber.open(io.BytesIO(result.stdout)) as pdf:
        page = pdf.pages[0]
        return page.extract_text() or "", page.extract_words(), page.width, page.height


def _render(page, max_width: int):
    dpi = max(72, min(300, round(72 * max_width / page.width)))
    return page.to_image(resolution=dpi).original.convert("RGB"), dpi


def _lines(words: list[dict]) -> list[list[dict]]:
    lines: list[list[dict]] = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and abs(word["top"] - lines[-1][0]["top"]) < 4:
            lines[-1].append(word)
        else:
            lines.append([word])
    return [sorted(line, key=lambda w: w["x0"]) for line in lines]


def _table_rows(words: list[dict]) -> list[list[str]]:
    """Reconstruct columns from OCR word positions; uncertainty is flagged by the caller."""
    lines = _lines(words)
    layouts = []
    for line in lines:
        item_indices = [i for i, w in enumerate(line) if re.fullmatch(r"ITEM[#.:]*", w["text"], re.I)]
        for idx, start in enumerate(item_indices):
            stop = item_indices[idx + 1] if idx + 1 < len(item_indices) else len(line)
            part = line[start:stop]
            columns = {}
            for w in part:
                token = w["text"].upper().strip(".:#|")
                if token == "ITEM":
                    columns["item"] = w["x0"]
                elif token == "DESCRIPTION":
                    columns["desc"] = w["x0"]
                elif token in ("QTY", "QUANTITY"):
                    columns["qty"] = w["x0"]
                elif token.startswith("MANUF"):
                    columns["mfr"] = w["x0"]
                elif token == "PART":
                    columns["part"] = w["x0"]
                elif token.startswith("SUPPLIED"):
                    columns["supplied"] = w["x0"]
                elif token.startswith("INSTALL"):
                    columns["installed"] = w["x0"]
            if {"item", "desc", "qty"} <= columns.keys():
                # PRODUCT normally precedes DESCRIPTION in the header.
                product = next((w for w in part if w["text"].upper().strip("|") == "PRODUCT"), None)
                if product:
                    columns["desc"] = product["x0"]
                layouts.append((line[0]["top"], columns,
                                line[stop]["x0"] if stop < len(line) else float("inf")))
    rows = []
    for top, columns, end in layouts:
        end = min(end, *(other["item"] for _, other, _ in layouts if other["item"] > columns["item"]),
                  float("inf"))
        keys = sorted(columns, key=columns.get)
        current = None
        for line in lines:
            if line[0]["top"] <= top:
                continue
            relevant = [w for w in line if columns["item"] - 4 <= w["x0"] < end]
            if not relevant:
                continue
            cells = {key: [] for key in keys}
            for word in relevant:
                key = max((k for k in keys if columns[k] - 4 <= word["x0"]),
                          key=columns.get, default=None)
                if key:
                    cells[key].append(word["text"])
            item = " ".join(cells["item"]).strip()
            if re.fullmatch(r"\d{1,4}\*?", item):
                current = {key: " ".join(cells.get(key, [])) for key in keys}
                rows.append(current)
            elif current and not item and cells.get("desc"):
                current["desc"] += " " + " ".join(cells["desc"])
                if len(current["desc"]) > 500:
                    raise OCRError("BOM row boundaries could not be reconstructed reliably")
    header = ["ITEM", "DESCRIPTION", "MANUFACTURER", "PART", "QTY", "SUPPLIED", "INSTALLED"]
    return [header] + [[r.get(k, "") for k in ("item", "desc", "mfr", "part", "qty", "supplied", "installed")]
                       for r in rows] if rows else []


def inspect_image_page(page, page_no: int) -> tuple[list[list[str]], list[dict]]:
    """Find BOM/revision text on a raster page; OCR BOM tables at higher resolution."""
    if not _tesseract()[0]:
        raise OCRError("Tesseract is not installed or is not on PATH")
    image, dpi = _render(page, 2600)
    text, words, width, height = _searchable_page(image, dpi)
    flags = []
    for line in _lines(words):
        content = " ".join(w["text"] for w in line)
        if re.search(r"\bREVISION\b", content, re.I):
            left = max(0, min(w["x0"] for w in line) / width - 0.05)
            top = max(0, line[0]["top"] / height - 0.02)
            box = (int(image.width * left), int(image.height * top),
                   min(image.width, int(image.width * (left + 0.55))),
                   min(image.height, int(image.height * (top + 0.25))))
            revision_text, _, _, _ = _searchable_page(image.crop(box), dpi)
            revision_text = re.sub(r"\s+", " ", revision_text).strip()
            flags.append({"type": "ocr_revision", "severity": "review", "page": page_no,
                          "message": f"OCR found revision-area text on page {page_no}: {revision_text[:500]}. "
                                     "Check the drawing for the complete revision notes."})
            break
    if not (re.search(r"\bBILL\s+OF\s+MATERIALS\b", text, re.I)
            or re.search(r"\bITEM\b", text, re.I) and re.search(r"\bQTY\b", text, re.I)
            or re.search(r"\bBOM[-\s]*\d", text, re.I)):
        flags.append({"type": "ocr_no_bom", "severity": "review", "page": page_no,
                      "message": f"Page {page_no} was inspected with OCR; no BOM table was identified. "
                                 "Verify image-only sheets and revision notes manually."})
        return [], flags
    header = next((line for line in _lines(words)
                   if re.search(r"\bITEM\b", " ".join(w["text"] for w in line), re.I)
                   and re.search(r"\b(?:QTY|QUANTITY|SUPPLIED)\b", " ".join(w["text"] for w in line), re.I)), None)
    try:
        image, dpi = _render(page, 7000)
        if header:
            top = max(0, int((header[0]["top"] / height - 0.02) * image.height))
            image = image.crop((0, top, image.width, image.height))
        _, words, _, _ = _searchable_page(image, dpi)
        rows = _table_rows(words)
    except OCRError as exc:
        flags.append({"type": "ocr_bom", "severity": "warning", "page": page_no, "reconstructed": False,
                      "message": f"Page {page_no} looks like a BOM, but OCR failed: {exc}."})
        return [], flags
    flags.append({"type": "ocr_bom", "severity": "review", "page": page_no, "reconstructed": bool(rows),
                  "message": f"Page {page_no} BOM was read with OCR; verify every item, quantity and unit."
                             if rows else f"Page {page_no} looks like a BOM, but OCR could not reconstruct its table."})
    return rows, flags
