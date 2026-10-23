import io
import os
import time
import wave

import pytest

from skelly_ai.pi_media import GIB, PiMediaLibrary
from skelly_ai.tts_previews import TTSPreviewError, TTSPreviewManager


def sample_wav():
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(22050)
        wav.writeframes(b"\x00\x00" * 1000)
    return output.getvalue()


def test_preview_creation_and_retrieval(tmp_path):
    manager = TTSPreviewManager(tmp_path)
    audio = sample_wav()

    preview_id = manager.create(audio)

    assert len(preview_id) == 32
    assert manager.get(preview_id).read_bytes() == audio
    assert manager.get(preview_id).stat().st_mode & 0o777 == 0o600


def test_preview_rejects_invalid_audio(tmp_path):
    manager = TTSPreviewManager(tmp_path)

    with pytest.raises(TTSPreviewError):
        manager.create(b"not a WAV file")


def test_preview_expires(tmp_path):
    manager = TTSPreviewManager(tmp_path)
    preview_id = manager.create(sample_wav())
    path = manager.get(preview_id)

    expired = time.time() - manager.TTL_SECONDS - 10
    os.utime(path, (expired, expired))

    with pytest.raises(TTSPreviewError, match="expired"):
        manager.get(preview_id)

    assert not path.exists()


@pytest.mark.asyncio
async def test_preview_save_to_pi_media(tmp_path, monkeypatch):
    manager = TTSPreviewManager(tmp_path)
    library = PiMediaLibrary(tmp_path)
    monkeypatch.setattr(library, "_disk_free", lambda: 20 * GIB)

    preview_id = manager.create(sample_wav())
    saved = await manager.save(
        preview_id,
        "welcome.wav",
        "Welcome Visitors",
        library,
    )

    assert saved["name"] == "welcome.wav"
    assert saved["display_name"] == "Welcome Visitors"
    assert saved["id"]
    assert (library.media_dir / "welcome.wav").is_file()

    with pytest.raises(TTSPreviewError):
        manager.get(preview_id)


@pytest.mark.asyncio
async def test_preview_save_duplicate_preserves_preview(tmp_path, monkeypatch):
    manager = TTSPreviewManager(tmp_path)
    library = PiMediaLibrary(tmp_path)
    monkeypatch.setattr(library, "_disk_free", lambda: 20 * GIB)

    library.add("existing.wav", sample_wav())
    preview_id = manager.create(sample_wav())

    with pytest.raises(Exception, match="already exists"):
        await manager.save(preview_id, "existing.wav", "Duplicate", library)

    assert manager.get(preview_id).exists()
    assert library.status()["file_count"] == 1


@pytest.mark.asyncio
async def test_preview_rejects_invalid_media_name(tmp_path, monkeypatch):
    manager = TTSPreviewManager(tmp_path)
    library = PiMediaLibrary(tmp_path)
    monkeypatch.setattr(library, "_disk_free", lambda: 20 * GIB)

    preview_id = manager.create(sample_wav())

    for name in ("", "   ", "X" * 121):
        with pytest.raises(TTSPreviewError, match="Media Name"):
            await manager.save(
                preview_id,
                "welcome.wav",
                name,
                library,
            )

    assert library.status()["file_count"] == 0
    assert manager.get(preview_id).exists()


@pytest.mark.asyncio
async def test_preview_cannot_be_saved_twice(tmp_path, monkeypatch):
    manager = TTSPreviewManager(tmp_path)
    library = PiMediaLibrary(tmp_path)
    monkeypatch.setattr(library, "_disk_free", lambda: 20 * GIB)

    preview_id = manager.create(sample_wav())

    first = await manager.save(
        preview_id,
        "welcome.wav",
        "Welcome Visitors",
        library,
    )

    assert first["display_name"] == "Welcome Visitors"

    with pytest.raises(TTSPreviewError, match="expired or not found"):
        await manager.save(
            preview_id,
            "welcome-copy.wav",
            "Another Welcome",
            library,
        )

    assert library.status()["file_count"] == 1
    assert not (library.media_dir / "welcome-copy.wav").exists()


@pytest.mark.asyncio
async def test_concurrent_saves_do_not_duplicate_preview(tmp_path, monkeypatch):
    import asyncio

    manager = TTSPreviewManager(tmp_path)
    library = PiMediaLibrary(tmp_path)
    monkeypatch.setattr(library, "_disk_free", lambda: 20 * GIB)

    preview_id = manager.create(sample_wav())

    results = await asyncio.gather(
        manager.save(
            preview_id,
            "first.wav",
            "First Save",
            library,
        ),
        manager.save(
            preview_id,
            "second.wav",
            "Second Save",
            library,
        ),
        return_exceptions=True,
    )

    successes = [result for result in results if isinstance(result, dict)]
    failures = [result for result in results if isinstance(result, Exception)]

    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], TTSPreviewError)
    assert library.status()["file_count"] == 1


@pytest.mark.parametrize("limit", ["count", "bytes", "disk"])
def test_aggregate_preview_limits(tmp_path, monkeypatch, limit):
    from collections import namedtuple
    import skelly_ai.tts_previews as module
    manager = TTSPreviewManager(tmp_path)
    audio = sample_wav()
    preview_id = manager.create(audio)
    if limit == "count":
        monkeypatch.setattr(manager, "MAX_PREVIEWS", 1)
    elif limit == "bytes":
        monkeypatch.setattr(manager, "MAX_TOTAL_BYTES", len(audio) * 2 - 1)
    else:
        Usage = namedtuple("Usage", "total used free")
        monkeypatch.setattr(module.shutil, "disk_usage", lambda _: Usage(0, 0, manager.MIN_FREE_BYTES + len(audio) - 1))
    with pytest.raises(TTSPreviewError):
        manager.create(audio)
    assert manager.get(preview_id).read_bytes() == audio
    assert len(list(manager.directory.glob("*.wav"))) == 1


def test_expired_previews_release_quota(tmp_path, monkeypatch):
    manager = TTSPreviewManager(tmp_path)
    monkeypatch.setattr(manager, "MAX_PREVIEWS", 1)
    old = manager.get(manager.create(sample_wav()))
    expired = time.time() - manager.TTL_SECONDS - 1
    os.utime(old, (expired, expired))
    assert manager.get(manager.create(sample_wav())).exists()
    assert not old.exists()
