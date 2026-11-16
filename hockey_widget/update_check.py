"""Update check against the GitHub releases of this repository (public, no token).

The installer is run only after its SHA-256 matches its line in SHA256SUMS.txt of the same release.
`check` never raises; `install_update` raises UpdateError with a message for the user.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

REPO = "tristanbest0802-beep/hockey-score-widget"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"  # stable releases only
DOWNLOAD_PREFIX = f"https://github.com/{REPO}/releases/download/"
INSTALLER = "HockeyScoreWidget-Setup.exe"
SUMS = "SHA256SUMS.txt"
MAX_BYTES = 200_000_000  # the installer is a few tens of MB; beyond this the answer is not one
Getter = Callable[[str], bytes]


class UpdateError(Exception):
    pass


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    installer_url: str
    sums_url: str


def http_get(url: str, timeout: float = 15.0) -> bytes:
    if not url.startswith("https://"):
        raise ValueError("adresse non https")
    req = urllib.request.Request(url, headers={"User-Agent": "HockeyScoreWidget-update-check",
                                               "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - https checked above and below
        if not r.geturl().startswith("https://"):  # a redirect must not leave https
            raise ValueError("redirection hors https")
        data = r.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("réponse trop grosse")
    return data


def parse_version(text: str) -> tuple[int, int, int]:
    """'v1.2.3' or '1.2.3-beta' -> (1, 2, 3); a missing part is 0."""
    nums = [int(n) for n in re.findall(r"\d+", text.split("-")[0])[:3]]
    return tuple((nums + [0, 0, 0])[:3])  # type: ignore[return-value]


def find_update(current: str, release: dict) -> UpdateInfo | None:
    """The release if it is newer than `current` and carries the installer and SHA256SUMS.txt."""
    tag = str(release.get("tag_name", ""))
    if release.get("draft") or parse_version(tag) <= parse_version(current):
        return None
    urls = {a.get("name"): str(a.get("browser_download_url", "")) for a in release.get("assets", [])}
    exe, sums = urls.get(INSTALLER, ""), urls.get(SUMS, "")
    if exe.startswith(DOWNLOAD_PREFIX) and sums.startswith(DOWNLOAD_PREFIX):
        return UpdateInfo(tag.lstrip("v"), exe, sums)
    return None


def check(current: str, get: Getter = http_get) -> UpdateInfo | None:
    """The update, or None when up to date. Network and JSON errors raise: the caller shows them."""
    return find_update(current, json.loads(get(LATEST_URL)))


def expected_sha(sums: str) -> str:
    """The installer's hash from a `sha256sum` output ('<hash>  <name>' per line)."""
    for line in sums.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == INSTALLER and re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            return parts[0].lower()
    raise UpdateError("Somme de contrôle introuvable : mise à jour refusée.")


def download_verified(info: UpdateInfo, folder: Path, get: Getter = http_get) -> Path:
    try:
        sums = get(info.sums_url).decode("ascii", "replace")
        data = get(info.installer_url)
    except Exception as exc:
        raise UpdateError(f"Téléchargement impossible : {exc}") from exc
    if hashlib.sha256(data).hexdigest() != expected_sha(sums):
        raise UpdateError("Somme de contrôle SHA-256 différente : installateur refusé.")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / INSTALLER
    path.write_bytes(data)
    return path


def install_update(info: UpdateInfo, folder: Path, get: Getter = http_get, launch=subprocess.Popen) -> None:
    """Download, verify, then start the installer (it closes this program itself: CloseApplications=yes)."""
    launch([str(download_verified(info, folder, get))])
