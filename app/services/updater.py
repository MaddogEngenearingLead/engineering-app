"""Check GitHub Releases for a newer desktop build and apply it in place.

Release assets are expected to be ``JobManager-windows.zip`` (Windows) and
``JobManager-macos.zip`` (macOS), as produced by the Build GUI workflow.
"""
from __future__ import annotations

import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import httpx

from app import update_config
from app.version import __version__

API = "https://api.github.com"
Progress = Callable[[str, int, int | None], None]
_UPDATE_MARKER = ".engineering-app-update"


@dataclass
class UpdateInfo:
    version: str
    notes: str
    asset_name: str
    asset_url: str


def parse_version(value: str) -> tuple[int, ...]:
    """'v1.2.3' -> (1, 2, 3). Non-numeric parts are ignored."""
    return tuple(int(n) for n in re.findall(r"\d+", value.split("-")[0])) or (0,)


def is_newer(candidate: str, current: str) -> bool:
    return parse_version(candidate) > parse_version(current)


def asset_name_for_platform() -> str | None:
    if sys.platform.startswith("win"):
        return "JobManager-windows.zip"
    if sys.platform == "darwin":
        return "JobManager-macos.zip"
    return None


def _headers(accept: str) -> dict[str, str]:
    headers = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28"}
    token = os.environ.get("UPDATE_TOKEN") or update_config.UPDATE_TOKEN
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def check_for_update(current: str = __version__, timeout: float = 8.0) -> UpdateInfo | None:
    """Return the newer release for this platform, or None. Never raises."""
    return check_for_update_status(current, timeout)[0]


def check_for_update_status(current: str = __version__, timeout: float = 8.0) -> tuple[UpdateInfo | None, str]:
    """Like ``check_for_update`` but also returns a human-readable result message."""
    try:
        name = asset_name_for_platform()
        if not name:
            return None, "Updates are only available on Windows and macOS."
        resp = httpx.get(
            f"{API}/repos/{update_config.UPDATE_REPO}/releases/latest",
            headers=_headers("application/vnd.github+json"),
            timeout=timeout,
        )
        if resp.status_code in (401, 403, 404):
            return None, (f"Could not read releases (HTTP {resp.status_code}). "
                          "The update token may be missing, expired or lack access.")
        if resp.status_code != 200:
            return None, f"Update check failed (HTTP {resp.status_code})."
        release = resp.json()
        tag = release.get("tag_name") or ""
        if not is_newer(tag, current):
            return None, f"You are up to date (v{current})."
        for asset in release.get("assets", []):
            if asset.get("name") == name:
                return UpdateInfo(tag.lstrip("v"), release.get("body") or "", name, asset["url"]), \
                    f"Update available: {tag}"
        return None, f"Release {tag} has no {name} file."
    except Exception as exc:
        return None, f"Could not reach GitHub: {exc.__class__.__name__}"


def can_self_update() -> bool:
    """Only a packaged (PyInstaller) build can replace itself."""
    return bool(getattr(sys, "frozen", False)) and asset_name_for_platform() is not None


def download_update(info: UpdateInfo, dest_dir: Path | None = None,
                    progress: Progress | None = None) -> Path:
    owned = dest_dir is None
    if owned:
        dest_dir = Path(tempfile.mkdtemp(prefix="jm_update_"))
        (dest_dir / _UPDATE_MARKER).write_text("Engineering App update\n", encoding="utf-8")
    assert dest_dir is not None
    target = dest_dir / info.asset_name
    try:
        with httpx.stream(
            "GET", info.asset_url, headers=_headers("application/octet-stream"),
            follow_redirects=True, timeout=120.0,
        ) as resp:
            resp.raise_for_status()
            length = resp.headers.get("content-length", "")
            total = int(length) if length.isdigit() else None
            received = 0
            if progress:
                progress("Downloading", received, total)
            with open(target, "wb") as fh:
                for chunk in resp.iter_bytes():
                    fh.write(chunk)
                    received += len(chunk)
                    if progress:
                        progress("Downloading", received, total)
    except Exception:
        if owned:
            cleanup_update(target)
        raise
    return target


def _owned_update_dir(downloaded: Path) -> Path | None:
    directory = downloaded.parent
    if (directory.is_symlink() or not directory.name.startswith("jm_update_")
            or directory.resolve().parent != Path(tempfile.gettempdir()).resolve()
            or not (directory / _UPDATE_MARKER).is_file()
            or (directory / _UPDATE_MARKER).is_symlink()):
        return None
    return directory


def cleanup_update(downloaded: Path) -> None:
    """Remove only a staging directory created and marked by this updater."""
    directory = _owned_update_dir(downloaded)
    if directory:
        shutil.rmtree(directory)


def _extract_update(downloaded: Path, destination: Path, progress: Progress | None = None) -> None:
    root = destination.resolve()
    links = []
    with zipfile.ZipFile(downloaded) as archive:
        total = sum(entry.file_size for entry in archive.infolist() if not entry.is_dir())
        extracted = 0
        if progress:
            progress("Extracting", 0, total)
        for entry in archive.infolist():
            path = (destination / entry.filename).resolve()
            if not path.is_relative_to(root):
                raise RuntimeError("The update archive contains an unsafe path.")
            mode = entry.external_attr >> 16
            if stat.S_ISLNK(mode):
                link = Path(archive.read(entry).decode("utf-8"))
                if link.is_absolute() or not (path.parent / link).resolve().is_relative_to(root):
                    raise RuntimeError("The update archive contains an unsafe symlink.")
                links.append((path, link))
                extracted += entry.file_size
                if progress:
                    progress("Extracting", extracted, total)
                continue
            if entry.is_dir():
                path.mkdir(parents=True, exist_ok=True)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(entry) as source, path.open("wb") as target:
                while chunk := source.read(1024 * 1024):
                    target.write(chunk)
                    extracted += len(chunk)
                    if progress:
                        progress("Extracting", extracted, total)
            if mode & 0o111:
                path.chmod(path.stat().st_mode | 0o111)
    for path, link in links:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(link)


def apply_update(downloaded: Path, progress: Progress | None = None) -> None:
    """Start a helper that swaps in the new build after this process exits, then relaunches.

    The caller must exit the app right after this returns.
    """
    pid = os.getpid()
    if sys.platform.startswith("win"):
        current = Path(sys.executable)
        install_dir = current.parent
        try:
            with tempfile.TemporaryFile(dir=install_dir):
                pass
        except OSError as exc:
            raise RuntimeError(
                f"The app folder is not writable ({install_dir}). "
                "Move the app to a writable folder or update it manually."
            ) from exc
        extract_dir = downloaded.parent / "extracted"
        _extract_update(downloaded, extract_dir, progress)
        if not (extract_dir / "JobManager.exe").is_file() or not (extract_dir / "_internal").is_dir():
            raise RuntimeError("The Windows update archive is missing the app executable or runtime.")
        if not (install_dir / "_internal").is_dir():
            raise RuntimeError("The installed app runtime is missing; install the update manually.")
        suffix = uuid.uuid4().hex
        old_internal = install_dir / f"_internal-update-backup-{suffix}"
        old_exe = install_dir / f"JobManager-update-backup-{suffix}.exe"
        script = downloaded.parent / "apply_update.bat"
        owned_dir = _owned_update_dir(downloaded)
        cleanup_staging = f'(goto) 2>nul & rmdir /S /Q "{owned_dir}"\r\n' if owned_dir else ""
        script.write_text(
            "@echo off\r\n"
            "title Engineering App update\r\n"
            "echo Waiting for Engineering App to close...\r\n"
            ":wait\r\n"
            f'tasklist /FI "PID eq {pid}" /NH | findstr /C:"{pid}" >nul\r\n'
            "if not errorlevel 1 (\r\n"
            "  ping -n 2 127.0.0.1 >nul\r\n"
            "  goto wait\r\n"
            ")\r\n"
            "echo Installing the update. Please wait...\r\n"
            f'move "{install_dir / "_internal"}" "{old_internal}" >nul\r\n'
            "if errorlevel 1 goto failed\r\n"
            f'move "{current}" "{old_exe}" >nul\r\n'
            "if errorlevel 1 goto restore_internal\r\n"
            f'robocopy "{extract_dir / "_internal"}" "{install_dir / "_internal"}" /E /COPY:DAT /R:2 /W:1 >nul\r\n'
            "if errorlevel 8 goto restore_new_internal\r\n"
            f'copy /Y "{extract_dir / "JobManager.exe"}" "{current}" >nul\r\n'
            "if errorlevel 1 goto restore_new_internal\r\n"
            f'rmdir /S /Q "{old_internal}"\r\n'
            "if errorlevel 1 goto cleanup_failed\r\n"
            f'del /Q "{old_exe}"\r\n'
            "if errorlevel 1 goto cleanup_failed\r\n"
            f'start "" "{current}"\r\n'
            f"{cleanup_staging}"
            "exit /b 0\r\n"
            ":restore_new_internal\r\n"
            f'if exist "{current}" del /Q "{current}"\r\n'
            f'if exist "{install_dir / "_internal"}" rmdir /S /Q "{install_dir / "_internal"}"\r\n'
            ":restore_exe\r\n"
            f'move "{old_exe}" "{current}" >nul\r\n'
            ":restore_internal\r\n"
            f'move "{old_internal}" "{install_dir / "_internal"}" >nul\r\n'
            ":failed\r\n"
            "echo Update failed. Check folder permissions and disk space; the app may need manual repair.\r\n"
            f'echo Update files: {downloaded.parent}\r\n'
            f'echo Old app backups, if present: {old_internal} and {old_exe}\r\n'
            "pause\r\n"
            "exit /b 1\r\n"
            ":cleanup_failed\r\n"
            "echo Update installed, but old application files could not be removed.\r\n"
            f'echo Backup files: {old_internal} and {old_exe}\r\n'
            "pause\r\n"
            f'start "" "{current}"\r\n'
            "exit /b 1\r\n"
        )
        env = {k: v for k, v in os.environ.items() if not k.startswith(("_MEI", "_PYI"))}
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        subprocess.Popen(
            ["cmd", "/c", str(script)],
            creationflags=0x00000010,  # new console remains visible if installation fails
            close_fds=True, env=env,
        )
    elif sys.platform == "darwin":
        # .../JobManager.app/Contents/MacOS/JobManager -> .../JobManager.app
        app_bundle = Path(sys.executable).resolve().parents[2]
        extract_dir = downloaded.parent / "extracted"
        _extract_update(downloaded, extract_dir, progress)
        new_app = extract_dir / "JobManager.app"
        if not (new_app / "Contents" / "MacOS" / "JobManager").is_file():
            raise RuntimeError("The macOS update archive is missing the application executable.")
        backup = app_bundle.with_name(f"{app_bundle.name}.update-backup-{uuid.uuid4().hex}")
        script = downloaded.parent / "apply_update.sh"
        owned_dir = _owned_update_dir(downloaded)
        cleanup_staging = f"rm -rf -- {shlex.quote(str(owned_dir))}\n" if owned_dir else ""
        old = shlex.quote(str(app_bundle))
        new = shlex.quote(str(new_app))
        backup_arg = shlex.quote(str(backup))
        script.write_text(
            "#!/bin/sh\n"
            f"while kill -0 {pid} 2>/dev/null; do sleep 1; done\n"
            f"if ! mv {old} {backup_arg}; then osascript -e 'display alert \"Update failed: cannot move the old app.\"'; exit 1; fi\n"
            f"if ! ditto {new} {old}; then\n"
            f"  if ! rm -rf -- {old} || ! mv {backup_arg} {old}; then\n"
            "    osascript -e 'display alert \"Update rollback failed; restore the backup manually.\"'\n"
            "    exit 1\n"
            "  fi\n"
            "  osascript -e 'display alert \"Update failed; the previous app was restored.\"'\n"
            "  exit 1\n"
            "fi\n"
            f"xattr -dr com.apple.quarantine {old} 2>/dev/null\n"
            f"if ! rm -rf -- {backup_arg}; then osascript -e 'display alert \"Update installed, but old app backup could not be removed.\"'; fi\n"
            f"open {old}\n"
            f"{cleanup_staging}"
        )
        script.chmod(0o755)
        env = {k: v for k, v in os.environ.items() if not k.startswith(("_MEI", "_PYI"))}
        subprocess.Popen(["/bin/sh", str(script)], start_new_session=True, close_fds=True, env=env)
    else:
        raise RuntimeError("Self-update is not supported on this platform.")
