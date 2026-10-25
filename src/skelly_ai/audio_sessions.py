"""Resolve application audio ownership from the running service identity."""
import os
import pwd


def audio_session_users() -> tuple[str, str]:
    """Return (Skelly/jaw session, primary/external session).

    Packaged images retain their managed two-session topology. Custom-user
    installations use their service account, never USER/HOME from the caller.
    """
    account = pwd.getpwuid(os.geteuid())
    primary = account.pw_name
    if primary == 'skelly-ai':
        try:
            pwd.getpwnam('dadtech')
        except KeyError:
            return primary, primary
        return 'dadtech', primary
    return primary, primary
