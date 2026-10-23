from pathlib import Path

import pytest

from skelly_ai.pi_media import GIB, PiMediaError, PiMediaLibrary


def test_pi_media_defaults_to_three_gib_and_ten_gib_reserve(tmp_path: Path) -> None:
    library = PiMediaLibrary(tmp_path)
    status = library.status()
    assert status["quota_bytes"] == 3 * GIB
    assert status["reserve_bytes"] == 10 * GIB
    assert status["file_count"] == 0


def test_pi_media_add_edit_delete(tmp_path: Path, monkeypatch) -> None:
    library = PiMediaLibrary(tmp_path)
    monkeypatch.setattr(library, "_disk_free", lambda: 20 * GIB)
    added = library.add("hello.mp3", b"ID3" + b"x" * 200)
    assert added["name"] == "hello.mp3"
    assert added["jaw_sync"] is True
    assert added["movement_activity"] == "normal"

    updated = library.update(
        "hello.mp3",
        {"action": 3, "eye": 4, "jaw_sync": False, "movement_activity": "high", "nag_response": True},
    )
    assert updated["action"] == 3
    assert updated["eye"] == 4
    assert updated["jaw_sync"] is False
    assert updated["movement_activity"] == "high"
    assert updated["nag_response"] is True

    library.delete("hello.mp3")
    assert library.status()["file_count"] == 0


def test_pi_media_rejects_duplicate_and_unsupported_files(tmp_path: Path, monkeypatch) -> None:
    library = PiMediaLibrary(tmp_path)
    monkeypatch.setattr(library, "_disk_free", lambda: 20 * GIB)
    library.add("hello.wav", b"RIFF" + b"x" * 200)
    with pytest.raises(PiMediaError, match="already exists"):
        library.add("hello.wav", b"RIFF" + b"y" * 200)
    with pytest.raises(PiMediaError, match="supports"):
        library.add("hello.exe", b"x")


@pytest.mark.asyncio
async def test_stream_upload_success(tmp_path, monkeypatch):
    library = PiMediaLibrary(tmp_path)
    monkeypatch.setattr(library, "_disk_free", lambda: 20 * GIB)

    async def chunks():
        yield b"ID3"
        yield b"x" * 1024

    result = await library.add_stream("stream.mp3", chunks())

    assert result["size"] == 1027
    assert (library.media_dir / "stream.mp3").read_bytes() == b"ID3" + b"x" * 1024
    assert library.status()["file_count"] == 1


@pytest.mark.asyncio
async def test_stream_upload_rejects_oversized_file(tmp_path, monkeypatch):
    library = PiMediaLibrary(tmp_path)
    monkeypatch.setattr(library, "_disk_free", lambda: 20 * GIB)
    monkeypatch.setattr(library, "MAX_FILE_BYTES", 100)

    async def chunks():
        yield b"x" * 60
        yield b"x" * 60

    with pytest.raises(PiMediaError, match="512 MB"):
        await library.add_stream("large.mp3", chunks())

    assert not (library.media_dir / "large.mp3").exists()
    assert not list(library.media_dir.glob(".*.upload"))


@pytest.mark.asyncio
async def test_stream_upload_cleans_up_interruption(tmp_path, monkeypatch):
    library = PiMediaLibrary(tmp_path)
    monkeypatch.setattr(library, "_disk_free", lambda: 20 * GIB)

    async def chunks():
        yield b"ID3"
        raise ConnectionError("Upload interrupted")

    with pytest.raises(ConnectionError, match="interrupted"):
        await library.add_stream("interrupted.mp3", chunks())

    assert not (library.media_dir / "interrupted.mp3").exists()
    assert not list(library.media_dir.glob(".*.upload"))


@pytest.mark.asyncio
async def test_stream_upload_rejects_duplicate(tmp_path, monkeypatch):
    library = PiMediaLibrary(tmp_path)
    monkeypatch.setattr(library, "_disk_free", lambda: 20 * GIB)
    library.add("existing.mp3", b"ID3")

    async def chunks():
        yield b"another file"

    with pytest.raises(PiMediaError, match="already exists"):
        await library.add_stream("existing.mp3", chunks())

    assert (library.media_dir / "existing.mp3").read_bytes() == b"ID3"


@pytest.mark.asyncio
async def test_stream_upload_concurrent_duplicate(tmp_path, monkeypatch):
    import asyncio

    library = PiMediaLibrary(tmp_path)
    monkeypatch.setattr(library, "_disk_free", lambda: 20 * GIB)

    async def chunks():
        yield b"ID3"
        await asyncio.sleep(0)
        yield b"x" * 100

    results = await asyncio.gather(
        library.add_stream("same.mp3", chunks()),
        library.add_stream("same.mp3", chunks()),
        return_exceptions=True,
    )

    assert sum(isinstance(result, dict) for result in results) == 1
    assert sum(isinstance(result, PiMediaError) for result in results) == 1
    assert library.status()["file_count"] == 1


@pytest.mark.asyncio
async def test_stream_upload_metadata_failure(tmp_path, monkeypatch):
    library = PiMediaLibrary(tmp_path)
    monkeypatch.setattr(library, "_disk_free", lambda: 20 * GIB)

    def fail_save(state):
        raise OSError("Simulated metadata failure")

    monkeypatch.setattr(library, "_save", fail_save)

    async def chunks():
        yield b"ID3"
        yield b"x" * 100

    with pytest.raises(OSError, match="metadata failure"):
        await library.add_stream("failure.mp3", chunks())

    assert not (library.media_dir / "failure.mp3").exists()
    assert not list(library.media_dir.glob(".*.upload"))


@pytest.mark.asyncio
async def test_stream_upload_concurrent_quota(tmp_path, monkeypatch):
    import asyncio

    library = PiMediaLibrary(tmp_path)
    monkeypatch.setattr(library, "_disk_free", lambda: 20 * GIB)

    # Simulate storage with only 150 bytes of remaining quota.
    original_status = library.status

    def limited_status(*args, **kwargs):
        status = original_status(*args, **kwargs)
        status["quota_remaining_bytes"] = max(
            0, 150 - int(status["usage_bytes"])
        )
        return status

    monkeypatch.setattr(library, "status", limited_status)

    async def chunks():
        yield b"x" * 100
        await asyncio.sleep(0)

    results = await asyncio.gather(
        library.add_stream("first.mp3", chunks()),
        library.add_stream("second.mp3", chunks()),
        return_exceptions=True,
    )

    assert sum(isinstance(result, dict) for result in results) == 1
    assert sum(isinstance(result, PiMediaError) for result in results) == 1
    assert library.status()["file_count"] == 1
    assert library.status()["usage_bytes"] == 100


@pytest.mark.asyncio
async def test_stream_upload_cancellation_cleanup(tmp_path, monkeypatch):
    import asyncio

    library = PiMediaLibrary(tmp_path)
    monkeypatch.setattr(library, "_disk_free", lambda: 20 * GIB)

    started = asyncio.Event()

    async def chunks():
        yield b"ID3"
        started.set()
        await asyncio.sleep(3600)

    task = asyncio.create_task(
        library.add_stream("cancelled.mp3", chunks())
    )

    await asyncio.wait_for(started.wait(), timeout=5)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert not (library.media_dir / "cancelled.mp3").exists()
    assert not list(library.media_dir.glob(".*.upload"))
    assert library.status()["file_count"] == 0


def test_lure_assignment_preserves_other_preset_settings(tmp_path, monkeypatch):
    library = PiMediaLibrary(tmp_path)
    monkeypatch.setattr(library, "_disk_free", lambda: 20 * GIB)

    library.add("lure-test.mp3", b"ID3" + b"x" * 100)

    original_lights = [
        {"effect_mode": 2, "brightness": 150,
         "r": 255, "g": 20, "b": 0, "cycle": False},
        {"effect_mode": 3, "brightness": 200,
         "r": 0, "g": 80, "b": 255, "cycle": True},
    ]

    library.update("lure-test.mp3", {
        "action": 5,
        "eye": 7,
        "jaw_sync": False,
        "movement_activity": "high",
        "lights": original_lights,
        "nag_response": False,
    })

    updated = library.update("lure-test.mp3", {
        "nag_response": True
    })

    assert updated["nag_response"] is True
    assert updated["action"] == 5
    assert updated["eye"] == 7
    assert updated["jaw_sync"] is False
    assert updated["movement_activity"] == "high"
    assert updated["lights"] == original_lights

    # Confirm settings survive a fresh library instance.
    reloaded = PiMediaLibrary(tmp_path).get("lure-test.mp3")
    assert reloaded["nag_response"] is True
    assert reloaded["lights"] == original_lights
    assert reloaded["action"] == 5
    assert reloaded["eye"] == 7
    assert reloaded["jaw_sync"] is False


def test_pi_media_display_name_and_stable_id(tmp_path, monkeypatch):
    library = PiMediaLibrary(tmp_path)
    monkeypatch.setattr(library, "_disk_free", lambda: 20 * GIB)

    original = library.add("scary_laugh.mp3", b"ID3test")

    clip_id = original["id"]
    assert clip_id
    assert original["display_name"] == "scary_laugh.mp3"

    updated = library.update(
        "scary_laugh.mp3",
        {"display_name": "Evil Laugh"},
    )

    assert updated["display_name"] == "Evil Laugh"
    assert updated["name"] == "scary_laugh.mp3"
    assert updated["id"] == clip_id

    reloaded = PiMediaLibrary(tmp_path).get("scary_laugh.mp3")
    assert reloaded["display_name"] == "Evil Laugh"
    assert reloaded["id"] == clip_id
    assert reloaded["name"] == "scary_laugh.mp3"


def test_pi_media_migrates_legacy_metadata(tmp_path, monkeypatch):
    import json

    library = PiMediaLibrary(tmp_path)
    monkeypatch.setattr(library, "_disk_free", lambda: 20 * GIB)

    library.media_dir.mkdir(parents=True)
    (library.media_dir / "old_clip.mp3").write_bytes(b"ID3old")

    legacy = {
        "quota_bytes": 3 * GIB,
        "files": {
            "old_clip.mp3": {
                "name": "old_clip.mp3",
                "size": 6,
                "action": 5,
                "eye": 7,
                "jaw_sync": False,
                "nag_response": True,
            }
        },
    }

    library.state_path.write_text(json.dumps(legacy))

    migrated = library.get("old_clip.mp3")
    assert migrated["id"]
    assert migrated["display_name"] == "old_clip.mp3"
    assert migrated["action"] == 5
    assert migrated["eye"] == 7
    assert migrated["jaw_sync"] is False
    assert migrated["nag_response"] is True

    # A second library instance must see the same permanent ID.
    second = PiMediaLibrary(tmp_path).get("old_clip.mp3")
    assert second["id"] == migrated["id"]


def test_pi_media_rejects_invalid_display_name(tmp_path, monkeypatch):
    library = PiMediaLibrary(tmp_path)
    monkeypatch.setattr(library, "_disk_free", lambda: 20 * GIB)

    library.add("test.mp3", b"ID3")

    with pytest.raises(PiMediaError, match="Media Name"):
        library.update("test.mp3", {"display_name": "   "})

    with pytest.raises(PiMediaError, match="Media Name"):
        library.update("test.mp3", {"display_name": "x" * 121})


@pytest.mark.asyncio
async def test_stream_upload_with_display_name(tmp_path, monkeypatch):
    library = PiMediaLibrary(tmp_path)
    monkeypatch.setattr(library, "_disk_free", lambda: 20 * GIB)

    async def audio_chunks():
        yield b"RIFF"
        yield b"generated speech"

    saved = await library.add_stream(
        "welcome.wav",
        audio_chunks(),
        display_name="Welcome Visitors",
    )

    assert saved["name"] == "welcome.wav"
    assert saved["display_name"] == "Welcome Visitors"
    assert saved["id"]

    loaded = library.get("welcome.wav")
    assert loaded["id"] == saved["id"]
    assert loaded["display_name"] == "Welcome Visitors"

    with pytest.raises(PiMediaError, match="already exists"):
        await library.add_stream(
            "welcome.wav",
            audio_chunks(),
            display_name="Duplicate",
        )

    assert library.get("welcome.wav")["id"] == saved["id"]


def test_synchronous_upload_collision_race_never_overwrites(tmp_path, monkeypatch):
    import os
    library = PiMediaLibrary(tmp_path)
    monkeypatch.setattr(library, '_disk_free', lambda: 20 * GIB)
    real_link = os.link
    def raced_link(source, destination):
        destination.write_bytes(b'existing-race-winner')
        real_link(source, destination)
    monkeypatch.setattr('skelly_ai.pi_media.os.link', raced_link)
    with pytest.raises(PiMediaError, match='already exists'):
        library.add('race.wav', b'RIFFreplacement')
    assert (library.media_dir / 'race.wav').read_bytes() == b'existing-race-winner'
    assert not list(library.media_dir.glob('.*.upload'))
