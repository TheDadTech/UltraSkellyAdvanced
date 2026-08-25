from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tomllib
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

import httpx


class UpdateError(RuntimeError):
    """A release could not be safely staged for installation."""


class UpdateManager:
    MAX_DOWNLOAD_BYTES = 150 * 1024 * 1024
    MAX_EXTRACTED_BYTES = 350 * 1024 * 1024

    def __init__(self, data_dir: Path, helper: Path) -> None:
        self.data_dir = data_dir
        self.helper = helper
        self.update_dir = data_dir / "updates"
        self.status_path = data_dir / "update-status.json"
        self.rollback_path = data_dir / "update-rollback.json"

    def status(self) -> dict[str, object]:
        try:
            payload = json.loads(self.status_path.read_text("utf-8"))
        except (OSError, ValueError):
            return {"state": "idle", "message": "No update is being installed."}
        return payload if isinstance(payload, dict) else {"state": "idle"}

    def rollback_status(self, *, current_version: str) -> dict[str, object]:
        try:
            payload = json.loads(self.rollback_path.read_text("utf-8"))
        except (OSError, ValueError):
            return {"available": False, "previous_version": None}
        if not isinstance(payload, dict):
            return {"available": False, "previous_version": None}
        previous = str(payload.get("previous_version") or "").strip()
        installed = str(payload.get("installed_version") or "").strip()
        available = bool(payload.get("available") and previous and installed == current_version)
        return {
            "available": available,
            "previous_version": previous if available else None,
        }

    def start_rollback(self, *, current_version: str) -> dict[str, object]:
        rollback = self.rollback_status(current_version=current_version)
        if not rollback["available"]:
            raise UpdateError("No previous USA version is available for rollback")
        if self.status().get("state") in {"downloading", "staged", "installing", "rolling_back"}:
            raise UpdateError("An update or rollback is already in progress")
        previous = str(rollback["previous_version"])
        self._write_status(
            "rolling_back",
            f"Rolling back USA {current_version} to {previous}. The dashboard will restart…",
            previous,
        )
        result = subprocess.run(
            ["sudo", "-n", str(self.helper), "update-rollback", current_version],
            text=True, capture_output=True, timeout=45, check=False,
        )
        if result.returncode:
            message = (result.stderr or result.stdout or "The rollback could not start").strip()
            self._write_status("failed", message, previous)
            raise UpdateError(message)
        return self.status()

    async def stage_and_start(
        self,
        manifest: dict[str, object],
        *,
        current_version: str,
    ) -> dict[str, object]:
        version = str(manifest.get("version") or "").strip()
        package_url = str(manifest.get("package_url") or "").strip()
        expected_hash = str(manifest.get("sha256") or "").strip().lower()
        if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?", version):
            raise UpdateError("The release version is invalid")
        if urlparse(package_url).scheme != "https":
            raise UpdateError("The release does not provide a secure update package")
        if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
            raise UpdateError("The release does not provide a valid SHA-256 checksum")
        if self.status().get("state") in {"downloading", "staged", "installing"}:
            raise UpdateError("An update is already in progress")

        stage = self.update_dir / version
        archive = stage / "release.zip"
        source = stage / "source"
        if stage.exists():
            shutil.rmtree(stage)
        stage.mkdir(parents=True, mode=0o700)
        self._write_status("downloading", f"Downloading USA {version}…", version)

        digest = hashlib.sha256()
        received = 0
        try:
            async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
                async with client.stream("GET", package_url) as response:
                    response.raise_for_status()
                    with archive.open("wb") as output:
                        async for chunk in response.aiter_bytes():
                            received += len(chunk)
                            if received > self.MAX_DOWNLOAD_BYTES:
                                raise UpdateError("The update package is unexpectedly large")
                            digest.update(chunk)
                            output.write(chunk)
        except httpx.HTTPError as exc:
            self._write_status("failed", "The update package could not be downloaded.", version)
            raise UpdateError("The update package could not be downloaded") from exc
        if digest.hexdigest() != expected_hash:
            archive.unlink(missing_ok=True)
            self._write_status("failed", "The update checksum did not match. Nothing was installed.", version)
            raise UpdateError("The update checksum did not match; nothing was installed")

        try:
            project_root = self._extract_and_validate(archive, source, version)
        except (OSError, ValueError, zipfile.BadZipFile, UpdateError) as exc:
            self._write_status("failed", f"The update package is invalid: {exc}", version)
            raise UpdateError(f"The update package is invalid: {exc}") from exc

        self._write_status("staged", f"USA {version} was verified and is ready to install.", version)
        result = subprocess.run(
            [
                "sudo", "-n", str(self.helper), "update-install",
                version, str(project_root), current_version,
            ],
            text=True,
            capture_output=True,
            timeout=45,
            check=False,
        )
        if result.returncode:
            message = (result.stderr or result.stdout or "The installer could not start").strip()
            self._write_status("failed", message, version)
            raise UpdateError(message)
        return self.status()

    def _extract_and_validate(self, archive: Path, destination: Path, version: str) -> Path:
        with zipfile.ZipFile(archive) as bundle:
            members = bundle.infolist()
            if len(members) > 5000:
                raise UpdateError("too many files")
            expanded = 0
            for member in members:
                path = PurePosixPath(member.filename)
                if path.is_absolute() or ".." in path.parts:
                    raise UpdateError("unsafe file path")
                expanded += member.file_size
                if expanded > self.MAX_EXTRACTED_BYTES:
                    raise UpdateError("expanded files are unexpectedly large")
                # ZIP Unix mode: reject symbolic links.
                if (member.external_attr >> 16) & 0o170000 == 0o120000:
                    raise UpdateError("symbolic links are not accepted")
            bundle.extractall(destination)

        candidates = [destination, *[path for path in destination.iterdir() if path.is_dir()]]
        for candidate in candidates:
            project = candidate / "pyproject.toml"
            installer = candidate / "deploy" / "bootstrap-pi.sh"
            if not project.is_file() or not installer.is_file():
                continue
            metadata = tomllib.loads(project.read_text("utf-8"))
            packaged_version = str(metadata.get("project", {}).get("version", ""))
            if packaged_version != version:
                raise UpdateError("package version does not match the release manifest")
            return candidate.resolve()
        raise UpdateError("USA installer files were not found")

    def _write_status(self, state: str, message: str, version: str) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.status_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"state": state, "message": message, "version": version}),
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        temporary.replace(self.status_path)

