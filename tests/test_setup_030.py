import json
import struct

import pytest
from fastapi.testclient import TestClient
from skelly_ai.api import create_app
from skelly_ai.config import Settings
from skelly_ai.fpp_sync import decode_discovery
from skelly_ai.backups import BackupManager, BackupError


def ping():
    payload=bytearray(294)
    payload[:3]=bytes((3,0,10))
    payload[7]=6
    payload[12:16]=b'Main'
    return struct.pack('<4sBH',b'FPPD',4,len(payload))+payload


def test_native_discovery_validates_replies():
    assert decode_discovery(ping(),'10.10.10.19') == {'hostname':'Main','address':'10.10.10.19','version':'','sending_sync':True}
    for data in (b'',ping()[:-1],b'EVIL'+ping()[4:]):
        assert decode_discovery(data,'10.10.10.19') is None
    assert decode_discovery(ping(),'127.0.0.1') is None
    request=bytearray(ping());request[8]=1
    assert decode_discovery(request,'10.10.10.19') is None


def test_setup_progress_persists_and_rejects_invalid_steps(tmp_path):
    app=create_app(Settings(data_dir=tmp_path,simulation=True))
    headers={'X-USA-Interactive-Auth':'1'}
    with TestClient(app) as c:
        assert c.post('/api/onboarding/progress',json={'step':2},headers=headers).status_code==200
        assert c.get('/api/onboarding/status').json()['wizard_step']==2
        for step in (-1,7,True,'2'):
            assert c.post('/api/onboarding/progress',json={'step':step},headers=headers).status_code==422
        assert c.post('/api/onboarding/progress',json={'step':2,'complete':True},headers=headers).status_code==422
        assert c.post('/api/onboarding/progress',json={'step':6,'complete':True},headers=headers).status_code==200
    assert json.loads((tmp_path/'onboarding.json').read_text())['wizard_complete'] is True


def test_fpp_backup_roundtrip_and_unsafe_links(tmp_path):
    (tmp_path/'fpp-settings.json').write_text(json.dumps({'enabled':True,'master_ip':'10.10.10.19','play_audio':True,'override_ai':True}))
    mapping={'Song.mp3':{'file':'jaw.wav','track':'Lead','source':'sequence'}}
    (tmp_path/'fpp-sequence-map.json').write_text(json.dumps(mapping))
    manager=BackupManager(tmp_path)
    files=manager.inspect(manager.create('test-backup-password'), 'test-backup-password')
    assert json.loads(files['fpp-sequence-map.json'])==mapping
    assert 'fpp-settings.json' in files
    mapping['Song.mp3']['file']='../escape.wav'
    with pytest.raises(ValueError):
        manager._validate({'fpp-sequence-map.json':json.dumps(mapping).encode()})
