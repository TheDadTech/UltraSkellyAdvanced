"""Password-encrypted, allowlisted portable application backups.

Never captures host WiFi/BlueZ state, environment files, models or update stages.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from . import __version__
from .operation_settings import OperationSettings
from .provider_settings import ProviderSettings
from .pi_media import PiMediaLibrary


class BackupError(ValueError):
    pass


class BackupManager:
    MAGIC = b"USA-BACKUP-1\n"
    MAX_BYTES = 128 * 1024 * 1024
    SETTINGS = {"operation-settings.json", "provider-settings.json", "credentials.json", "pi-media.json", "nag-media.json"}

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir

    @staticmethod
    def _key(password: str, salt: bytes) -> bytes:
        if not 12 <= len(password) <= 256:
            raise BackupError("Use a backup password between 12 and 256 characters")
        return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(password.encode())

    def encrypt(self, payload: bytes, password: str) -> bytes:
        salt, nonce = os.urandom(16), os.urandom(12)
        return self.MAGIC + salt + nonce + AESGCM(self._key(password, salt)).encrypt(nonce, payload, self.MAGIC)

    def decrypt(self, payload: bytes, password: str) -> bytes:
        if len(payload) > self.MAX_BYTES or not payload.startswith(self.MAGIC) or len(payload) < len(self.MAGIC) + 44:
            raise BackupError("Not a supported encrypted USA backup")
        body = payload[len(self.MAGIC):]
        try:
            return AESGCM(self._key(password, body[:16])).decrypt(body[16:28], body[28:], self.MAGIC)
        except InvalidTag:
            raise BackupError("Incorrect password or damaged backup") from None

    def inventory(self, include_media: bool = False) -> dict:
        files = self._files(include_media)
        total = sum(path.stat().st_size for path in files.values())
        return {"files": sorted(files), "bytes": total, "limit_bytes": self.MAX_BYTES,
                "includes_media": include_media, "fits": total < self.MAX_BYTES - 1024 * 1024}

    def _files(self, include_media: bool) -> dict[str, Path]:
        files = {}
        for name in self.SETTINGS:
            path = self.data_dir / name
            if path.is_symlink():
                raise BackupError("Backup refuses linked settings files")
            if path.is_file():
                files[name] = path
        media = self.data_dir / "media"
        if media.is_symlink():
            raise BackupError("Backup refuses a linked media directory")
        if include_media and media.exists():
            for path in media.iterdir():
                if path.is_file() and not path.is_symlink() and path.suffix.lower() in PiMediaLibrary.ALLOWED_SUFFIXES:
                    files[f"media/{path.name}"] = path
        return files

    def create(self, password: str, include_media: bool = False, overrides: dict[str, bytes] | None = None) -> bytes:
        files = self._files(include_media)
        if not self.inventory(include_media)["fits"]:
            raise BackupError("Backup exceeds 128 MiB; omit audio files and copy large media separately")
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps({"format": 1, "version": __version__, "media": include_media}))
            for name, path in files.items():
                archive.writestr(name, (overrides or {}).get(name, path.read_bytes()))
            for name, payload in (overrides or {}).items():
                if name not in files:
                    archive.writestr(name, payload)
        if stream.tell() > self.MAX_BYTES - 1024:
            raise BackupError("Backup exceeds 128 MiB")
        return self.encrypt(stream.getvalue(), password)

    def inspect(self, encrypted: bytes, password: str) -> dict[str, bytes]:
        result = {}
        try:
            with zipfile.ZipFile(io.BytesIO(self.decrypt(encrypted, password))) as archive:
                members = archive.infolist()
                if len(members) > 2000 or sum(m.file_size for m in members) > self.MAX_BYTES:
                    raise BackupError("Backup contains too much data")
                for member in members:
                    name = member.filename
                    parts = name.split("/")
                    audio = len(parts) == 2 and parts[0] == "media" and parts[1] not in {"", ".", ".."} and not parts[1].startswith(".") and Path(parts[1]).suffix.lower() in PiMediaLibrary.ALLOWED_SUFFIXES
                    if "\\" in name or name in result or (name not in self.SETTINGS | {"manifest.json"} and not audio) or (member.external_attr >> 16) & 0o170000 == 0o120000:
                        raise BackupError("Backup contains an unsafe or unsupported file")
                    result[name] = archive.read(member)
            manifest = json.loads(result.pop("manifest.json"))
            if manifest.get("format") != 1:
                raise BackupError("Unsupported backup version")
            self._validate(result)
        except (KeyError, ValueError, TypeError, AttributeError, zipfile.BadZipFile, RuntimeError) as exc:
            if isinstance(exc, BackupError):
                raise
            raise BackupError("Backup contents are invalid") from None
        return result

    @staticmethod
    def _validate(files: dict[str, bytes]) -> None:
        for name, payload in files.items():
            if name.startswith("media/"):
                if not payload:
                    raise BackupError("Backup contains an empty audio file")
                continue
            if len(payload) > 2 * 1024 * 1024:
                raise BackupError("Settings file is too large")
            value = json.loads(payload)
            if not isinstance(value, dict):
                raise BackupError("Settings must be objects")
            model = {"operation-settings.json": OperationSettings, "provider-settings.json": ProviderSettings}.get(name)
            if model:
                if set(value) - model.model_fields.keys():
                    raise BackupError("Settings contain unsupported fields")
                try:
                    model.model_validate(value)
                except ValueError:
                    raise BackupError("Invalid installation or voice settings") from None
            elif name == "credentials.json":
                pin = value.get("speaker_pin")
                if pin is not None and (not isinstance(pin, str) or not 4 <= len(pin) <= 16 or not pin.isascii() or not pin.isdecimal()):
                    raise BackupError("Invalid speaker pairing PIN in backup")
                if set(value) - {"groq_api_key", "elevenlabs_api_key", "speaker_pin"} or any(not isinstance(v, str) or len(v) > 4096 for v in value.values()):
                    raise BackupError("Invalid credential settings")
            elif name == "nag-media.json":
                if set(value) != {"serials"} or not isinstance(value["serials"], list) or len(value["serials"]) > 65536 or any(type(v) is not int or not 0 <= v <= 65535 for v in value["serials"]):
                    raise BackupError("Invalid lure assignments")
            elif name == "pi-media.json":
                if not isinstance(value.get("files"), dict) or not isinstance(value.get("quota_bytes"), int) or not 1024**3 <= value["quota_bytes"] <= 1000 * 1024**3:
                    raise BackupError("Invalid media settings")
                for filename, entry in value["files"].items():
                    if filename != Path(filename).name or "\\" in filename or filename.startswith(".") or Path(filename).suffix.lower() not in PiMediaLibrary.ALLOWED_SUFFIXES or not isinstance(entry, dict):
                        raise BackupError("Invalid media metadata")
                    # The library's normal editor validates the same preset fields.
                    if not isinstance(entry.get("display_name", filename), str) or len(entry.get("display_name", filename)) > 160:
                        raise BackupError("Invalid media name")
                    if not 0 <= int(entry.get("action", 255)) <= 255 or entry.get("movement_activity", "normal") not in {"low", "normal", "high"}:
                        raise BackupError("Invalid media movement")
                    lights = entry.get("lights", [])
                    if not isinstance(lights, list) or len(lights) > 2:
                        raise BackupError("Invalid media lights")
                    for light in lights:
                        if not isinstance(light, dict) or any(not 0 <= int(light.get(field, 0)) <= 255 for field in ("r", "g", "b", "brightness")):
                            raise BackupError("Invalid media lights")
                    if not 1 <= int(entry.get("eye", 1)) <= 18:
                        raise BackupError("Invalid media eye preset")

    def restore(self, files: dict[str, bytes], password: str, overrides: dict[str, bytes] | None = None) -> str:
        try:
            self._validate(files)
        except (ValueError, TypeError, KeyError):
            raise BackupError("Invalid backup settings") from None
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if self.data_dir.is_symlink():
            raise BackupError("Restore refuses a linked data directory")
        if shutil.disk_usage(self.data_dir).free < 10 * 1024**3 + sum(map(len, files.values())) * 3:
            raise BackupError("Not enough free space to restore safely")
        for name in files:
            target = self.data_dir / name
            if target.is_symlink() or target.parent.is_symlink():
                raise BackupError("Restore refuses linked files")
        # Media is never silently overwritten: only byte-identical existing files are accepted.
        for name, payload in files.items():
            target = self.data_dir / name
            if name.startswith("media/") and target.exists() and target.read_bytes() != payload:
                raise BackupError("An audio filename already exists with different contents; rename it before restoring")
        recovery = self.create(password, include_media=False, overrides=overrides)
        recovery_name = "recovery-" + os.urandom(12).hex() + ".usabackup"
        recovery_dir = self.data_dir / "backups"
        if recovery_dir.is_symlink():
            raise BackupError("Recovery directory must not be linked")
        recovery_dir.mkdir(mode=0o700, exist_ok=True)
        recovery_path = recovery_dir / recovery_name
        recovery_path.touch(mode=0o600, exist_ok=False)
        recovery_path.write_bytes(recovery)
        originals = {name: (self.data_dir / name).read_bytes() if (self.data_dir / name).exists() else None for name in files}
        with tempfile.TemporaryDirectory(prefix=".restore-", dir=self.data_dir) as staging:
            for index, (name, payload) in enumerate(files.items()):
                staged = Path(staging) / str(index)
                staged.write_bytes(payload); staged.chmod(0o600)
            applied = []
            try:
                for index, name in enumerate(files):
                    target = self.data_dir / name
                    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    os.replace(Path(staging) / str(index), target)
                    applied.append(name)
            except OSError:
                for name in reversed(applied):
                    target = self.data_dir / name
                    if originals[name] is None:
                        target.unlink(missing_ok=True)
                    else:
                        target.write_bytes(originals[name]); target.chmod(0o600)
                raise BackupError("Restore failed; previous files were recovered") from None
        return recovery_name
