"""List published app releases that include the current platform's package."""
from __future__ import annotations

from app import update_config
from app.services import updater


def list_available_releases(timeout: float = 8.0) -> tuple[list[updater.UpdateInfo], str]:
    """Return published releases with a platform asset, newest version first.

    Includes older and prerelease versions so users can explicitly roll back or
    select a prerelease. Draft releases are not returned by GitHub's releases API.
    """
    asset_name = updater.asset_name_for_platform()
    if not asset_name:
        return [], "Updates are only available on Windows and macOS."

    releases: list[updater.UpdateInfo] = []
    try:
        for page in range(1, 21):
            response = updater.httpx.get(
                f"{updater.API}/repos/{update_config.UPDATE_REPO}/releases",
                params={"per_page": 100, "page": page},
                headers=updater._headers("application/vnd.github+json"),
                timeout=timeout,
            )
            if response.status_code in (401, 403, 404):
                return [], (f"Could not read releases (HTTP {response.status_code}). "
                            "The update token may be missing, expired or lack access.")
            if response.status_code != 200:
                return [], f"Could not list releases (HTTP {response.status_code})."
            batch = response.json()
            if not isinstance(batch, list):
                return [], "GitHub returned an unexpected release list."
            for release in batch:
                tag = release.get("tag_name") or ""
                asset = next((item for item in release.get("assets", [])
                              if item.get("name") == asset_name and item.get("url")), None)
                if tag and asset:
                    releases.append(updater.UpdateInfo(
                        tag.lstrip("v"), release.get("body") or "", asset_name, asset["url"]
                    ))
            if len(batch) < 100:
                break
        # Keep the first copy of a tag if GitHub data ever contains duplicates.
        unique = {item.version: item for item in releases}
        return sorted(unique.values(), key=lambda item: updater.parse_version(item.version), reverse=True), ""
    except Exception as exc:
        return [], f"Could not reach GitHub: {exc.__class__.__name__}"
