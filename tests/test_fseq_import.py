import ctypes
import ctypes.util
import json
import struct
import wave
import array
import pytest
from fastapi.testclient import TestClient
from skelly_ai.fseq_import import inspect, render, decompress, SequenceLibrary
from skelly_ai.fpp_sync import MediaTimeline
from skelly_ai.api import create_app
from skelly_ai.config import Settings

XML=b'''<xsequence><ElementEffects><Element type="timing" name="Singer"><EffectLayer><Effect label="Hello" startTime="0" endTime="500"/></EffectLayer><EffectLayer><Effect label="AI" startTime="100" endTime="300"/><Effect label="MBP" startTime="300" endTime="400"/><Effect label="FV" startTime="400" endTime="500"/></EffectLayer></Element></ElementEffects></xsequence>'''

def fseq(xml=XML):
    z=ctypes.CDLL(ctypes.util.find_library('zstd'))
    z.ZSTD_compressBound.argtypes=[ctypes.c_size_t];z.ZSTD_compressBound.restype=ctypes.c_size_t
    cap=z.ZSTD_compressBound(len(xml));buf=ctypes.create_string_buffer(cap)
    z.ZSTD_compress.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_int];z.ZSTD_compress.restype=ctypes.c_size_t
    n=z.ZSTD_compress(buf,cap,xml,len(xml),1);compressed=buf.raw[:n]
    mf=b'C:\\show\\Song.mp3\0';meta=struct.pack('<H2s',len(mf)+4,b'mf')+mf
    offset=32+len(meta)+18
    extended=struct.pack('<H2s2sQI',18,b'ED',b'XS',offset,len(compressed))
    header=bytearray(32);header[:4]=b'PSEQ';struct.pack_into('<HBBHII',header,4,offset,2,2,32,1,40);header[18]=25
    return bytes(header)+meta+extended+compressed

def test_extract_and_render_release_and_closed(tmp_path):
    p=tmp_path/'x.fseq';p.write_bytes(fseq());info=inspect(p)
    assert info['media_name']=='Song.mp3'
    assert [(t['name'],t['layer'],t['cue_count']) for t in info['tracks']]==[('Singer',2,3)]
    out=tmp_path/'p.wav';render(info,'Singer',out)
    with wave.open(str(out)) as w:
        assert w.getnframes()==22050
        data=array.array('h');data.frombytes(w.readframes(w.getnframes()))
    def energy(start,end):return max(map(abs,data[round(start*22050):round(end*22050)]),default=0)
    assert energy(.11,.18)>6000
    assert energy(.21,.4)==0  # release + MBP
    assert energy(.41,.44)>0 and energy(.46,.5)==0
    with pytest.raises(ValueError):render(info,'not there',out)
    with pytest.raises(ValueError):render(info,'Singer',out,6000)

@pytest.mark.parametrize('data',[b'bad',fseq(b'<xsequence/>'),fseq(b'<!DOCTYPE a><xsequence/>')])
def test_invalid_input(tmp_path,data):
    p=tmp_path/'x';p.write_bytes(data)
    with pytest.raises(ValueError):inspect(p)

def test_extended_range_rejected(tmp_path):
    b=bytearray(fseq());pos=b.index(b'EDXS')+4;struct.pack_into('<Q',b,pos,len(b)+100)
    p=tmp_path/'x';p.write_bytes(b)
    with pytest.raises(ValueError):inspect(p)

def test_mapping_is_safe_and_persistent(tmp_path):
    media=tmp_path/'media';media.mkdir();(media/'generated.wav').write_bytes(b'wave')
    lib=SequenceLibrary(tmp_path);lib.link('Song.mp3','generated.wav','Singer')
    t=MediaTimeline(media,'10.0.0.1');t.filename='Song.mp3';assert t.local_file()==media/'generated.wav'
    lib.map_path.write_text(json.dumps({'Song.mp3':{'file':'../secret.wav'}}));assert t.local_file() is None

@pytest.mark.asyncio
async def test_failed_import_removes_raw_file(tmp_path):
    lib=SequenceLibrary(tmp_path)
    async def chunks():yield b'bad'
    with pytest.raises(ValueError):await lib.receive(chunks())
    assert list(lib.root.iterdir())==[]

def test_api_import_prepare_link_and_fallback(tmp_path):
    app=create_app(Settings(data_dir=tmp_path,simulation=True));headers={'X-USA-Interactive-Auth':'1'}
    with TestClient(app) as c:
        assert c.post('/api/fpp/sequence/import',content=fseq()).status_code==403
        response=c.post('/api/fpp/sequence/import',content=fseq(),headers=headers)
        assert response.status_code==200,response.text
        d=response.json();assert 'cues' not in d['tracks'][0]
        r=c.post('/api/fpp/sequence/prepare',headers=headers,json={'id':d['id'],'media_name':'Song.mp3','track':'Singer','offset_ms':0})
        assert r.status_code==200,r.text
        generated=r.json()['file'];assert (tmp_path/'media'/generated).is_file()
        assert c.get('/api/fpp/sequence/links').json()['Song.mp3']['file']==generated
        assert c.get('/api/pi-media/status').json()['file_count']==1 # registered; not pruned
        c.post('/api/fpp/sequence/unlink',headers=headers,json={'media_name':'Song.mp3'})
        assert c.get('/api/fpp/sequence/links').json()=={}
        assert c.post('/api/fpp/sequence/prepare',headers=headers,json={'id':'../bad'}).status_code==422

def test_old_timing_cues_past_rendered_end_are_clipped(tmp_path):
    p=tmp_path/'x';p.write_bytes(fseq(XML.replace(b'endTime="500"',b'endTime="1500"')))
    info=inspect(p)
    assert info['tracks'][0]['cues'][-1][1]==1000

@pytest.mark.parametrize('xml',[
    ('<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE x [<!ENTITY x "boom">]><xsequence>&x;</xsequence>').encode('utf-16'),
    XML.replace(b'startTime="400"',b'startTime="200"'),
    XML.replace(b'startTime="100"',b'startTime="-1"'),
    XML.replace(b'endTime="300"',b'endTime="100"'),
    XML.replace(b'endTime="300"',b'endTime="99999999999999999999"'),
    XML.replace(b'xsequence',b'wrongroot'),
])
def test_hostile_metadata_rejected(tmp_path,xml):
    p=tmp_path/'x';p.write_bytes(fseq(xml))
    with pytest.raises(ValueError):inspect(p)


def test_mutated_headers_never_crash_or_allocate_unbounded(tmp_path):
    import random
    rnd=random.Random(413);original=fseq();p=tmp_path/'mutant'
    for _ in range(1200):
        data=bytearray(original)
        for _ in range(rnd.randint(1,5)):
            index=rnd.randrange(len(data));data[index]=rnd.randrange(256)
        p.write_bytes(data)
        try:
            result=inspect(p)
            assert 0<result['duration_ms']<=1800000
        except ValueError:
            pass


@pytest.mark.asyncio
async def test_worker_timeout_reaps_process(tmp_path,monkeypatch):
    import asyncio
    import os
    from skelly_ai.fseq_worker import run_worker
    spawn=asyncio.create_subprocess_exec;children=[]
    async def capture(*args,**kwargs):
        child=await spawn(*args,**kwargs);children.append(child);return child
    monkeypatch.setattr(asyncio,'create_subprocess_exec',capture)
    p=tmp_path/'x';p.write_bytes(fseq())
    with pytest.raises(TimeoutError):
        await run_worker('inspect',str(p),str(tmp_path/'out'),timeout=.00001)
    assert children and children[0].returncode is not None
    with pytest.raises(ProcessLookupError):os.kill(children[0].pid,0)


@pytest.mark.asyncio
async def test_cancelled_import_reaps_worker_and_cleans_files(tmp_path,monkeypatch):
    import asyncio
    from skelly_ai import fseq_worker
    original=asyncio.create_subprocess_exec;started=asyncio.Event();children=[]
    async def spawn(*args,**kwargs):
        child=await original(*args,**kwargs);children.append(child);started.set();return child
    monkeypatch.setattr(asyncio,'create_subprocess_exec',spawn)
    async def chunks():yield fseq()
    task=asyncio.create_task(SequenceLibrary(tmp_path).receive(chunks()))
    await started.wait();task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    assert children[0].returncode is not None
    assert list((tmp_path/'fseq-imports').iterdir())==[]


def test_repeated_preparation_reuses_registered_audio(tmp_path):
    app=create_app(Settings(data_dir=tmp_path,simulation=True));h={'X-USA-Interactive-Auth':'1'}
    with TestClient(app) as c:
        d=c.post('/api/fpp/sequence/import',headers=h,content=fseq()).json()
        body={'id':d['id'],'media_name':'Song.mp3','track':'Singer','offset_ms':0}
        files=[]
        for _ in range(12):
            r=c.post('/api/fpp/sequence/prepare',headers=h,json=body)
            assert r.status_code==200,r.text
            files.append(r.json()['file'])
        assert len(set(files))==1
        assert c.get('/api/pi-media/status').json()['file_count']==1
        # A reimport of the same content must reuse the same generated asset too.
        d=c.post('/api/fpp/sequence/import',headers=h,content=fseq()).json();body['id']=d['id']
        assert c.post('/api/fpp/sequence/prepare',headers=h,json=body).json()['file']==files[0]


@pytest.mark.parametrize('body',[None,[],1,'text',{'id':None},{'id':[]},{'id':'../bad'}, {'media_name':'../secret'}])
def test_bad_prepare_json_never_500(tmp_path,body):
    with TestClient(create_app(Settings(data_dir=tmp_path,simulation=True))) as c:
        r=c.post('/api/fpp/sequence/prepare',headers={'X-USA-Interactive-Auth':'1'},content=json.dumps(body))
        assert r.status_code==422,r.text


def test_invalid_json_and_large_settings_rejected(tmp_path):
    h={'X-USA-Interactive-Auth':'1'}
    with TestClient(create_app(Settings(data_dir=tmp_path,simulation=True))) as c:
        for route in ['prepare','unlink']:
            for data in ['not json','[1]', '{"a":"'+'x'*70000+'"}']:
                assert c.post('/api/fpp/sequence/'+route,headers=h,content=data).status_code==422
        assert c.post('/api/fpp/sequence/import',headers={**h,'Origin':'http://evil.example'},content=fseq()).status_code==403


@pytest.mark.parametrize('mapping',[[],None,{'Song.mp3':None},{'Song.mp3':{'file':'../secret','track':'Singer'}}])
def test_damaged_map_not_overwritten(tmp_path,mapping):
    lib=SequenceLibrary(tmp_path);lib.map_path.write_text(json.dumps(mapping))
    original=lib.map_path.read_bytes()
    with pytest.raises(ValueError):lib.link('Song.mp3','new.wav','Singer')
    assert lib.map_path.read_bytes()==original


def test_metadata_cache_bounded(tmp_path):
    lib=SequenceLibrary(tmp_path);lib.root.mkdir()
    for i in range(50):(lib.root/(f'{i:032x}.json')).write_text('{}')
    newest=lib.root/'new.json';newest.write_text('{}');lib.prune(exclude=newest)
    assert len(list(lib.root.iterdir()))<=32 and newest.exists()


def test_stock_silent_settings_rejected(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path,simulation=True))) as c:
        r=c.post('/api/fpp/settings',headers={'X-USA-Interactive-Auth':'1'},json={'enabled':True,'master_ip':'10.10.10.19','play_audio':False})
        assert r.status_code==422,r.text
        assert 'failed hardware validation' in r.json()['detail']


def test_duplicate_and_one_frame_overlap_normalized_with_count(tmp_path):
    xml=XML.replace(b'<Effect label="MBP"',b'<Effect label="AI" startTime="100" endTime="300"/><Effect label="MBP"').replace(b'startTime="400"',b'startTime="375"')
    p=tmp_path/'x';p.write_bytes(fseq(xml));info=inspect(p);track=info['tracks'][0]
    assert track['adjusted_cues']==2
    assert track['cue_count']==3
    assert track['cues'][1]==[300,375,'MBP']


@pytest.mark.asyncio
async def test_worker_does_not_inherit_provider_credentials(tmp_path,monkeypatch):
    import asyncio
    from skelly_ai.fseq_worker import run_worker
    spawn=asyncio.create_subprocess_exec;seen=[]
    monkeypatch.setenv('ELEVENLABS_API_KEY','fictional-test-key')
    monkeypatch.setenv('GROQ_API_KEY','fictional-test-key')
    async def capture(*args,**kwargs):
        seen.append(kwargs['env']);return await spawn(*args,**kwargs)
    monkeypatch.setattr(asyncio,'create_subprocess_exec',capture)
    source=tmp_path/'x';source.write_bytes(fseq())
    await run_worker('inspect',str(source),str(tmp_path/'parsed.json'))
    assert 'ELEVENLABS_API_KEY' not in seen[0] and 'GROQ_API_KEY' not in seen[0]


def test_generated_jaw_tracks_are_identified_without_body_motion_or_lures(tmp_path):
    from skelly_ai.pi_media import PiMediaLibrary
    library=PiMediaLibrary(tmp_path)
    name='fseq-'+'a'*32+'.wav'
    library.add(name,b'fixture')
    status=library.status();entry=next(f for f in status['files'] if f['name']==name)
    assert entry['generated_fseq'] is True
    assert entry['action']==0 and entry['nag_response'] is False


def test_recording_switch_preserves_sequence_and_rejects_missing_file(tmp_path):
    app=create_app(Settings(data_dir=tmp_path,simulation=True));h={'X-USA-Interactive-Auth':'1'}
    with TestClient(app) as c:
        d=c.post('/api/fpp/sequence/import',headers=h,content=fseq()).json()
        r=c.post('/api/fpp/sequence/prepare',headers=h,json={'id':d['id'],'media_name':'Song.mp3','track':'Singer'});assert r.status_code==200
        generated=r.json()['file'];before=c.get('/api/fpp/sequence/links').json()
        bad=c.post('/api/fpp/sequence/source',headers=h,json={'media_name':'Song.mp3','source':'audio','file':'missing.wav'})
        assert bad.status_code==422 and c.get('/api/fpp/sequence/links').json()==before
        c.post('/api/pi-media/upload?filename=Vocals.wav',content=b'fixture')
        r=c.post('/api/fpp/sequence/source',headers=h,json={'media_name':'Song.mp3','source':'audio','file':'Vocals.wav'})
        assert r.status_code==200 and r.json()['sequence_file']==generated
        assert (tmp_path/'media'/generated).exists()
        r=c.post('/api/fpp/sequence/source',headers=h,json={'media_name':'Song.mp3','source':'sequence'})
        assert r.status_code==200 and r.json()['file']==generated


def test_generated_preset_keeps_custom_movement_and_timing(tmp_path):
    from skelly_ai.pi_media import PiMediaLibrary
    lib=PiMediaLibrary(tmp_path);name='fseq-'+'b'*32+'.wav';lib.add(name,b'fixture')
    app=create_app(Settings(data_dir=tmp_path,simulation=True))
    with TestClient(app) as c:
        r=c.post('/api/pi-media/edit',json={'name':name,'action':1,'eye':4,'jaw_timing_offset_ms':-500})
        assert r.status_code==200,r.text
        entry=next(f for f in r.json()['files'] if f['name']==name)
        assert entry['action']==1 and entry['eye']==4 and entry['jaw_timing_offset_ms']==-500
        assert c.post('/api/pi-media/edit',json={'name':name,'jaw_timing_offset_ms':6000}).status_code==422


def test_deferred_feature_is_not_exposed_or_shipped(tmp_path):
    from pathlib import Path
    import skelly_ai.api
    base=Path(skelly_ai.api.__file__).parent
    assert not (base/'holiday.py').exists()
    assert not (base/'static/visitor.js').exists()
    with TestClient(create_app(Settings(data_dir=tmp_path,simulation=True))) as c:
        assert c.get('/api/holiday/settings').status_code==404
        assert c.get('/visitor').status_code==404
