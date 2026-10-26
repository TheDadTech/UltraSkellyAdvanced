#!/usr/bin/env python3
"""Reversible, per-account USA WirePlumber policy migration (run unprivileged)."""
import json
import os
from pathlib import Path
import pwd
import sys

LEGACY = '''wireplumber.profiles = {
  main = {
    monitor.bluez = required
    monitor.bluez.seat-monitoring = disabled
  }
}
monitor.bluez.properties = {
  bluez5.roles = [ a2dp_sink a2dp_source ]
}
'''
OWNER = '''# Managed by UltraSkellyAdvanced: one Bluetooth audio owner.
wireplumber.profiles = {
  main = {
    monitor.bluez = required
    monitor.bluez.seat-monitoring = disabled
  }
}
'''
SECONDARY = '''# Managed by UltraSkellyAdvanced: Bluetooth belongs to the USA service.
wireplumber.profiles = {
  main = {
    monitor.bluez = disabled
    monitor.bluez-midi = disabled
  }
}
'''


def migrate(home: Path, role: str) -> bool:
    directory = home / '.config/wireplumber/wireplumber.conf.d'
    journal = home / '.config/wireplumber/usa-policy-recovery.json'
    if role == 'restore':
        if not journal.exists():
            return False
        entries = json.loads(journal.read_text())
        # Preflight all changes before restoring anything; preserve later edits.
        for name, record in entries.items():
            if name not in {'50-headless-bluetooth.conf', '90-usa-bluetooth-owner.conf'}:
                raise RuntimeError('Invalid policy recovery entry')
            path = directory / name
            if not path.is_file() or path.read_text() != record['after']:
                raise RuntimeError('Policy changed since migration; manual recovery required')
        for name, record in entries.items():
            path = directory / name
            if record['before'] is None:
                path.unlink()
            else:
                path.write_text(record['before'])
        journal.unlink()
        return True
    if role not in {'owner', 'secondary', 'fresh-secondary'}:
        raise ValueError('Unsupported audio policy role')
    name = '90-usa-bluetooth-owner.conf' if role == 'owner' else '50-headless-bluetooth.conf'
    path = directory / name
    if path.is_symlink() or journal.is_symlink():
        raise RuntimeError('Refusing symlinked policy file')
    before = path.read_text() if path.exists() else None
    after = OWNER if role == 'owner' else SECONDARY
    if before == after:
        return False
    if role == 'secondary' and before != LEGACY:
        # No proof this file was installed by USA: do not touch this account.
        return False
    if before is not None and role != 'secondary':
        raise RuntimeError('Custom policy occupies USA policy path; preserve it and resolve manually')
    directory.mkdir(parents=True, exist_ok=True)
    entries = json.loads(journal.read_text()) if journal.exists() else {}
    entries.setdefault(name, {'before': before, 'after': after})
    temp = journal.with_suffix('.tmp')
    temp.write_text(json.dumps(entries))
    temp.chmod(0o600)
    os.replace(temp, journal)
    temp = path.with_suffix('.tmp')
    temp.write_text(after)
    os.replace(temp, path)
    return True


if __name__ == '__main__':
    # No privileged writes through user-controlled home/config paths.
    if os.geteuid() == 0:
        raise SystemExit('Run policy migration as the target non-root account')
    try:
        changed = migrate(Path(pwd.getpwuid(os.geteuid()).pw_dir), sys.argv[1])
    except (OSError, ValueError, RuntimeError):
        raise SystemExit('USA audio policy migration could not complete. Preserve custom policy files and inspect the local recovery journal.') from None
    print('changed' if changed else 'unchanged')
