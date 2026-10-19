"""Persistent Raspberry Pi media library with quota and disk-safety enforcement."""

from __future__ import annotations

import json
import shutil
from pathlib import Path


GIB = 1024 ** 3


class PiMediaError(RuntimeError):
    pass


class PiMediaLibrary:
    DEFAULT_QUOTA_BYTES = 3 * GIB
    RESERVE_BYTES = 10 * GIB
    MAX_FILE_BYTES = 512 * 1024 * 1024
    ALLOWED_SUFFIXES = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac"}

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.media_dir = self.data_dir / "media"
        self.state_path = self.data_dir / "pi-media.json"

    @staticmethod
    def _default_light() -> dict[str, object]:
        return {
            "effect_mode": 1,
            "brightness": 255,
            "r": 255,
            "g": 0,
            "b": 0,
            "cycle": False,
        }

    @classmethod
    def _default_entry(cls, name: str, size: int) -> dict[str, object]:
        return {
            "name": name,
            "size": int(size),
            "enabled": True,
            "action": 255,
            "eye": 1,
            "lights": [cls._default_light(), cls._default_light()],
            "jaw_sync": True,
            "nag_response": False,
        }

    def _ensure_media_dir(self) -> None:
        self.media_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

    def _load(self) -> dict[str, object]:
        if not self.state_path.exists():
            return {"quota_bytes": self.DEFAULT_QUOTA_BYTES, "files": {}}
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            payload = {}
        quota = int(payload.get("quota_bytes") or self.DEFAULT_QUOTA_BYTES)
        files = payload.get("files") if isinstance(payload.get("files"), dict) else {}
        return {"quota_bytes": max(GIB, quota), "files": files}

    def _save(self, payload: dict[str, object]) -> None:
        self.data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, separators=(",", ":"), sort_keys=True),
            encoding="utf-8",
        )
        temporary.chmod(0o600)
        temporary.replace(self.state_path)
        self.state_path.chmod(0o600)

    def _clean_name(self, name: str) -> str:
        clean = Path(name).name.strip()
        if not clean or clean != name.strip() or len(clean) > 160:
            raise PiMediaError("Choose a valid audio filename")
        if Path(clean).suffix.casefold() not in self.ALLOWED_SUFFIXES:
            raise PiMediaError("Pi Media supports MP3, WAV, OGG, FLAC, M4A, and AAC audio")
        return clean

    def _usage_bytes(self) -> int:
        self._ensure_media_dir()
        total = 0
        for path in self.media_dir.iterdir():
            if path.is_file() and not path.name.startswith("."):
                try:
                    total += path.stat().st_size
                except OSError:
                    pass
        return total

    def _disk_free(self) -> int:
        self._ensure_media_dir()
        return int(shutil.disk_usage(self.media_dir).free)

    def _files(self) -> list[dict[str, object]]:
        self._ensure_media_dir()
        state = self._load()
        saved = state["files"]
        changed = False
        result: list[dict[str, object]] = []
        present: set[str] = set()
        for path in sorted(self.media_dir.iterdir(), key=lambda item: item.name.casefold()):
            if not path.is_file() or path.name.startswith("."):
                continue
            present.add(path.name)
            entry = dict(saved.get(path.name) or self._default_entry(path.name, path.stat().st_size))
            entry["name"] = path.name
            entry["size"] = path.stat().st_size
            saved[path.name] = entry
            result.append(entry)
        for stale in set(saved) - present:
            saved.pop(stale, None)
            changed = True
        if changed:
            self._save(state)
        return result

    def status(self, *, playing_name: str | None = None) -> dict[str, object]:
        state = self._load()
        usage = self._usage_bytes()
        free = self._disk_free()
        quota = int(state["quota_bytes"])
        quota_remaining = max(0, quota - usage)
        disk_safe_remaining = max(0, free - self.RESERVE_BYTES)
        return {
            "available": True,
            "files": self._files(),
            "file_count": len(self._files()),
            "playing_name": playing_name,
            "usage_bytes": usage,
            "quota_bytes": quota,
            "quota_remaining_bytes": quota_remaining,
            "filesystem_free_bytes": free,
            "reserve_bytes": self.RESERVE_BYTES,
            "safe_upload_bytes": min(quota_remaining, disk_safe_remaining),
            "max_safe_quota_bytes": usage + disk_safe_remaining,
            "max_file_bytes": self.MAX_FILE_BYTES,
        }

    def get(self, name: str) -> dict[str, object]:
        clean = self._clean_name(name)
        for entry in self._files():
            if entry["name"] == clean:
                return entry
        raise PiMediaError("That Pi media file was not found")

    def path_for(self, name: str) -> Path:
        entry = self.get(name)
        return self.media_dir / str(entry["name"])

    def add(self, name: str, data: bytes) -> dict[str, object]:
        self._ensure_media_dir()
        clean = self._clean_name(name)
        if not data:
            raise PiMediaError("The audio file is empty")
        if len(data) > self.MAX_FILE_BYTES:
            raise PiMediaError("A single Pi media file may not exceed 512 MB")
        destination = self.media_dir / clean
        if destination.exists():
            raise PiMediaError("A Pi media file with that name already exists")
        status = self.status()
        if len(data) > int(status["quota_remaining_bytes"]):
            raise PiMediaError("This upload would exceed the Pi Media quota")
        if len(data) > max(0, int(status["filesystem_free_bytes"]) - self.RESERVE_BYTES):
            raise PiMediaError("This upload would use the 10 GB filesystem safety reserve")
        temporary = self.media_dir / f".{clean}.upload"
        try:
            temporary.write_bytes(data)
            temporary.chmod(0o600)
            temporary.replace(destination)
            destination.chmod(0o600)
        finally:
            temporary.unlink(missing_ok=True)
        state = self._load()
        state["files"][clean] = self._default_entry(clean, len(data))
        self._save(state)
        return self.get(clean)

    def delete(self, name: str) -> None:
        self._ensure_media_dir()
        clean = self._clean_name(name)
        path = self.media_dir / clean
        if not path.exists():
            raise PiMediaError("That Pi media file was not found")
        path.unlink()
        state = self._load()
        state["files"].pop(clean, None)
        self._save(state)

    def update(self, name: str, values: dict[str, object]) -> dict[str, object]:
        clean = self._clean_name(name)
        current = self.get(clean)
        current.update(values)
        current["name"] = clean
        state = self._load()
        state["files"][clean] = current
        self._save(state)
        return current

    def set_quota_gb(self, quota_gb: int) -> dict[str, object]:
        quota = int(quota_gb) * GIB
        usage = self._usage_bytes()
        if quota < usage:
            raise PiMediaError("The Pi Media limit cannot be smaller than current media usage")
        free = self._disk_free()
        max_safe = usage + max(0, free - self.RESERVE_BYTES)
        if quota > max_safe:
            raise PiMediaError("That limit would use the 10 GB filesystem safety reserve")
        state = self._load()
        state["quota_bytes"] = quota
        self._save(state)
        return self.status()
