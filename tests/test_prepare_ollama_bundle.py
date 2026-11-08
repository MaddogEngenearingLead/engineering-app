from __future__ import annotations

import shutil
import stat
import zipfile

import pytest

from scripts import prepare_ollama_bundle


def _mock_release_download(monkeypatch, source_archive):
    digest = prepare_ollama_bundle.sha256(source_archive)
    asset = prepare_ollama_bundle.ASSETS["win32"]

    def download(url, destination):
        if url.endswith("sha256sum.txt"):
            destination.write_text(f"{digest}  ./{asset}\n")
        else:
            shutil.copyfile(source_archive, destination)

    monkeypatch.setattr(prepare_ollama_bundle, "download", download)


def test_prepares_verified_runtime_folder(tmp_path, monkeypatch):
    archive_path = tmp_path / "source.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("ollama.exe", "runtime")
        archive.writestr("lib/ollama.dll", "library")
    _mock_release_download(monkeypatch, archive_path)

    output = prepare_ollama_bundle.prepare(tmp_path / "output", "win32")

    assert (output / "ollama.exe").read_text() == "runtime"
    assert (output / "lib" / "ollama.dll").read_text() == "library"


def test_rejects_runtime_archive_path_traversal(tmp_path, monkeypatch):
    archive_path = tmp_path / "source.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("ollama.exe", "runtime")
        archive.writestr("../outside.dll", "unsafe")
    _mock_release_download(monkeypatch, archive_path)

    with pytest.raises(RuntimeError, match="unsafe path"):
        prepare_ollama_bundle.prepare(tmp_path / "output", "win32")
    assert not (tmp_path / "outside.dll").exists()


def test_preserves_runtime_symlinks(tmp_path, monkeypatch):
    archive_path = tmp_path / "source.zip"
    link = zipfile.ZipInfo("lib/current.dll")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("ollama.exe", "runtime")
        archive.writestr("lib/versioned.dll", "library")
        archive.writestr(link, "versioned.dll")
    _mock_release_download(monkeypatch, archive_path)

    output = prepare_ollama_bundle.prepare(tmp_path / "output", "win32")

    assert (output / "lib/current.dll").is_symlink()
    assert (output / "lib/current.dll").read_text() == "library"
