"""Exercise only the standalone validation code, never the privileged installer."""
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_legacy_bridge_copies_match_and_require_explicit_package():
    script = (ROOT/'scripts/install-updater-bridge.sh').read_text()
    assert script == (ROOT/'install-updater-bridge.sh').read_text()
    result = subprocess.run(['bash', str(ROOT/'scripts/install-updater-bridge.sh')],capture_output=True,text=True)
    assert result.returncode == 2 and 'PUBLISHED_SHA256' in result.stderr


def test_offline_recovery_archive_validator_rejects_traversal(tmp_path):
    script=(ROOT/'scripts/install-updater-bridge.sh').read_text()
    validator=script.split("<<'VALIDATE_ZIP'\n",1)[1].split('\nVALIDATE_ZIP',1)[0]
    archive=tmp_path/'release.zip'
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('../escape','unsafe')
    import sys
    result=subprocess.run([sys.executable,'-c',validator,str(archive),str(tmp_path/'extract'),'0.28.0'],capture_output=True,text=True)
    assert result.returncode != 0 and 'Unsafe ZIP entry' in result.stderr
    assert not (tmp_path/'escape').exists()
