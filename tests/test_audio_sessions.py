"""Synthetic account and permission fixtures; never read customer identities."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import stat
import subprocess
import pytest
from skelly_ai.audio_sessions import audio_session_users

SERVICE='testoperator'
SPEAKER='audio_test_user'
SECONDARY='secondary_test_user'


def account(name,uid):
    return SimpleNamespace(pw_name=name,pw_uid=uid,pw_dir=f'/home/{name}')


class RoleFile:
    def __init__(self,roles=None,owner=0,mode=stat.S_IFREG|0o644):
        self.roles=roles;self.owner=owner;self.mode=mode
    def lstat(self):
        if self.roles is None:raise FileNotFoundError()
        return SimpleNamespace(st_uid=self.owner,st_mode=self.mode)
    def read_text(self):return json.dumps(self.roles)


class RuntimePath:
    def __init__(self,path,owner=None,permissions=0o700,socket_owner=None):
        self.path=str(path);self.uid=int(self.path.split('/')[3])
        self.owner=self.uid if owner is None else owner
        self.permissions=permissions;self.socket_owner=socket_owner
    def exists(self):return True
    def __truediv__(self,name):return RuntimePath(self.path+'/'+name,self.owner,self.permissions,self.socket_owner)
    def lstat(self):
        directory=len(self.path.split('/'))==4
        owner=self.owner if directory or self.socket_owner is None else self.socket_owner
        return SimpleNamespace(st_uid=owner,st_mode=(stat.S_IFDIR|self.permissions) if directory else (stat.S_IFSOCK|0o600))


def load_helper(monkeypatch,users=None,service=SERVICE,roles=None,role_owner=0,role_mode=stat.S_IFREG|0o644,runtime_owner=None,permissions=0o700,socket_owner=None):
    spec=importlib.util.spec_from_file_location('synthetic_audio_helper',Path(__file__).parents[1]/'deploy/usa-system-helper.py')
    h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
    users=users if users is not None else {SERVICE:account(SERVICE,2620),SECONDARY:account(SECONDARY,4621)}
    def getpwnam(name):
        if name not in users:raise KeyError(name)
        return users[name]
    monkeypatch.setattr(h,'pwd',SimpleNamespace(getpwnam=getpwnam,getpwuid=lambda uid:next(a for a in users.values() if a.pw_uid==uid)))
    role_file=RoleFile(roles,role_owner,role_mode)
    def path(value):
        if str(value)=='/etc/skelly-ai/audio-sessions.json':return role_file
        if str(value).startswith('/run/user/'):
            return RuntimePath(value,runtime_owner,permissions,socket_owner)
        raise AssertionError('Unexpected filesystem access')
    monkeypatch.setattr(h,'pathlib',SimpleNamespace(Path=path))
    calls=[]
    def run(*args,**kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args,0,service if args[:2]==('systemctl','show') else '', '')
    monkeypatch.setattr(h,'run',run)
    return h,calls


@pytest.mark.parametrize('user,uid',[(SERVICE,2620),(SPEAKER,3781),(SECONDARY,4621),('test-operator',5792)])
def test_custom_service_identity_ignores_caller_environment(monkeypatch,user,uid):
    monkeypatch.setattr('skelly_ai.audio_sessions.os.geteuid',lambda:uid)
    monkeypatch.setattr('skelly_ai.audio_sessions.pwd.getpwuid',lambda value:account(user,value))
    monkeypatch.setattr('skelly_ai.audio_sessions.ROLE_FILE',RoleFile())
    monkeypatch.setenv('USER',SECONDARY);monkeypatch.setenv('HOME',f'/home/{SECONDARY}')
    assert audio_session_users()==(user,user)


@pytest.mark.parametrize('owner,mode,expected',[(0,stat.S_IFREG|0o644,SPEAKER),(2620,stat.S_IFREG|0o644,SERVICE),(0,stat.S_IFREG|0o666,SERVICE),(0,stat.S_IFLNK|0o777,SERVICE)])
def test_speaker_role_requires_root_owned_nonwritable_regular_metadata(monkeypatch,owner,mode,expected):
    monkeypatch.setattr('skelly_ai.audio_sessions.pwd.getpwuid',lambda uid:account(SERVICE,2620))
    monkeypatch.setattr('skelly_ai.audio_sessions.pwd.getpwnam',lambda name:account(name,3781))
    monkeypatch.setattr('skelly_ai.audio_sessions.ROLE_FILE',RoleFile({'service_user':SERVICE,'speaker_user':SPEAKER},owner,mode))
    assert audio_session_users()==(expected,SERVICE)


@pytest.mark.parametrize('user,uid',[(SERVICE,2620),(SPEAKER,3781),(SECONDARY,4621)])
def test_custom_helper_resolves_each_uid_home_and_socket_environment(monkeypatch,user,uid):
    users={user:account(user,uid),'other_test_user':account('other_test_user',6803)}
    h,calls=load_helper(monkeypatch,users,service=user)
    actual,env=h._audio_session_env(user)
    assert actual==str(uid)
    assert f'HOME=/home/{user}' in env
    assert f'XDG_RUNTIME_DIR=/run/user/{uid}' in env
    assert f'PULSE_SERVER=unix:/run/user/{uid}/pulse/native' in env
    assert f'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus' in env
    assert h._audio_competitor(user) is None


@pytest.mark.parametrize('service',['missing_test_user','root','invalid/name'])
def test_unavailable_or_unsafe_service_identity_is_rejected(monkeypatch,service):
    h,calls=load_helper(monkeypatch,{'root':account('root',0)},service=service)
    with pytest.raises(SystemExit):h._audio_session_env(service)


def test_caller_cannot_authorize_secondary_account_via_environment(monkeypatch):
    h,calls=load_helper(monkeypatch)
    monkeypatch.setenv('USER',SECONDARY);monkeypatch.setenv('SUDO_USER',SECONDARY)
    with pytest.raises(SystemExit,match='Unsupported'):h._audio_session_env(SECONDARY)


@pytest.mark.parametrize('role_owner,role_mode,allowed',[(0,stat.S_IFREG|0o644,True),(2620,stat.S_IFREG|0o644,False),(0,stat.S_IFREG|0o666,False),(0,stat.S_IFLNK|0o777,False)])
def test_helper_only_accepts_explicit_trusted_secondary_role(monkeypatch,role_owner,role_mode,allowed):
    users={SERVICE:account(SERVICE,2620),SPEAKER:account(SPEAKER,3781)}
    h,calls=load_helper(monkeypatch,users,roles={'service_user':SERVICE,'speaker_user':SPEAKER},role_owner=role_owner,role_mode=role_mode)
    assert (SPEAKER in h._audio_role_users()[1]) is allowed


def test_missing_configured_secondary_is_not_a_primary_repair_failure(monkeypatch):
    h,calls=load_helper(monkeypatch,{SERVICE:account(SERVICE,2620)},roles={'service_user':SERVICE,'speaker_user':SPEAKER})
    assert h._audio_competitor(SERVICE) is None


def test_custom_session_prepare_and_execution_do_not_touch_secondary_or_home(monkeypatch):
    h,calls=load_helper(monkeypatch)
    captured=[]
    monkeypatch.setattr(h,'os',SimpleNamespace(execvp=lambda exe,args:captured.append((exe,args))))
    h.audio_session_pause_competitor(SERVICE)
    h.audio_session_resume_competitor(SERVICE)
    h.audio_session_exec('wpctl',['--session',SERVICE,'status'])
    assert captured[0][1][:4]==['runuser','-u',SERVICE,'--']
    assert 'PULSE_SERVER=unix:/run/user/2620/pulse/native' in captured[0][1]
    assert not any(SECONDARY in command for command in calls)
    assert not any('stop' in command for command in calls)
    assert not any(command[0] in {'useradd','usermod','chown'} for command in calls)


@pytest.mark.parametrize('options',[{'runtime_owner':4621},{'permissions':0o777},{'socket_owner':4621}])
def test_wrong_runtime_or_socket_ownership_and_permissions_are_rejected(monkeypatch,options):
    h,calls=load_helper(monkeypatch,**options)
    with pytest.raises(SystemExit,match='unsafe ownership'):h._audio_session_env(SERVICE)


def test_api_routes_custom_speaker_external_and_playback_to_service(tmp_path,monkeypatch):
    from skelly_ai.api import create_app
    from skelly_ai.config import Settings
    from skelly_ai.hardware import SimulatedSkelly
    monkeypatch.setattr('skelly_ai.audio_sessions.audio_session_users',lambda:(SERVICE,SERVICE))
    app=create_app(Settings(simulation=False,data_dir=tmp_path),hardware_client=SimulatedSkelly())
    assert app.state.classic_audio._pipewire_session==SERVICE
    assert app.state.external_audio._pipewire_session==SERVICE
    assert app.state.local_speech.status()['playback_session']==SERVICE
    assert app.state.local_speech.status()['jaw_mirror_session']==SERVICE


def test_numeric_systemd_service_uid_resolves_to_canonical_account(monkeypatch):
    h,calls=load_helper(monkeypatch,service='2620')
    assert h._configured_audio_service_user()==SERVICE
    assert h._audio_session_env(SERVICE)[0]=='2620'


def test_stale_role_metadata_cannot_authorize_another_service(monkeypatch):
    h,calls=load_helper(monkeypatch,roles={'service_user':SECONDARY,'speaker_user':SECONDARY})
    assert h._audio_role_users()[1]=={SERVICE}
