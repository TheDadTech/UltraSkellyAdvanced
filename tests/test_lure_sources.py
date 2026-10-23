import json

import pytest
from fastapi.testclient import TestClient

from skelly_ai.api import create_app
from skelly_ai.config import Settings
from skelly_ai.operation_settings import OperationSettingsStore
from skelly_ai.pi_media import PiMediaLibrary


@pytest.mark.parametrize('mode', ['disabled', 'media', 'pi_media', 'ai'])
def test_lure_source_selection_persists(tmp_path, mode):
    with TestClient(create_app(Settings(data_dir=tmp_path, simulation=True))) as c:
        r = c.post('/api/operation/settings', json={'nag_mode':mode})
        assert r.status_code == 200
        assert r.json()['nag_mode'] == mode
    assert OperationSettingsStore(tmp_path).load().nag_mode == mode


@pytest.mark.asyncio
async def test_classic_lure_never_reads_pi_media(tmp_path, monkeypatch):
    app = create_app(Settings(data_dir=tmp_path, simulation=True))
    store = app.state.operation_store
    store.save(store.load().model_copy(update={'nag_mode':'media','nag_require_presence':False}))
    (tmp_path/'nag-media.json').write_text(json.dumps({'serials':[7]}))
    monkeypatch.setattr(app.state.hardware,'media_status',lambda:{'files':[{'serial':7,'enabled':True}]})
    monkeypatch.setattr(PiMediaLibrary,'status',lambda self:pytest.fail('Classic must not inspect Pi Media'))
    played=[]
    async def play(serial, enabled):played.append(serial)
    monkeypatch.setattr(app.state.hardware,'play_media',play)
    result=await app.state.perception._nagger(0,100,None)
    assert result['source']=='skelly' and played==[7]


@pytest.mark.asyncio
async def test_pi_lure_never_falls_back_to_classic_or_ai(tmp_path, monkeypatch):
    app = create_app(Settings(data_dir=tmp_path, simulation=True))
    store=app.state.operation_store
    store.save(store.load().model_copy(update={'nag_mode':'pi_media','nag_require_presence':False}))
    monkeypatch.setattr(app.state.hardware,'media_status',lambda:pytest.fail('Pi Media must not inspect Classic'))
    monkeypatch.setattr(PiMediaLibrary,'status',lambda self:{'files':[]})
    assert await app.state.perception._nagger(0,100,None) is None
    monkeypatch.setattr(PiMediaLibrary,'status',lambda self:{'files':[{'name':'pi.wav','enabled':True,'nag_response':True}]})
    class SelectedPi(Exception):pass
    def get(self,name):
        assert name=='pi.wav'
        raise SelectedPi
    monkeypatch.setattr(PiMediaLibrary,'get',get)
    with pytest.raises(SelectedPi):
        await app.state.perception._nagger(0,100,None)
