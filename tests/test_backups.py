import io
import json
import os
import zipfile
from pathlib import Path

import pytest

from skelly_ai.backups import BackupManager, BackupError

PASSWORD = 'test-only-backup-password'


def test_encrypted_backup_round_trip_credentials_metadata_and_media(tmp_path):
    source = tmp_path / 'source'; source.mkdir()
    (source / 'credentials.json').write_text(json.dumps({'groq_api_key': 'test-secret-not-real', 'elevenlabs_api_key': ''}))
    (source / 'operation-settings.json').write_text('{"skelly_name":"Boney"}')
    (source / 'media').mkdir(); (source / 'media' / 'hello.wav').write_bytes(b'RIFFtest-audio')
    manager = BackupManager(source)
    encrypted = manager.create(PASSWORD, True)
    assert b'test-secret-not-real' not in encrypted
    assert b'Boney' not in encrypted
    files = manager.inspect(encrypted, PASSWORD)
    assert files['media/hello.wav'] == b'RIFFtest-audio'
    destination = tmp_path / 'restored'
    restored = BackupManager(destination)
    recovery = restored.restore(files, PASSWORD)
    assert (destination / 'credentials.json').read_bytes() == files['credentials.json']
    assert (destination / 'credentials.json').stat().st_mode & 0o777 == 0o600
    assert (destination / 'backups' / recovery).stat().st_mode & 0o777 == 0o600
    assert restored.inspect((destination / 'backups' / recovery).read_bytes(), PASSWORD) == {}


def test_wrong_password_and_tampering_rejected(tmp_path):
    manager = BackupManager(tmp_path)
    encrypted = manager.create(PASSWORD)
    with pytest.raises(BackupError, match='password or damaged'):
        manager.inspect(encrypted, 'wrong-password-test')
    with pytest.raises(BackupError):
        manager.inspect(encrypted[:-1] + bytes([encrypted[-1] ^ 1]), PASSWORD)
    with pytest.raises(BackupError):
        manager.create('short')


@pytest.mark.parametrize('name', ['../escape', '/etc/passwd', 'media/../escape', 'media/../../evil.wav', 'media\\evil.wav', 'unknown.json'])
def test_restore_rejects_unallowlisted_paths(tmp_path, name):
    manager = BackupManager(tmp_path)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as bundle:
        bundle.writestr('manifest.json', '{"format":1}')
        bundle.writestr(name, b'unsafe')
    with pytest.raises(BackupError):
        manager.inspect(manager.encrypt(stream.getvalue(), PASSWORD), PASSWORD)
    assert not (tmp_path.parent / 'escape').exists()


def test_restore_preserves_recovery_and_never_overwrites_different_media(tmp_path):
    (tmp_path / 'operation-settings.json').write_text('{"skelly_name":"Original"}')
    manager = BackupManager(tmp_path)
    recovery = manager.restore({'operation-settings.json': b'{"skelly_name":"Restored"}'}, PASSWORD)
    old = manager.inspect((tmp_path / 'backups' / recovery).read_bytes(), PASSWORD)
    assert json.loads(old['operation-settings.json'])['skelly_name'] == 'Original'
    (tmp_path / 'media').mkdir(); (tmp_path / 'media' / 'clip.wav').write_bytes(b'original')
    with pytest.raises(BackupError, match='different contents'):
        manager.restore({'media/clip.wav': b'replacement'}, PASSWORD)
    assert (tmp_path / 'media' / 'clip.wav').read_bytes() == b'original'


def test_restore_rejects_symlinks_and_malformed_settings(tmp_path):
    manager = BackupManager(tmp_path)
    target = tmp_path / 'outside'; target.write_text('unchanged')
    (tmp_path / 'credentials.json').symlink_to(target)
    with pytest.raises(BackupError):
        manager.restore({'credentials.json': b'{"groq_api_key":"test"}'}, PASSWORD)
    assert target.read_text() == 'unchanged'
    with pytest.raises(BackupError):
        manager.restore({'operation-settings.json': b'{"hardware_profile":"bad"}'}, PASSWORD)


def test_backup_expansion_limit(tmp_path, monkeypatch):
    manager = BackupManager(tmp_path)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr('manifest.json', '{"format":1}')
        bundle.writestr('media/huge.wav', b'x' * 4096)
    encrypted = manager.encrypt(stream.getvalue(), PASSWORD)
    monkeypatch.setattr(manager, 'MAX_BYTES', 2048)
    with pytest.raises(BackupError, match='too much data'):
        manager.inspect(encrypted, PASSWORD)


def test_metadata_only_restore_survives_until_audio_is_copied(tmp_path, monkeypatch):
    from skelly_ai.pi_media import PiMediaLibrary, GIB
    manager = BackupManager(tmp_path)
    entry = PiMediaLibrary._default_entry('later.wav', 100)
    entry['eye'] = 18
    manager.restore({'pi-media.json': json.dumps({'quota_bytes': 3 * GIB, 'files': {'later.wav': entry}}).encode()}, PASSWORD)
    library = PiMediaLibrary(tmp_path)
    monkeypatch.setattr(library, '_disk_free', lambda: 20 * GIB)
    assert library.status()['file_count'] == 0
    clip = library.add('later.wav', b'RIFF' + b'x' * 96)
    assert clip['id'] == entry['id'] and clip['eye'] == 18
