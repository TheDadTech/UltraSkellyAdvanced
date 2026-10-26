"""All USA Bluetooth playback belongs to its configured non-root service account."""
import os
from pathlib import Path
import pwd

# Retained for compatibility with earlier installations; it no longer assigns owners.
ROLE_FILE = Path('/etc/skelly-ai/audio-sessions.json')


def audio_session_users() -> tuple[str, str]:
    account = pwd.getpwuid(os.geteuid())
    if account.pw_uid == 0:
        raise RuntimeError("USA audio must run as a non-root service account")
    return account.pw_name, account.pw_name
