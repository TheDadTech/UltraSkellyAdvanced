"""Resolve audio roles from service identity and trusted installer metadata."""
import json
import os
from pathlib import Path
import pwd
import stat

ROLE_FILE = Path('/etc/skelly-ai/audio-sessions.json')


def audio_session_users() -> tuple[str, str]:
    """Return (speaker/jaw session, primary session), with no name assumptions."""
    primary = pwd.getpwuid(os.geteuid()).pw_name
    try:
        info = ROLE_FILE.lstat()
        if info.st_uid != 0 or info.st_mode & 0o022 or not stat.S_ISREG(info.st_mode):
            return primary, primary
        roles = json.loads(ROLE_FILE.read_text())
        if not isinstance(roles, dict):
            return primary, primary
        speaker = roles['speaker_user']
        if roles.get('service_user') != primary or not isinstance(speaker, str):
            return primary, primary
        if pwd.getpwnam(speaker).pw_uid == 0:
            return primary, primary
        return speaker, primary
    except (OSError, ValueError, KeyError, TypeError):
        return primary, primary
