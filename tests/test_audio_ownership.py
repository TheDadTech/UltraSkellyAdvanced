"""Synthetic multi-account Bluetooth ownership and reversible migration fixtures."""
import importlib.util
from pathlib import Path
import subprocess
import pytest
from test_audio_sessions import load_helper, SERVICE, SECONDARY
from test_speaker_repair import audio_fixture, SPEAKER, BLE
from skelly_ai.classic_audio import ClassicAudioUnavailable, _CommandResult


def policy_module():
    path=Path(__file__).parents[1]/'deploy/audio-session-policy.py'
    spec=importlib.util.spec_from_file_location('synthetic_policy',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_single_owner_policy_is_persistent_idempotent_and_reversible(tmp_path):
    p=policy_module()
    assert p.migrate(tmp_path,'owner')
    assert not p.migrate(tmp_path,'owner')
    config=tmp_path/'.config/wireplumber/wireplumber.conf.d/90-usa-bluetooth-owner.conf'
    assert 'monitor.bluez = required' in config.read_text()
    assert p.migrate(tmp_path,'restore')
    assert not config.exists()


def test_only_recognized_secondary_policy_is_migrated_and_restored(tmp_path):
    p=policy_module();config=tmp_path/'.config/wireplumber/wireplumber.conf.d/50-headless-bluetooth.conf'
    config.parent.mkdir(parents=True);config.write_text(p.LEGACY)
    assert p.migrate(tmp_path,'secondary')
    assert 'monitor.bluez = disabled' in config.read_text()
    assert 'monitor.alsa' not in config.read_text()
    assert not p.migrate(tmp_path,'secondary')
    assert p.migrate(tmp_path,'restore')
    assert config.read_text()==p.LEGACY


def test_custom_secondary_and_unrelated_configuration_are_untouched(tmp_path):
    p=policy_module();config=tmp_path/'.config/wireplumber/wireplumber.conf.d/50-headless-bluetooth.conf'
    config.parent.mkdir(parents=True);config.write_text('synthetic custom owner policy')
    assert not p.migrate(tmp_path,'secondary')
    assert config.read_text()=='synthetic custom owner policy'
    assert not p.migrate(tmp_path/'other_test_user','secondary')
    assert not (tmp_path/'other_test_user').exists()


def test_owner_collision_and_edits_after_migration_are_preserved(tmp_path):
    p=policy_module();p.migrate(tmp_path,'owner')
    config=tmp_path/'.config/wireplumber/wireplumber.conf.d/90-usa-bluetooth-owner.conf'
    config.write_text('synthetic custom policy')
    with pytest.raises(RuntimeError):p.migrate(tmp_path,'owner')
    with pytest.raises(RuntimeError):p.migrate(tmp_path,'restore')
    assert config.read_text()=='synthetic custom policy'


def test_fresh_image_secondary_has_no_bluetooth_monitor(tmp_path):
    p=policy_module();assert p.migrate(tmp_path,'fresh-secondary')
    assert 'monitor.bluez = disabled' in (tmp_path/'.config/wireplumber/wireplumber.conf.d/50-headless-bluetooth.conf').read_text()


def test_helper_restart_is_scoped_to_service_account(monkeypatch):
    h,calls=load_helper(monkeypatch)
    h.audio_session_recover(SERVICE)
    restarts=[args for args in calls if 'restart' in args]
    assert len(restarts)==1 and restarts[0][:4]==('runuser','-u',SERVICE,'--')
    assert restarts[0][-1]=='wireplumber.service'
    assert not any(SECONDARY in args or 'stop' in args for args in calls)
    with pytest.raises(SystemExit):h.audio_session_recover(SECONDARY)


@pytest.mark.parametrize('processes,expected',[
    ('2620 wireplumber\n','Check USA WirePlumber'),
    ('2620 wireplumber\n4621 wireplumber\n','possible audio ownership conflict'),
])
def test_missing_sink_diagnosis_never_stops_competing_accounts(monkeypatch,processes,expected):
    h,calls=load_helper(monkeypatch);original=h.run
    def run(*args,**kwargs):
        if args[0]=='ps':return subprocess.CompletedProcess(args,0,processes,'')
        return original(*args,**kwargs)
    monkeypatch.setattr(h,'run',run)
    with pytest.raises(SystemExit,match=expected):h.audio_session_diagnose(SERVICE)
    assert not any('stop' in args or 'restart' in args for args in calls)


@pytest.mark.asyncio
async def test_connected_missing_card_recovers_sink_without_forgetting(monkeypatch):
    audio,calls=audio_fixture(monkeypatch,initially_paired=True)
    recovered=[]
    async def missing():return audio._update(sink_ready=False,sink_id=None)
    async def recover():recovered.append(True)
    monkeypatch.setattr(audio,'_read_pipewire_status',missing)
    monkeypatch.setattr(audio,'_recover_audio_owner',recover)
    result=await audio.repair('0579',forbidden_addresses={BLE})
    assert result.connected and result.sink_ready and recovered
    assert ('connect',SPEAKER) in calls
    assert not any(args[0] in {'remove','pair','scan'} for args in calls)
    assert all(BLE not in args for args in calls)


@pytest.mark.asyncio
async def test_already_usable_pairing_is_preserved_without_discovery(monkeypatch):
    audio,calls=audio_fixture(monkeypatch,initially_paired=True)
    async def ready():return audio._update(sink_ready=True,sink_id='91')
    monkeypatch.setattr(audio,'_read_pipewire_status',ready)
    result=await audio.repair('0579',forbidden_addresses={BLE})
    assert result.sink_ready
    assert not any(args[0] in {'remove','connect','disconnect','scan'} for args in calls)


@pytest.mark.asyncio
async def test_known_paired_speaker_missing_sink_reports_conflict_without_bond_reset(monkeypatch):
    audio,calls=audio_fixture(monkeypatch,initially_paired=True,sink=False)
    async def missing():return audio._update(sink_ready=False,sink_id=None)
    async def diagnosis():return 'Possible audio ownership conflict; unrelated services were left running.'
    monkeypatch.setattr(audio,'_read_pipewire_status',missing)
    monkeypatch.setattr(audio,'_missing_sink_error',diagnosis)
    with pytest.raises(ClassicAudioUnavailable,match='audio verification failed.*ownership conflict'):
        await audio.repair('0579',forbidden_addresses={BLE})
    assert not any(args[0]=='remove' for args in calls)
    assert not audio.snapshot().sink_ready


@pytest.mark.asyncio
async def test_restart_dropping_bluetooth_transport_is_reconnected(monkeypatch):
    audio,calls=audio_fixture(monkeypatch,initially_paired=True)
    original=audio._read_info;restarted=[]
    async def missing():return audio._update(sink_ready=False,sink_id=None)
    async def recover():
        restarted.append(True)
        await audio._run('disconnect',SPEAKER)
    monkeypatch.setattr(audio,'_read_pipewire_status',missing)
    monkeypatch.setattr(audio,'_recover_audio_owner',recover)
    assert (await audio.repair('0579',forbidden_addresses={BLE})).sink_ready
    assert restarted and ('connect',SPEAKER) in calls
    assert not any(args[0]=='remove' for args in calls)


def test_missing_runtime_is_actionable_without_touching_other_users(monkeypatch):
    from types import SimpleNamespace
    h,calls=load_helper(monkeypatch)
    class Missing:
        def exists(self):return False
    monkeypatch.setattr(h,'pathlib',SimpleNamespace(Path=lambda value:Missing()))
    with pytest.raises(SystemExit,match='runtime is unavailable'):
        h._audio_session_env(SERVICE)
    times=iter([0,11])
    monkeypatch.setattr(h,'time',SimpleNamespace(monotonic=lambda:next(times)))
    with pytest.raises(SystemExit,match='runtime is unavailable'):
        h.audio_session_prepare(SERVICE)
    assert not any(SECONDARY in args or 'stop' in args for args in calls)


def test_failed_owner_restart_reports_partial_failure_without_stopping_others(monkeypatch):
    h,calls=load_helper(monkeypatch);original=h.run
    def run(*args,**kwargs):
        if 'restart' in args:return subprocess.CompletedProcess(args,1,'','synthetic failure')
        return original(*args,**kwargs)
    monkeypatch.setattr(h,'run',run)
    with pytest.raises(SystemExit,match='could not restart'):h.audio_session_recover(SERVICE)
    assert not any(SECONDARY in args or 'stop' in args for args in calls)


@pytest.mark.asyncio
async def test_stale_authentication_can_reset_only_speaker_bond(monkeypatch):
    audio,calls=audio_fixture(monkeypatch,initially_paired=True)
    original=audio._run;attempts=[]
    async def missing():return audio._update(sink_ready=False,sink_id=None)
    async def run(*args,**kwargs):
        if args[0]=='connect' and not attempts:
            attempts.append(True)
            return _CommandResult(1,'org.bluez.Error.AuthenticationFailed')
        return await original(*args,**kwargs)
    monkeypatch.setattr(audio,'_read_pipewire_status',missing)
    monkeypatch.setattr(audio,'_run',run)
    assert (await audio.repair('0579',forbidden_addresses={BLE})).sink_ready
    assert ('remove',SPEAKER) in calls
    assert all(BLE not in args for args in calls)


@pytest.mark.asyncio
async def test_offline_known_bond_recovery_does_not_use_network(monkeypatch):
    import socket
    def forbidden(*args,**kwargs):raise AssertionError('Repair must work offline')
    monkeypatch.setattr(socket,'create_connection',forbidden)
    audio,calls=audio_fixture(monkeypatch,initially_paired=True)
    assert (await audio.repair('0579',forbidden_addresses={BLE})).sink_ready


@pytest.mark.asyncio
@pytest.mark.parametrize('selected,expected',[('skelly',True),('system',False),('external_bluetooth',False)])
async def test_selected_route_recovers_after_restart_without_changing_preference(tmp_path,monkeypatch,selected,expected):
    import asyncio
    import inspect
    from skelly_ai.api import create_app
    from skelly_ai.config import Settings
    app=create_app(Settings(simulation=True,data_dir=tmp_path))
    lifecycle=inspect.getclosurevars(app.router.lifespan_context.__wrapped__).nonlocals
    maintain=lifecycle['maintain_external_audio_connection']
    state=inspect.getclosurevars(maintain).nonlocals
    store=state['operation_store']
    store.save(store.load().model_copy(update={'device_configured':True,'speaker_address':SPEAKER,'audio_output':selected}))
    audio=state['classic_audio'];calls=[]
    async def refresh():return audio._snapshot
    async def connect(*,route=True):
        calls.append(route)
        # SimulatedClassicAudio is intentionally a different implementation;
        # use its real connect to produce the same public snapshot contract.
        return await original_connect()
    original_connect=audio.connect
    monkeypatch.setattr(audio,'connect',connect)
    sleeps=[]
    async def sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps)>1:raise asyncio.CancelledError()
    monkeypatch.setattr('skelly_ai.api.asyncio.sleep',sleep)
    with pytest.raises(asyncio.CancelledError):await maintain()
    assert bool(calls) is expected
    assert store.load().audio_output==selected
