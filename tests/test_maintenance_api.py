import hashlib
import io
import json
import subprocess
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient
from skelly_ai.api import create_app
from skelly_ai.config import Settings
from skelly_ai.updates import UpdateManager, UpdateError
from skelly_ai.backups import BackupManager
import pytest

PASSWORD = 'test-only-backup-password'
AUTH = ('operator', 'test-only-operator-password')


def client_for(tmp_path):
    return TestClient(create_app(Settings(data_dir=tmp_path, simulation=True, tts_password=AUTH[1])))


def release(version='0.28.2'):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as z:
        z.writestr('pyproject.toml', f'[project]\nname="skelly-ai"\nversion="{version}"')
        for name in ['deploy/bootstrap-pi.sh', 'deploy/usa-system-helper.py', 'src/skelly_ai/api.py', 'src/skelly_ai/__init__.py', 'src/skelly_ai/static/index.html']:
            z.writestr(name, 'test fixture')
    return stream.getvalue()


def test_backup_api_authenticated_round_trip_and_no_secret_in_preview(tmp_path):
    with client_for(tmp_path) as c:
        challenge = c.get('/api/backup/inventory')
        assert challenge.status_code == 200 and 'www-authenticate' not in challenge.headers
        interactive = c.get('/api/backup/inventory', headers={'X-USA-Interactive-Auth':'1'})
        assert interactive.status_code == 200 and 'www-authenticate' not in interactive.headers
        headers = {'X-Backup-Password': PASSWORD}
        r = c.post('/api/backup/download', headers=headers, auth=AUTH)
        assert r.status_code == 200 and r.headers['cache-control'] == 'no-store'
        encrypted = r.content
        r = c.post('/api/backup/inspect', headers=headers, content=encrypted, auth=AUTH)
        assert r.status_code == 200 and 'credentials.json' in r.json()['files']
        assert PASSWORD not in r.text
        assert c.post('/api/backup/restore', headers=headers, content=encrypted, auth=AUTH).status_code == 409
        r = c.post('/api/backup/restore', headers={**headers,'X-Restore-Confirm':'replace'}, content=encrypted, auth=AUTH)
        assert r.status_code == 200
        assert (tmp_path / 'backups' / r.json()['recovery']).is_file()
        assert c.post('/api/backup/inspect', headers={**headers, 'Origin':'https://evil.invalid'}, content=encrypted, auth=AUTH).status_code == 403


def test_backup_api_wrong_password_and_operation_guard(tmp_path):
    with client_for(tmp_path) as c:
        headers = {'X-Backup-Password': PASSWORD}
        encrypted = c.post('/api/backup/download', headers=headers, auth=AUTH).content
        assert c.post('/api/backup/inspect', headers={'X-Backup-Password':'wrong-password-test'}, content=encrypted, auth=AUTH).status_code == 422
        c.post('/api/operation/start', json={'mode':'classic'})
        assert c.post('/api/backup/restore', headers={**headers,'X-Restore-Confirm':'replace'}, content=encrypted, auth=AUTH).status_code == 409


def test_manual_verify_and_simulation_install_guard(tmp_path, monkeypatch):
    data = release()
    headers = {'X-USA-Version':'0.28.2', 'X-USA-SHA256':hashlib.sha256(data).hexdigest()}
    with client_for(tmp_path) as c:
        monkeypatch.setattr('skelly_ai.api.httpx.AsyncClient', lambda **kwargs: pytest.fail('manual ZIP must not contact GitHub'))
        assert c.post('/api/update/manual/verify', content=data, headers={**headers,'Origin':'https://other.invalid'}).status_code == 403
        r=c.post('/api/update/manual/verify', content=data, headers=headers)
        assert r.status_code == 200, r.text
        assert 'www-authenticate' not in r.headers
        token=r.json()['token']
        assert c.post('/api/update/manual/install', json={'token':token}).status_code == 409
        assert c.post('/api/update/manual/verify', content=data, headers={**headers,'X-USA-SHA256':'0'*64}).status_code == 422
        assert c.post('/api/update/manual/verify', content=data, headers={**headers,'X-USA-Version':'0.27.4'}).status_code == 409
        assert c.post('/api/update/manual/verify', content=data, headers={**headers,'X-USA-Version':'0.28.2-beta1'}).status_code == 409


def test_manual_install_uses_existing_helper_path_and_verified_bytes(tmp_path, monkeypatch):
    manager = UpdateManager(tmp_path/'data', tmp_path/'helper')
    archive=tmp_path/'release.zip'; archive.write_bytes(release())
    result=manager.verify_manual(archive,'0.28.2',hashlib.sha256(archive.read_bytes()).hexdigest())
    # A modification to extracted code cannot survive the final archive verification.
    (manager._manual['source']/'src/skelly_ai/api.py').write_text('tampered')
    calls=[]
    def run(args,**kwargs):
        calls.append(args)
        assert Path(args[5]).is_relative_to(manager.update_dir/'0.28.2'/'source')
        assert (Path(args[5])/'src/skelly_ai/api.py').read_text() == 'test fixture'
        return subprocess.CompletedProcess(args,0)
    monkeypatch.setattr('skelly_ai.updates.subprocess.run',run)
    manager.install_manual(result['token'],current_version='0.27.4')
    assert calls[0][3:5] == ['update-install','0.28.2']
    with pytest.raises(UpdateError):
        manager.install_manual(result['token'],current_version='0.27.4')


def test_manual_corrupt_archive_never_calls_helper(tmp_path, monkeypatch):
    manager=UpdateManager(tmp_path/'data',tmp_path/'helper')
    archive=tmp_path/'release.zip'; archive.write_bytes(release())
    verified=manager.verify_manual(archive,'0.28.2',hashlib.sha256(archive.read_bytes()).hexdigest())
    (manager._manual['stage']/'release.zip').write_bytes(b'corrupt')
    monkeypatch.setattr('skelly_ai.updates.subprocess.run',lambda *a,**k:pytest.fail('helper must not run'))
    with pytest.raises(UpdateError,match='changed'):
        manager.install_manual(verified['token'],current_version='0.27.4')


def test_health_simulation_is_safe_and_secret_free(tmp_path, monkeypatch):
    monkeypatch.setattr('skelly_ai.api.collect_diagnostics',lambda:pytest.fail('no hardware probes in simulation'))
    with client_for(tmp_path) as c:
        r=c.get('/api/system/health')
        assert r.status_code == 200, r.text
        assert r.json()['simulation'] is True
        assert AUTH[1] not in r.text
        assert c.get('/api/diagnostics').status_code == 200


def test_connectivity_success_failure_and_persistence(tmp_path, monkeypatch):
    class Response:
        def raise_for_status(self): pass
        def json(self): return {'version':'0.28.2','package_url':'https://example.test/usa.zip','sha256':'0'*64}
    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def get(self,*args): return Response()
    monkeypatch.setattr('skelly_ai.api.httpx.AsyncClient',lambda **kwargs:Client())
    with client_for(tmp_path) as c:
        r=c.post('/api/update/check')
        assert r.status_code == 200
        info=r.json()['connectivity']
        assert info['stable']=='0.28.2' and info['reachable'] is True and info['last_success']
    import httpx
    class Unreachable(Client):
        async def get(self,*args): raise httpx.ConnectError('test network failure')
    monkeypatch.setattr('skelly_ai.api.httpx.AsyncClient',lambda **kwargs:Unreachable())
    with client_for(tmp_path) as c:
        assert c.post('/api/update/check').status_code == 503
        info=c.get('/api/update/status').json()['connectivity']
        assert info['reachable'] is False and info['stable']=='0.28.2'
        assert info['last_success']
        assert 'test network failure' not in info['error']


def test_recovery_copy_list_and_authenticated_download(tmp_path):
    with client_for(tmp_path) as c:
        headers={'X-Backup-Password':PASSWORD}
        data=c.post('/api/backup/download',headers=headers,auth=AUTH).content
        restored=c.post('/api/backup/restore',content=data,headers={**headers,'X-Restore-Confirm':'replace'},auth=AUTH).json()
        files=c.get('/api/backup/recoveries',auth=AUTH).json()['files']
        assert files[0]['name']==restored['recovery']
        path='/api/backup/recovery/'+restored['recovery']
        assert c.get(path).status_code == 200
        r=c.get(path,auth=AUTH)
        assert r.status_code == 200 and r.content.startswith(BackupManager.MAGIC)
        assert r.headers['cache-control']=='no-store'


def test_manual_expired_token_and_duplicate_zip_entries(tmp_path, monkeypatch):
    manager=UpdateManager(tmp_path/'data',tmp_path/'helper')
    archive=tmp_path/'release.zip'; archive.write_bytes(release())
    verified=manager.verify_manual(archive,'0.28.2',hashlib.sha256(archive.read_bytes()).hexdigest())
    manager._manual['expires']=0
    monkeypatch.setattr('skelly_ai.updates.subprocess.run',lambda *a,**k:pytest.fail('no helper'))
    with pytest.raises(UpdateError):
        manager.install_manual(verified['token'],current_version='0.27.4')
    with zipfile.ZipFile(archive,'a') as z:
        with pytest.warns(UserWarning):
            z.writestr('deploy/bootstrap-pi.sh','replacement')
    with pytest.raises(UpdateError,match='unsafe'):
        manager.verify_manual(archive,'0.28.2',hashlib.sha256(archive.read_bytes()).hexdigest())


def test_unicode_backup_password_and_effective_credential_recovery(tmp_path):
    import base64
    from pydantic import SecretStr
    password='backup-with-unicode-☃-password'
    settings=Settings(data_dir=tmp_path,simulation=True,tts_password=AUTH[1],groq_api_key=SecretStr('test-env-only-groq-value'))
    with TestClient(create_app(settings)) as c:
        headers={'X-Backup-Password-Encoded':base64.b64encode(password.encode()).decode()}
        backup=c.post('/api/backup/download',headers=headers,auth=AUTH)
        assert backup.status_code==200
        files=BackupManager(tmp_path).inspect(backup.content,password)
        assert json.loads(files['credentials.json'])['groq_api_key']=='test-env-only-groq-value'
        result=c.post('/api/backup/restore',headers={**headers,'X-Restore-Confirm':'replace'},content=backup.content,auth=AUTH)
        assert result.status_code==200
        recovered=BackupManager(tmp_path).inspect((tmp_path/'backups'/result.json()['recovery']).read_bytes(),password)
        assert json.loads(recovered['credentials.json'])['groq_api_key']=='test-env-only-groq-value'


def test_legacy_welcome_settings_are_retained_but_greeting_is_disabled(tmp_path):
    (tmp_path/'operation-settings.json').write_text('{"welcome_enabled":true,"welcome_message":"Legacy greeting","nag_mode":"media","listening_sensitivity":61}')
    app=create_app(Settings(data_dir=tmp_path,simulation=True))
    with TestClient(app) as c:
        assert app.state.perception._welcomer is None
        settings=c.get('/api/status').json()['operation']['settings']
        assert settings['welcome_message']=='Legacy greeting'
        assert settings['listening_sensitivity']==61 and settings['nag_mode']=='media'


def test_backup_lan_and_nginx_access_without_operator_login(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, simulation=True, tts_password='legacy-unused-password'))
    for peer, headers in [('192.168.1.25', {}), ('127.0.0.1', {'X-Forwarded-For':'192.168.1.25','X-Real-IP':'192.168.1.25'})]:
        with TestClient(app, client=(peer, 50000)) as c:
            r = c.get('/api/backup/inventory', headers=headers)
            assert r.status_code == 200 and 'www-authenticate' not in r.headers
            assert c.post('/api/backup/download', headers=headers).status_code == 422
            assert c.post('/api/backup/download', headers={**headers,'X-Backup-Password':PASSWORD,'Origin':'https://other.invalid'}).status_code == 403
    with TestClient(app, client=('8.8.8.8', 50000)) as c:
        assert c.get('/api/backup/inventory', headers={'X-Forwarded-For':'192.168.1.25'}).status_code == 403
