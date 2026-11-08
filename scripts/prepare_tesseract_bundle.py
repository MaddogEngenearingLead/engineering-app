"""Prepare a relocatable OCR runtime from a conda-forge Tesseract environment."""
import argparse
import hashlib
import json
import shutil
import sys
import urllib.request
from pathlib import Path


FONT_URL = "https://raw.githubusercontent.com/tesseract-ocr/tesseract/5.5.3/tessdata/pdf.ttf"
FONT_SHA256 = "c7845420925a23d88ed830a63957b8af85a66a8daf8d9fc90e843673b2ef1a59"


def prepare(prefix: Path, cache: Path, output: Path, platform: str) -> None:
    if output.exists():
        raise ValueError(f"Output directory already exists: {output}")
    windows = platform == "win32"
    source_bin = prefix / ("Library/bin" if windows else "bin")
    executable = source_bin / ("tesseract.exe" if windows else "tesseract")
    data = prefix / "share" / "tessdata" / "eng.traineddata"
    if not executable.is_file() or not data.is_file():
        raise FileNotFoundError("The conda environment must contain Tesseract and English language data")

    bin_dir = output / "bin"
    bin_dir.mkdir(parents=True)
    shutil.copy2(executable, bin_dir / executable.name)
    pattern = "*.dylib" if platform == "darwin" else "*.so*"
    libraries = source_bin.glob("*.dll") if windows else (prefix / "lib").glob(pattern)
    lib_dir = bin_dir if windows else output / "lib"
    lib_dir.mkdir(exist_ok=True)
    count = 0
    for library in libraries:
        if not library.is_file():
            continue
        shutil.copy2(library, lib_dir / library.name, follow_symlinks=True)
        count += 1
    if not count:
        raise FileNotFoundError("No Tesseract runtime libraries found")

    tessdata = output / "tessdata"
    tessdata.mkdir()
    shutil.copy2(data, tessdata / data.name)
    with urllib.request.urlopen(FONT_URL, timeout=60) as response:
        font = response.read()
    if hashlib.sha256(font).hexdigest() != FONT_SHA256:
        raise ValueError("Tesseract PDF font checksum mismatch")
    (tessdata / "pdf.ttf").write_bytes(font)

    records = list((prefix / "conda-meta").glob("*.json"))
    if not records:
        raise FileNotFoundError("Conda package metadata is missing")
    notices = output / "licenses"
    notices.mkdir()
    for record in records:
        metadata = json.loads(record.read_text(encoding="utf-8"))
        name = f'{metadata["name"]}-{metadata["version"]}-{metadata["build"]}'
        extracted = metadata.get("extracted_package_dir")
        source = Path(extracted) / "info" / "licenses" if extracted else cache / name / "info" / "licenses"
        if not source.is_dir():
            matches = list(cache.glob(f"**/{name}/info/licenses"))
            if matches:
                source = matches[0]
        target = notices / name
        target.mkdir()
        (target / "package.json").write_text(
            json.dumps({k: metadata.get(k) for k in ("name", "version", "license", "license_family", "url")},
                       indent=2) + "\n", encoding="utf-8")
        if source.is_dir():
            shutil.copytree(source, target / "licenses")
        elif metadata["name"] == "tesseract":
            raise FileNotFoundError("Tesseract license files are missing from the package cache")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform not in ("win32", "darwin", "linux"):
        parser.error(f"Unsupported platform: {sys.platform}")
    prepare(args.prefix, args.cache, args.output, sys.platform)


if __name__ == "__main__":
    main()
