import asyncio
import inspect

import pytest
from fastapi.testclient import TestClient
from skelly_ai.api import create_app
from skelly_ai.config import Settings
from skelly_ai.classic_audio import BluetoothClassicAudio, ClassicAudioUnavailable, _CommandResult

SPEAKER='AA:BB:CC:DD:EE:02'
BLE='AA:BB:CC:DD:EE:01'


def audio_fixture(monkeypatch, *, missing=False, auth_failure=False, sink=True, wrong_name=False, initially_paired=True):
    monkeypatch.setattr('skelly_ai.classic_audio.shutil.which',lambda _: '/usr/bin/tool')
    audio=BluetoothClassicAudio(address=SPEAKER)
    state={'paired':initially_paired,'trusted':initially_paired,'connected':initially_paired}
    calls=[]
    async def run(*args, **kwargs):
        calls.append(args)
        if args==('devices',):
            return _CommandResult(0,'' if missing else f'Device {BLE} Animated Skelly\nDevice {SPEAKER} Animated Skelly(Live)')
        if args[0]=='info':
            name='Animated Skelly' if wrong_name else 'Animated Skelly(Live)'
            return _CommandResult(0,f'Device {SPEAKER}\n Name: {name}\n'+''.join(f' {k.title()}: {"yes" if v else "no"}\n' for k,v in state.items()))
        if args[0]=='disconnect':state['connected']=False
        if args[0]=='remove':state.update(paired=False,trusted=False,connected=False)
        if 'pair' in args:
            if auth_failure:return _CommandResult(1,'org.bluez.Error.AuthenticationCanceled')
            state['paired']=True
        if args[0]=='trust':state['trusted']=True
        if args[0]=='connect':state['connected']=True
        return _CommandResult(0,'')
    async def pause():return False
    async def route():return audio._update(sink_ready=sink,sink_id='91' if sink else None)
    async def program(*args,**kwargs):return _CommandResult(0,'Audio\n Sinks:\n * 91. Animated Skelly(Live) [vol: 1.00]\n Sources:')
    monkeypatch.setattr(audio,'_run_program',program)
    monkeypatch.setattr(audio,'_run',run)
    monkeypatch.setattr(audio,'_pause_competing_audio_session',pause)
    monkeypatch.setattr(audio,'_route_pipewire_sink',route)
    monkeypatch.setattr(audio,'_find_pipewire_sink_without_routing',route)
    return audio,calls


@pytest.mark.asyncio
async def test_repair_removes_stale_speaker_bond_and_preserves_ble(monkeypatch):
    audio,calls=audio_fixture(monkeypatch)
    result=await audio.repair('0000',forbidden_addresses={BLE})
    assert result.connected and result.paired and result.trusted and result.sink_ready
    assert ('remove',SPEAKER) in calls
    assert all(BLE not in args for args in calls)
    assert sum(args==('remove',SPEAKER) for args in calls)==1
    assert sum('scan' in args for args in calls)==2


@pytest.mark.asyncio
@pytest.mark.parametrize('option,message,removed',[
    ('missing','No unique',False),('wrong_name','identity',False),
    ('auth_failure','pairing PIN',True),('sink','PipeWire',True),
])
async def test_repair_failure_is_actionable_and_never_removes_other_devices(monkeypatch,option,message,removed):
    audio,calls=audio_fixture(monkeypatch,**{option:False if option=='sink' else True})
    with pytest.raises(ClassicAudioUnavailable,match=message):
        await audio.repair('0000',forbidden_addresses={BLE})
    assert (('remove',SPEAKER) in calls)==removed
    assert all(BLE not in args for args in calls)
    assert message.lower() in audio.snapshot().last_error.lower()


@pytest.mark.asyncio
async def test_repair_refuses_ble_address_even_if_its_name_looks_like_audio(monkeypatch):
    audio,calls=audio_fixture(monkeypatch)
    with pytest.raises(ClassicAudioUnavailable,match='No unique'):
        await audio.repair('0000',forbidden_addresses={SPEAKER})
    assert not any(args[0]=='remove' for args in calls)


@pytest.mark.asyncio
async def test_repair_preserves_selected_external_route(monkeypatch):
    audio,calls=audio_fixture(monkeypatch)
    async def forbidden():pytest.fail('External output must not be replaced')
    monkeypatch.setattr(audio,'_route_pipewire_sink',forbidden)
    assert (await audio.repair('0000',forbidden_addresses={BLE},route=False)).sink_ready


@pytest.mark.asyncio
async def test_repair_cancellation_releases_lock_and_records_recovery_advice(monkeypatch):
    audio,calls=audio_fixture(monkeypatch)
    entered=asyncio.Event()
    async def pair(*args):entered.set();await asyncio.Event().wait()
    monkeypatch.setattr(audio,'_pair',pair)
    task=asyncio.create_task(audio.repair('0000',forbidden_addresses={BLE}))
    await entered.wait();task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    assert not audio._lock.locked()
    assert 'retry' in audio.snapshot().last_error


def test_api_confirmation_origin_idle_and_ble_preservation(tmp_path,monkeypatch):
    app=create_app(Settings(data_dir=tmp_path,simulation=True))
    with TestClient(app) as c:
        assert c.post('/api/hardware/connect',json={'address':BLE}).status_code==200
        before=app.state.hardware.snapshot().to_dict()
        assert before['connected'] is True
        assert c.post('/api/audio/repair-speaker',json={}).status_code==409
        assert c.post('/api/audio/repair-speaker',json={'confirm':'repair-speaker'},headers={'Origin':'https://evil.invalid'}).status_code==403
        r=c.post('/api/audio/repair-speaker',json={'confirm':'repair-speaker'})
        assert r.status_code==200,r.text
        assert r.json()['speaker']['sink_ready']
        assert app.state.hardware.snapshot().to_dict()==before
        assert c.get('/api/audio/speaker-management').json()['repair']['state']=='succeeded'
        c.post('/api/operation/start',json={'mode':'classic'})
        assert c.post('/api/audio/repair-speaker',json={'confirm':'repair-speaker'}).status_code==409


@pytest.mark.asyncio
async def test_api_concurrent_repair_rejected_and_timeout_is_reported(tmp_path,monkeypatch):
    import httpx
    app=create_app(Settings(data_dir=tmp_path,simulation=True))
    entered=asyncio.Event();release=asyncio.Event()
    status_endpoint = next(r.endpoint for r in app.routes if getattr(r,'path','')=='/api/audio/status')
    audio = inspect.getclosurevars(status_endpoint).nonlocals['classic_audio']
    async def blocked(*args,**kwargs):
        entered.set();await release.wait();raise TimeoutError()
    monkeypatch.setattr(audio,'repair',blocked)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app,client=('127.0.0.1',50000)),base_url='http://testserver') as c:
        task=asyncio.create_task(c.post('/api/audio/repair-speaker',json={'confirm':'repair-speaker'}))
        await entered.wait()
        assert (await c.post('/api/audio/repair-speaker',json={'confirm':'repair-speaker'})).status_code==409
        assert (await c.post('/api/operation/start',json={'mode':'ai'})).status_code==409
        for path in ['/api/hardware/disconnect','/api/setup/forget-skelly','/api/audio/disconnect']:
            assert (await c.post(path)).status_code==409
        assert (await c.get('/api/audio/speaker-management')).json()['repair']['state']=='repairing'
        release.set();r=await task
        assert r.status_code==503 and 'timed out' in r.json()['detail']
        assert (await c.get('/api/audio/speaker-management')).json()['repair']['state']=='failed'


@pytest.mark.asyncio
async def test_repair_refuses_success_when_pipewire_default_does_not_match(monkeypatch):
    audio,calls=audio_fixture(monkeypatch)
    async def program(*args,**kwargs):return _CommandResult(0,'Audio\n Sinks:\n 91. Animated Skelly(Live) [vol: 1.00]\n Sources:')
    monkeypatch.setattr(audio,'_run_program',program)
    with pytest.raises(ClassicAudioUnavailable,match='not the selected'):
        await audio.repair('0000',forbidden_addresses={BLE})
    assert not audio.snapshot().sink_ready


@pytest.mark.asyncio
async def test_unavailable_bluetooth_never_removes_a_bond(monkeypatch):
    audio,calls=audio_fixture(monkeypatch)
    async def run(*args,**kwargs):
        calls.append(args)
        return _CommandResult(1,'No default controller available')
    monkeypatch.setattr(audio,'_run',run)
    with pytest.raises(ClassicAudioUnavailable,match='discovery could not start'):
        await audio.repair('0000',forbidden_addresses={BLE})
    assert not any(args[0]=='remove' for args in calls)


@pytest.mark.asyncio
async def test_failed_authentication_restores_competing_session(monkeypatch,tmp_path):
    audio,calls=audio_fixture(monkeypatch,auth_failure=True)
    helper=tmp_path/'helper';helper.touch();audio._system_helper=helper
    restored=[]
    async def resume():restored.append(True)
    monkeypatch.setattr(audio,'_resume_competing_audio_session',resume)
    with pytest.raises(ClassicAudioUnavailable,match='pairing PIN'):
        await audio.repair('0000',forbidden_addresses={BLE})
    assert restored==[True]


@pytest.mark.asyncio
@pytest.mark.parametrize('route_ok',[True,False])
async def test_audio_helper_failure_does_not_block_bluetooth_pairing(monkeypatch,route_ok):
    audio,calls=audio_fixture(monkeypatch)
    async def unavailable():raise ClassicAudioUnavailable('Audio session user is unavailable')
    monkeypatch.setattr(audio,'_pause_competing_audio_session',unavailable)
    if not route_ok:monkeypatch.setattr(audio,'_route_pipewire_sink',unavailable)
    if route_ok:
        assert (await audio.repair('0000',forbidden_addresses={BLE})).sink_ready
    else:
        with pytest.raises(ClassicAudioUnavailable,match='paired and connected, but audio verification failed'):
            await audio.repair('0000',forbidden_addresses={BLE})
        status=audio.snapshot()
        assert status.connected and status.paired and not status.sink_ready
        assert 'Audio session user' in status.last_error
    assert ('remove',SPEAKER) in calls and ('connect',SPEAKER) in calls
    assert all(BLE not in command for command in calls)


@pytest.mark.asyncio
async def test_repair_pairs_without_a_preexisting_sink_or_pairing(monkeypatch):
    audio,calls=audio_fixture(monkeypatch,initially_paired=False)
    # Existing fixture's remove resets all bond state; no sink lookup is allowed
    # until fresh pairing, trust and connection have completed.
    async def route():
        assert ('connect',SPEAKER) in calls
        return audio._update(sink_ready=True,sink_id='91')
    monkeypatch.setattr(audio,'_route_pipewire_sink',route)
    assert (await audio.repair('0000',forbidden_addresses={BLE})).sink_ready


@pytest.mark.asyncio
async def test_speaker_repair_is_offline_and_preserves_ble(monkeypatch):
    import socket
    def no_network(*args,**kwargs):raise AssertionError('Internet must not be needed for repair')
    monkeypatch.setattr(socket,'create_connection',no_network)
    audio,calls=audio_fixture(monkeypatch,initially_paired=False)
    assert (await audio.repair('0000',forbidden_addresses={BLE})).connected
    assert all(BLE not in command for command in calls)


def test_synthetic_audio_session_failure_returns_http503_without_identity(tmp_path,monkeypatch):
    app=create_app(Settings(data_dir=tmp_path,simulation=True))
    async def unavailable(*args,**kwargs):
        raise ClassicAudioUnavailable('Audio session user unavailable')
    monkeypatch.setattr(app.state.classic_audio,'repair',unavailable)
    with TestClient(app) as client:
        client.post('/api/hardware/connect',json={'address':BLE})
        result=client.post('/api/audio/repair-speaker',json={'confirm':'repair-speaker'})
        assert result.status_code==503
        assert result.json()['detail']=='Audio session user unavailable'
