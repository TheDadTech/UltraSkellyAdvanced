"""Exercise real recovery workers against isolated filesystem trees.

Only bootstrap/service/HTTP boundaries are simulated; backup, swaps, restores,
rollback metadata and preservation use actual files. No production paths used.
"""
import importlib.util
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def worker(tmp_path):
    spec = importlib.util.spec_from_file_location('isolated_update_helper', Path(__file__).parents[1] / 'deploy/usa-system-helper.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    def path(value):
        value = Path(value)
        return tmp_path / value.relative_to('/') if value.is_absolute() and not value.is_relative_to(tmp_path) else value
    helper.pathlib = SimpleNamespace(Path=path)
    helper.DATA_DIR = path('/var/lib/skelly-ai')
    helper.DATA_DIR.mkdir(parents=True)
    helper.UPDATE_STATUS = helper.DATA_DIR / 'update-status.json'
    helper.ROLLBACK_STATE = helper.DATA_DIR / 'update-rollback.json'
    active = path('/opt/skelly-ai/venv')
    active.mkdir(parents=True)
    system_files = [path(p) for p in ['/usr/local/libexec/usa-system-helper', '/etc/systemd/system/skelly-ai.service', '/etc/systemd/system/usa-network.service', '/etc/nginx/sites-available/usa']]
    for p in system_files:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('original-system-file')
    saved = {n: b'unchanged-test-data' for n in ['credentials.json', 'operation-settings.json', 'media/visitor.wav']}
    for n, data in saved.items():
        p=helper.DATA_DIR/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    mode = {'install_fail': False, 'nginx_fail': False, 'health_fail': False}
    def bootstrap(*args, **kwargs):
        (active/'version').write_text('0.28.0')
        for p in system_files:p.write_text('updated-system-file')
        return subprocess.CompletedProcess(args, 1 if mode['install_fail'] else 0, '', 'deliberate bootstrap failure' if mode['install_fail'] else '')
    helper.subprocess = SimpleNamespace(run=bootstrap)
    def run(*args, **kwargs):
        return subprocess.CompletedProcess(args, 1 if args[:2]==('nginx','-t') and mode['nginx_fail'] else 0, 'skelly-ai' if args[:2]==('systemctl','show') else '', 'deliberate nginx failure')
    helper.run = run
    clock = [0]
    helper.time = SimpleNamespace(monotonic=lambda:clock[0],sleep=lambda n:clock.__setitem__(0,clock[0]+n),time=lambda:1000)
    class Response:
        status=200
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,*args):return self.data
    def urlopen(url, **kwargs):
        r=Response()
        r.data = json.dumps({'version':'unhealthy' if mode['health_fail'] else (active/'version').read_text()}).encode() if url.endswith('/api/health') else b'<!doctype html><html>Dashboard</html>'
        return r
    helper.urllib = SimpleNamespace(request=SimpleNamespace(urlopen=urlopen))
    def preserved():
        assert all((helper.DATA_DIR/n).read_bytes()==v for n,v in saved.items())
    return helper,active,system_files,mode,preserved


@pytest.mark.parametrize('previous',['0.27.4','0.28.3-beta4'])
def test_real_worker_install_and_manual_rollback_preserve_data(worker,previous):
    h,active,system,mode,preserved=worker
    (active/'version').write_text(previous)
    h.update_install_worker('0.28.0',str(active.parent/'staged-source'),previous)
    assert json.loads(h.UPDATE_STATUS.read_text())['state']=='succeeded'
    assert (active/'version').read_text()=='0.28.0'
    assert json.loads(h.ROLLBACK_STATE.read_text())['previous_version']==previous
    preserved()
    h.update_rollback_worker('0.28.0',previous)
    assert json.loads(h.UPDATE_STATUS.read_text())['state']=='rolled_back'
    assert (active/'version').read_text()==previous
    assert all(p.read_text()=='original-system-file' for p in system)
    assert not json.loads(h.ROLLBACK_STATE.read_text())['available']
    preserved()


@pytest.mark.parametrize('failure',['install_fail','nginx_fail','health_fail'])
def test_real_worker_failed_update_restores_previous_application(worker,failure):
    h,active,system,mode,preserved=worker
    (active/'version').write_text('0.27.4');mode[failure]=True
    h.update_install_worker('0.28.0',str(active.parent/'staged-source'),'0.27.4')
    assert json.loads(h.UPDATE_STATUS.read_text())['state']=='failed'
    assert (active/'version').read_text()=='0.27.4'
    assert all(p.read_text()=='original-system-file' for p in system)
    preserved()


def test_real_worker_failed_rollback_restores_working_current_installation(worker):
    h,active,system,mode,preserved=worker
    (active/'version').write_text('0.27.4')
    h.update_install_worker('0.28.0',str(active.parent/'staged-source'),'0.27.4')
    mode['health_fail']=True
    h.update_rollback_worker('0.28.0','0.27.4')
    assert json.loads(h.UPDATE_STATUS.read_text())['state']=='failed'
    assert (active/'version').read_text()=='0.28.0'
    assert all(p.read_text()=='updated-system-file' for p in system)
    preserved()
