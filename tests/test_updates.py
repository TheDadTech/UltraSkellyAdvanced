from __future__ import annotations

import hashlib
import subprocess
import zipfile
from pathlib import Path

import pytest

from skelly_ai.updates import UpdateError, UpdateManager


def make_release(path: Path, version: str = "0.25.1") -> Path:
    archive = path / "release.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(
            "pyproject.toml",
            f'[project]\nname = "skelly-ai"\nversion = "{version}"\n',
        )
        bundle.writestr("deploy/bootstrap-pi.sh", "#!/usr/bin/env bash\n")
        bundle.writestr("src/skelly_ai/__init__.py", "")
    return archive


def test_release_archive_is_extracted_and_version_checked(tmp_path: Path) -> None:
    manager = UpdateManager(tmp_path / "data", tmp_path / "helper")
    archive = make_release(tmp_path)
    source = tmp_path / "source"

    project = manager._extract_and_validate(archive, source, "0.25.1")

    assert project == source.resolve()
    assert (project / "deploy" / "bootstrap-pi.sh").is_file()


def test_release_archive_rejects_traversal(tmp_path: Path) -> None:
    manager = UpdateManager(tmp_path / "data", tmp_path / "helper")
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("../outside", "bad")

    with pytest.raises(UpdateError, match="unsafe file path"):
        manager._extract_and_validate(archive, tmp_path / "source", "0.25.1")


def test_update_status_survives_service_restart(tmp_path: Path) -> None:
    manager = UpdateManager(tmp_path, tmp_path / "helper")
    manager._write_status("installing", "Installing", "0.25.1")

    assert manager.status() == {
        "state": "installing",
        "message": "Installing",
        "version": "0.25.1",
    }


@pytest.mark.asyncio
async def test_verified_release_is_staged_before_helper_starts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = make_release(tmp_path)
    content = archive.read_bytes()

    class Response:
        def raise_for_status(self) -> None:
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def aiter_bytes(self):
            yield content

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def stream(self, *_args, **_kwargs):
            return Response()

    helper_calls: list[list[str]] = []

    def fake_run(args, **_kwargs):
        helper_calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr("skelly_ai.updates.httpx.AsyncClient", lambda **_kwargs: Client())
    monkeypatch.setattr("skelly_ai.updates.subprocess.run", fake_run)
    manager = UpdateManager(tmp_path / "data", tmp_path / "helper")

    status = await manager.stage_and_start(
        {
            "version": "0.25.1",
            "package_url": "https://example.test/usa.zip",
            "sha256": hashlib.sha256(content).hexdigest(),
        },
        current_version="0.25.0",
    )

    assert status["state"] == "staged"
    assert helper_calls[0][3:5] == ["update-install", "0.25.1"]


@pytest.mark.asyncio
async def test_bad_checksum_never_starts_helper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = make_release(tmp_path)
    content = archive.read_bytes()

    class Response:
        def raise_for_status(self) -> None:
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def aiter_bytes(self):
            yield content

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def stream(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr("skelly_ai.updates.httpx.AsyncClient", lambda **_kwargs: Client())
    manager = UpdateManager(tmp_path / "data", tmp_path / "helper")

    with pytest.raises(UpdateError, match="checksum did not match"):
        await manager.stage_and_start(
            {
                "version": "0.25.1",
                "package_url": "https://example.test/usa.zip",
                "sha256": "0" * 64,
            },
            current_version="0.25.0",
        )
