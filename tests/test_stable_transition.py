import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest
from fastapi.testclient import TestClient
from skelly_ai import api as api_module
from skelly_ai.config import Settings

OFFICIAL='https://raw.githubusercontent.com/TheDadTech/UltraSkellyAdvanced/main/releases/stable/latest.json'
PACKAGE='https://github.com/TheDadTech/UltraSkellyAdvanced/releases/download/v0.28.0/UltraSkellyAdvanced-0.28.0.zip'


def release_bytes(version='0.28.0'):
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w') as z:
        z.writestr('pyproject.toml',f'[project]\nname="skelly-ai"\nversion="{version}"')
        z.writestr('deploy/bootstrap-pi.sh','#!/bin/bash\n')
        z.writestr('src/skelly_ai/__init__.py','__version__="'+version+'"')
    return buf.getvalue()


def setup_transition(tmp_path,monkeypatch,version='0.28.2',channel='beta',changes=None,package_version='0.28.0',helper_failure=False):
    monkeypatch.setattr(api_module,'__version__',version)
    monkeypatch.setattr(api_module,'__release_channel__','beta')
    monkeypatch.setattr(api_module,'__stable_transition_target__','0.28.0')
    data=release_bytes(package_version)
    manifest={'version':'0.28.0','channel':'stable','package_url':PACKAGE,'sha256':hashlib.sha256(data).hexdigest()}
    manifest.update(changes or {})
    requests=[];calls=[]
    class Response:
        def raise_for_status(self):pass
        def json(self):return manifest
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def aiter_bytes(self):yield data
    class Client:
        def __init__(self,*args,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def get(self,url):requests.append(url);return Response()
        def stream(self,method,url):requests.append(url);return Response()
    monkeypatch.setattr(api_module.httpx,'AsyncClient',Client)
    app=api_module.create_app(Settings(data_dir=tmp_path,simulation=True,update_manifest_url='https://untrusted.invalid/override.json'))
    (tmp_path/'update-channel.json').write_text(json.dumps({'channel':channel}))
    store=app.state.operation_store
    store.save(store.load().model_copy(update={'skelly_name':'Preserve my setup'}))
    credentials=tmp_path/'credentials.json';credentials.write_text(json.dumps({'groq_api_key':'dummy-groq','elevenlabs_api_key':'dummy-elevenlabs'}))
    original={name:(tmp_path/name).read_bytes() for name in ['operation-settings.json','credentials.json']}
    def run(args,**kwargs):
        calls.append(args)
        if not helper_failure:app.state.updates._write_status('installing','Starting stable transition','0.28.0')
        return SimpleNamespace(returncode=1 if helper_failure else 0,stderr='Test installer failure' if helper_failure else '',stdout='')
    monkeypatch.setattr('skelly_ai.updates.subprocess',SimpleNamespace(run=run))
    return app,requests,calls,original


@pytest.mark.parametrize('version',['0.28.1','0.28.2','0.28.3-beta1'])
@pytest.mark.parametrize('channel',['beta','stable'])
def test_interim_versions_return_to_official_0280_with_rollback_handoff(tmp_path,monkeypatch,version,channel):
    app,requests,calls,original=setup_transition(tmp_path,monkeypatch,version,channel)
    with TestClient(app) as c:
        status=c.get('/api/update/status').json()
        assert status['running_beta'] and status['return_to_stable_available']
        r=c.post('/api/update/return-stable')
        assert r.status_code==200,r.text
        assert calls[0][3:5]==['update-install','0.28.0']
        assert calls[0][-1]==version  # existing installer receives correct rollback predecessor
        assert requests[0].split('?')[0]==OFFICIAL and requests[1]==PACKAGE
        assert c.get('/api/update/status').json()['channel']=='stable'
        for name,content in original.items():assert (tmp_path/name).read_bytes()==content
        # Rollback remains keyed to the installed target, not numeric ordering.
        app.state.updates.rollback_path.write_text(json.dumps({'available':True,'previous_version':version,'installed_version':'0.28.0'}))
        assert app.state.updates.rollback_status(current_version='0.28.0')=={'available':True,'previous_version':version}
        app.state.updates._write_status('succeeded','Stable transition complete','0.28.0')
        app.state.updates.start_rollback(current_version='0.28.0')
        assert calls[-1][3:]==['update-rollback','0.28.0']


@pytest.mark.parametrize('changes,status',[
    ({'version':'0.27.4'},409),({'version':'0.28.2'},409),({'version':'0.29.0'},409),
    ({'version':'0.28.0-beta1'},409),({'channel':'testing'},409),
    ({'package_url':'https://other.invalid/payload.zip'},502),({'sha256':'0'*64},422),
])
def test_transition_does_not_allow_unrelated_downgrades_or_unverified_packages(tmp_path,monkeypatch,changes,status):
    app,requests,calls,_=setup_transition(tmp_path,monkeypatch,changes=changes)
    with TestClient(app) as c:
        r=c.post('/api/update/return-stable')
        assert r.status_code==status,r.text
        assert not calls
        assert c.get('/api/update/status').json()['channel']=='beta'


@pytest.mark.parametrize('kwargs',[{'package_version':'0.27.4'},{'helper_failure':True}])
def test_staging_failure_preserves_channel_and_does_not_change_settings(tmp_path,monkeypatch,kwargs):
    app,requests,calls,original=setup_transition(tmp_path,monkeypatch,**kwargs)
    with TestClient(app) as c:
        assert c.post('/api/update/return-stable').status_code==422
        assert c.get('/api/update/status').json()['channel']=='beta'
        for name,content in original.items():assert (tmp_path/name).read_bytes()==content


def test_stable_build_and_regular_version_guards_are_not_weakened(tmp_path,monkeypatch):
    app,requests,calls,_=setup_transition(tmp_path,monkeypatch,version='0.28.0')
    monkeypatch.setattr(api_module,'__release_channel__','stable')
    with TestClient(app) as c:
        status=c.get('/api/update/status').json()
        assert not status['running_beta'] and not status['return_to_stable_available']
        assert c.post('/api/update/return-stable').status_code==409
        assert not requests and not calls
    monkeypatch.setattr(api_module,'__version__','0.28.2')
    with TestClient(app) as c:
        assert c.post('/api/update/install').status_code==409
        assert c.post('/api/update/manual/verify',headers={'X-USA-Version':'0.28.0'}).status_code==409
        assert c.post('/api/update/return-stable').status_code==409
        assert not calls


def test_transition_requires_idle_and_same_origin(tmp_path,monkeypatch):
    app,requests,calls,_=setup_transition(tmp_path,monkeypatch)
    with TestClient(app) as c:
        assert c.post('/api/update/return-stable',headers={'Origin':'https://other.invalid'}).status_code==403
        c.post('/api/operation/start',json={'mode':'classic'})
        assert c.post('/api/update/return-stable').status_code==409
        assert not calls
