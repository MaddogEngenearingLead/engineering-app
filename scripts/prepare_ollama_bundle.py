"""Download and verify the official Ollama runtime archive for desktop builds."""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import stat
import tempfile
import urllib.request
import zipfile
from pathlib import Path

OLLAMA_VERSION = "v0.40.15"
ASSETS = {
    "win32": "ollama-windows-amd64.zip",
    "darwin": "Ollama-darwin.zip",
}


def download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "EngineeringApp-build"})
    with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as target:
        shutil.copyfileobj(response, target)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare(output: Path, platform: str) -> Path:
    asset = ASSETS.get(platform)
    if not asset:
        raise ValueError(f"Unsupported Ollama build platform: {platform}")
    base = f"https://github.com/ollama/ollama/releases/download/{OLLAMA_VERSION}"
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        checksums = temp / "sha256sum.txt"
        archive = temp / asset
        download(f"{base}/sha256sum.txt", checksums)
        expected = next((fields[0].lower() for line in checksums.read_text().splitlines()
                         if (fields := line.split()) and
                         Path(fields[-1].lstrip("*")).name == asset), None)
        if not expected or len(expected) != 64:
            raise RuntimeError(f"No SHA-256 checksum published for {asset}.")
        download(f"{base}/{asset}", archive)
        digest = sha256(archive)
        if digest != expected:
            raise RuntimeError(f"SHA-256 verification failed for {asset}.")
        executable = ("ollama.exe" if platform == "win32"
                      else "Ollama.app/Contents/Resources/ollama")
        with zipfile.ZipFile(archive) as bundle:
            entries = bundle.infolist()
            if executable not in {entry.filename for entry in entries}:
                raise RuntimeError(f"Expected Ollama executable is missing from {asset}.")
            target = output / "ollama-runtime"
            if target.exists():
                shutil.rmtree(target)
            target.mkdir(parents=True, exist_ok=True)
            root = target.resolve()
            links = []
            for entry in entries:
                extracted = (target / entry.filename).resolve()
                if not extracted.is_relative_to(root):
                    raise RuntimeError("Ollama archive contains an unsafe path.")
                mode = entry.external_attr >> 16
                if stat.S_ISLNK(mode):
                    link = Path(bundle.read(entry).decode("utf-8"))
                    if link.is_absolute() or not (extracted.parent / link).resolve().is_relative_to(root):
                        raise RuntimeError("Ollama archive contains an unsafe symlink.")
                    links.append((extracted, link))
                    continue
                bundle.extract(entry, target)
                if mode & 0o111:
                    extracted.chmod(extracted.stat().st_mode | 0o111)
            for path, link in links:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.symlink_to(link)
        return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--platform", default=os.sys.platform)
    args = parser.parse_args()
    print(prepare(args.output, args.platform))
