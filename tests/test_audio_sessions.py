import importlib.util
from pathlib import Path
from types import SimpleNamespace
import subprocess
import pytest
from skelly_ai.audio_sessions import audio_session_users


def account(name,uid):
    return SimpleNamespace(pw_name=name,pw_uid=uid,pw_dir=f'/home/{name}')


def load_helper(monkeypatch,users=None,service='custom_user_a'):
    spec=importlib.util.spec_from_file_location('audio_helper',Path(__file__).parents[1]/'deploy/usa-system-helper.py')
    h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
    users=users if users is not None else {'custom_user_a':account('custom_user_a',1000),'dadtech':account('dadtech',1001)}
    def getpwnam(name):
        if name not in users:raise KeyError(name)
        return users[name]
    monkeypatch.setattr(h,'pwd',SimpleNamespace(getpwnam=getpwnam))
    calls=[]
    def run(*args,**kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args,0,service if args[:2]==('systemctl','show') else '', '')
    monkeypatch.setattr(h,'run',run)
    return h,calls


@pytest.mark.parametrize('user,uid',[('custom_user_a',1000),('custom_user_b',2345),('prop_owner',1017),('show-user',1100)])
def test_custom_effective_service_user_ignores_secondary_and_environment(monkeypatch,user,uid):
    monkeypatch.setattr('skelly_ai.audio_sessions.os.geteuid',lambda:uid)
    monkeypatch.setattr('skelly_ai.audio_sessions.pwd.getpwuid',lambda value:account(user,value))
    monkeypatch.setenv('USER','dadtech');monkeypatch.setenv('HOME','/home/dadtech')
    assert audio_session_users()==(user,user)


def test_managed_image_retains_two_sessions(monkeypatch):
    monkeypatch.setattr('skelly_ai.audio_sessions.pwd.getpwuid',lambda uid:account('skelly-ai',997))
    monkeypatch.setattr('skelly_ai.audio_sessions.pwd.getpwnam',lambda name:account(name,1000))
    assert audio_session_users()==('dadtech','skelly-ai')


def test_custom_helper_resolves_uid_home_and_pipewire_environment(monkeypatch):
    h,calls=load_helper(monkeypatch)
    uid,env=h._audio_session_env('custom_user_a')
    assert uid=='1000'
    assert 'HOME=/home/custom_user_a' in env and 'XDG_RUNTIME_DIR=/run/user/1000' in env
    assert 'PULSE_SERVER=unix:/run/user/1000/pulse/native' in env
    assert 'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus' in env
    # No missing skelly-ai lookup or unrelated dadtech service is required.
    assert h._audio_competitor('custom_user_a') is None


def test_uid_is_resolved_not_assumed(monkeypatch):
    h,calls=load_helper(monkeypatch,{'custom_user_a':account('custom_user_a',2345)})
    assert 'XDG_RUNTIME_DIR=/run/user/2345' in h._audio_session_env('custom_user_a')[1]


@pytest.mark.parametrize('service',['missing','root','bad/name'])
def test_missing_or_unsafe_configured_service_identity_is_rejected(monkeypatch,service):
    h,calls=load_helper(monkeypatch,{'root':account('root',0)},service=service)
    with pytest.raises(SystemExit):h._audio_session_env(service)


def test_caller_cannot_select_an_arbitrary_privileged_session(monkeypatch):
    h,calls=load_helper(monkeypatch)
    with pytest.raises(SystemExit,match='Unsupported'):h._audio_session_env('another-user')


def test_missing_secondary_image_account_is_not_a_repair_failure(monkeypatch):
    h,calls=load_helper(monkeypatch,{'skelly-ai':account('skelly-ai',997)},service='skelly-ai')
    assert h._audio_competitor('skelly-ai') is None


def test_custom_valid_session_prepare_exec_and_competitor_noop(monkeypatch):
    h,calls=load_helper(monkeypatch)
    monkeypatch.setattr(h.pathlib.Path,'exists',lambda path:True)
    captured=[]
    monkeypatch.setattr(h.os,'execvp',lambda executable,args:captured.append((executable,args)))
    h.audio_session_pause_competitor('custom_user_a')
    h.audio_session_resume_competitor('custom_user_a')
    h.audio_session_exec('wpctl',['--session','custom_user_a','status'])
    assert captured[0][1][:4]==['runuser','-u','custom_user_a','--']
    assert 'PULSE_SERVER=unix:/run/user/1000/pulse/native' in captured[0][1]
    assert not any('dadtech' in command for command in calls)
    assert not any('stop' in command for command in calls)


def test_api_wires_custom_session_for_speaker_external_and_playback(tmp_path,monkeypatch):
    from skelly_ai.api import create_app
    from skelly_ai.config import Settings
    from skelly_ai.hardware import SimulatedSkelly
    monkeypatch.setattr('skelly_ai.audio_sessions.audio_session_users',lambda:('custom_user_a','custom_user_a'))
    app=create_app(Settings(simulation=False,data_dir=tmp_path),hardware_client=SimulatedSkelly())
    assert app.state.classic_audio._pipewire_session=='custom_user_a'
    assert app.state.external_audio._pipewire_session=='custom_user_a'
    assert app.state.local_speech.status()['playback_session']=='custom_user_a'
    assert app.state.local_speech.status()['jaw_mirror_session']=='custom_user_a'


@pytest.mark.parametrize('user,uid',[('custom_user_b',2345),('prop_owner',1017),('show-user',1100)])
def test_helper_accepts_any_configured_custom_service_account(monkeypatch,user,uid):
    h,calls=load_helper(monkeypatch,{user:account(user,uid),'dadtech':account('dadtech',1001)},service=user)
    actual,env=h._audio_session_env(user)
    assert actual==str(uid)
    assert f'HOME=/home/{user}' in env
    assert f'XDG_RUNTIME_DIR=/run/user/{uid}' in env
    assert h._audio_competitor(user) is None
