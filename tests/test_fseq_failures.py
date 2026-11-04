"""Network, interrupted-operation and resource-bound regressions."""
import asyncio
import json
from pathlib import Path
import httpx
import pytest
from fastapi.testclient import TestClient
from skelly_ai.api import create_app
from skelly_ai.config import Settings
from skelly_ai.fseq_import import SequenceLibrary
from test_fseq_import import fseq

AUTH={'X-USA-Interactive-Auth':'1'}

def app(tmp_path):
    return create_app(Settings(data_dir=tmp_path,simulation=True,fpp_master_ip='10.10.10.19'))

@pytest.mark.asyncio
@pytest.mark.parametrize('failure',['offline','redirect','bad-json','huge','not-list'])
async def test_remote_listing_failures_are_bounded_and_clear(tmp_path,monkeypatch,failure):
    original=httpx.AsyncClient
    async def handler(request):
        if failure=='offline':raise httpx.ConnectError('offline',request=request)
        if failure=='redirect':return httpx.Response(302,headers={'Location':'http://outside.example/'})
        if failure=='bad-json':return httpx.Response(200,content=b'not JSON')
        if failure=='huge':return httpx.Response(200,content=b'x'*(1024*1024+1))
        return httpx.Response(200,json={'not':'a list'})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    a=app(tmp_path)
    async with original(transport=httpx.ASGITransport(app=a,client=('127.0.0.1',123)),base_url='http://usa') as client:
        r=await client.get('/api/fpp/sequences')
        assert r.status_code==422,r.text

@pytest.mark.asyncio
async def test_remote_import_is_readonly_fixed_host_and_does_not_follow_redirect(tmp_path,monkeypatch):
    original=httpx.AsyncClient;seen=[]
    async def handler(request):
        seen.append(request)
        return httpx.Response(302,headers={'Location':'http://outside.example/'})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    a=app(tmp_path)
    async with original(transport=httpx.ASGITransport(app=a,client=('127.0.0.1',123)),base_url='http://usa') as c:
        r=await c.post('/api/fpp/sequence/import?filename=Song.fseq',headers=AUTH)
        assert r.status_code==422
        assert len(seen)==1 and seen[0].method=='GET' and seen[0].url.host=='10.10.10.19'
        before=len(seen)
        r=await c.post('/api/fpp/sequence/import?filename=../secret.fseq',headers=AUTH)
        assert r.status_code==422 and len(seen)==before

@pytest.mark.asyncio
async def test_parallel_imports_reject_busy_instead_of_queuing_and_cleanup_after_failure(tmp_path,monkeypatch):
    started=asyncio.Event();finish=asyncio.Event()
    async def receive(self,chunks):
        started.set();await finish.wait();raise ValueError('simulated failed download')
    monkeypatch.setattr(SequenceLibrary,'receive',receive)
    a=app(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=a,client=('127.0.0.1',123)),base_url='http://usa') as c:
        task=asyncio.create_task(c.post('/api/fpp/sequence/import',content=b'x',headers=AUTH))
        await started.wait()
        responses=await asyncio.gather(*[c.post('/api/fpp/sequence/import',content=b'x',headers=AUTH) for _ in range(30)])
        assert all(r.status_code==409 for r in responses)
        finish.set();assert (await task).status_code==422
        assert (await c.post('/api/fpp/sequence/import',content=b'x',headers=AUTH)).status_code==422

@pytest.mark.asyncio
async def test_low_disk_and_chunk_failure_cleanup(tmp_path,monkeypatch):
    import shutil
    monkeypatch.setattr(shutil,'disk_usage',lambda p:shutil._ntuple_diskusage(1024,1023,1))
    async def chunks():yield b'xx'
    lib=SequenceLibrary(tmp_path)
    with pytest.raises(ValueError,match='space'):await lib.receive(chunks())
    assert list(lib.root.iterdir())==[]

@pytest.mark.asyncio
async def test_remote_client_cannot_reach_setup_endpoints(tmp_path):
    a=app(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=a,client=('8.8.8.8',123)),base_url='http://usa') as c:
        assert (await c.get('/api/fpp/sequences')).status_code==403
        assert (await c.get('/api/fpp/sequence/links')).status_code==403
        assert (await c.post('/api/fpp/sequence/import',headers=AUTH,content=b'x')).status_code==403


def test_failed_link_preserves_old_mapping_and_removes_new_generated_file(tmp_path,monkeypatch):
    lib=SequenceLibrary(tmp_path);lib.link('Song.mp3','previous.wav','Previous')
    before=lib.map_path.read_bytes()
    def fail(*args):raise OSError('simulated full disk at commit')
    monkeypatch.setattr(SequenceLibrary,'link',fail)
    with TestClient(app(tmp_path)) as c:
        imported=c.post('/api/fpp/sequence/import',headers=AUTH,content=fseq()).json()
        r=c.post('/api/fpp/sequence/prepare',headers=AUTH,json={'id':imported['id'],'media_name':'Song.mp3','track':'Singer'})
        assert r.status_code==422,r.text
        assert lib.map_path.read_bytes()==before
        assert c.get('/api/pi-media/status').json()['file_count']==0
        assert not list(lib.root.glob('*.tmp'))


def test_link_fsync_failure_preserves_previous_map(tmp_path,monkeypatch):
    import os
    lib=SequenceLibrary(tmp_path);lib.link('Song.mp3','old.wav','Old');before=lib.map_path.read_bytes()
    def fail(fd):raise OSError('simulated fsync failure')
    monkeypatch.setattr(os,'fsync',fail)
    with pytest.raises(OSError):lib.link('Song.mp3','new.wav','New')
    assert lib.map_path.read_bytes()==before
    assert not lib.map_path.with_suffix('.tmp').exists()
