import json
import stat
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from skelly_ai.api import create_app
from skelly_ai.config import Settings
from skelly_ai.credentials import CredentialStore
from skelly_ai.backups import BackupManager


def test_pin_persists_securely_and_preserves_cloud_credentials(tmp_path):
    store=CredentialStore(tmp_path)
    store.save_groq(SecretStr('synthetic-cloud-key'))
    store.save_speaker_pin('0579')
    store.save_elevenlabs(SecretStr('synthetic-voice-key'))
    saved=CredentialStore(tmp_path).load()
    assert saved.speaker_pin.get_secret_value()=='0579'
    assert saved.groq_api_key.get_secret_value()=='synthetic-cloud-key'
    assert saved.api_key.get_secret_value()=='synthetic-voice-key'
    assert stat.S_IMODE((tmp_path/'credentials.json').stat().st_mode)==0o600
    password='synthetic-backup-password'
    bundle=BackupManager(tmp_path).create(password)
    files=BackupManager(tmp_path).inspect(bundle,password)
    dest=tmp_path/'restored'
    BackupManager(dest).restore(files,password)
    assert CredentialStore(dest).load().speaker_pin.get_secret_value()=='0579'


@pytest.mark.parametrize('pin',['','123','12345678901234567','12\n34','１２３４',1234,None])
def test_invalid_pin_rejected_without_echo(tmp_path,pin):
    app=create_app(Settings(simulation=True,data_dir=tmp_path))
    with TestClient(app) as c:
        r=c.post('/api/audio/speaker-pin',json={'pin':pin})
        assert r.status_code==422
        assert r.json()=={'detail':'Use 4–16 digits for the speaker pairing PIN'}
        assert not (tmp_path/'credentials.json').exists()


def test_saved_pin_used_by_prepare_and_repair_after_restart(tmp_path,monkeypatch):
    app=create_app(Settings(simulation=True,data_dir=tmp_path,classic_audio_pin='1234'))
    with TestClient(app) as c:
        assert c.get('/api/audio/speaker-pin').json()=={'configured':False}
        assert c.post('/api/audio/speaker-pin',json={'pin':'0579'}).json()=={'configured':True}
    restarted=create_app(Settings(simulation=True,data_dir=tmp_path,classic_audio_pin='1234'))
    pins=[]
    audio=restarted.state.classic_audio
    original=audio.connect
    async def prepare(pin):
        pins.append(pin)
        return await original()
    async def repair(pin,**kwargs):
        pins.append(pin)
        return await original()
    monkeypatch.setattr(audio,'prepare',prepare)
    monkeypatch.setattr(audio,'repair',repair)
    with TestClient(restarted) as c:
        assert c.get('/api/audio/speaker-pin').json()=={'configured':True}
        assert c.post('/api/hardware/connect',json={}).status_code==200
        assert c.post('/api/audio/prepare-connect').status_code==200
        c.post('/api/audio/repair-speaker',json={'confirm':'repair-speaker'})
        assert pins==['0579','0579']
        assert '0579' not in c.get('/api/operation/status').text


def test_pin_save_rejects_cross_origin_and_does_not_connect(tmp_path,monkeypatch):
    app=create_app(Settings(simulation=True,data_dir=tmp_path))
    async def unexpected(*args,**kwargs):raise AssertionError('Save must not connect')
    monkeypatch.setattr(app.state.classic_audio,'connect',unexpected)
    with TestClient(app) as c:
        assert c.post('/api/audio/speaker-pin',json={'pin':'0579'},headers={'Origin':'https://untrusted.example'}).status_code==403
        assert c.post('/api/audio/speaker-pin',json={'pin':'0579'}).status_code==200
