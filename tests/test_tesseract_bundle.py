import hashlib
import io
import json
import sys

import pytest

from scripts import prepare_tesseract_bundle as bundler
from app.services import drawing_ocr


@pytest.mark.parametrize("platform,bindir,executable,library,library_dir", [
    ("win32", "Library/bin", "tesseract.exe", "ocr.dll", "bin"),
    ("darwin", "bin", "tesseract", "libocr.dylib", "lib"),
])
def test_prepare_bundle_and_licenses(tmp_path, monkeypatch, platform, bindir, executable, library, library_dir):
    prefix = tmp_path / "env"
    source_bin = prefix / bindir
    source_bin.mkdir(parents=True)
    (source_bin / executable).write_bytes(b"exe")
    source_lib = source_bin if platform == "win32" else prefix / "lib"
    source_lib.mkdir(exist_ok=True)
    (source_lib / library).write_bytes(b"lib")
    data = prefix / "share" / "tessdata"
    data.mkdir(parents=True)
    (data / "eng.traineddata").write_bytes(b"english")
    metadata = prefix / "conda-meta"
    metadata.mkdir()
    cache = tmp_path / "cache"
    package = cache / "https" / "example.test" / "ocr-1-0"
    (metadata / "ocr.json").write_text(json.dumps({
        "name": "ocr", "version": "1", "build": "0", "extracted_package_dir": str(package)}))
    license_dir = package / "info" / "licenses"
    license_dir.mkdir(parents=True)
    (license_dir / "LICENSE").write_text("license")
    font = b"font"
    monkeypatch.setattr(bundler.urllib.request, "urlopen", lambda *args, **kwargs: io.BytesIO(font))
    monkeypatch.setattr(bundler, "FONT_SHA256", hashlib.sha256(font).hexdigest())
    output = tmp_path / "bundle"

    bundler.prepare(prefix, cache, output, platform)

    assert (output / "bin" / executable).read_bytes() == b"exe"
    assert (output / library_dir / library).read_bytes() == b"lib"
    assert (output / "tessdata" / "eng.traineddata").read_bytes() == b"english"
    assert (output / "tessdata" / "pdf.ttf").read_bytes() == font
    assert (output / "licenses" / "ocr-1-0" / "licenses" / "LICENSE").read_text() == "license"


def test_bundled_bin_is_preferred_over_path(tmp_path, monkeypatch):
    root = tmp_path / "tesseract"
    binary = root / "bin" / ("tesseract.exe" if sys.platform.startswith("win") else "tesseract")
    binary.parent.mkdir(parents=True)
    binary.touch()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.setattr(drawing_ocr.shutil, "which", lambda _: "system-tesseract")
    selected, env = drawing_ocr._tesseract()
    assert selected == str(binary)
    assert env["TESSDATA_PREFIX"] == str(root / "tessdata")
