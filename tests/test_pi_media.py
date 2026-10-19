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

    updated = library.update(
        "hello.mp3",
        {"action": 3, "eye": 4, "jaw_sync": False, "nag_response": True},
    )
    assert updated["action"] == 3
    assert updated["eye"] == 4
    assert updated["jaw_sync"] is False
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
