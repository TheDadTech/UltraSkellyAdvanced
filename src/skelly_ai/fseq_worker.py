"""Bounded subprocess for untrusted FSEQ parsing and pulse generation."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sys


async def run_worker(mode: str, *args: str, timeout: float = 60) -> None:
    environment = {k: os.environ[k] for k in ('PATH', 'PYTHONPATH', 'LANG', 'LC_ALL') if k in os.environ}
    process = await asyncio.create_subprocess_exec(
        sys.executable, '-m', 'skelly_ai.fseq_worker', mode, *map(str, args),
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE, env=environment,
    )
    try:
        _, error = await asyncio.wait_for(process.communicate(), timeout)
        if process.returncode:
            raise ValueError(error.decode(errors='replace')[:500].strip()
                             or 'Sequence processing exceeded its resource limits')
    except BaseException:
        if process.returncode is None:
            process.kill()
        await process.wait()
        raise


def main() -> int:
    import resource
    os.nice(10)
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024**2,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (40, 40))
    resource.setrlimit(resource.RLIMIT_FSIZE, (100 * 1024**2,) * 2)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    from .fseq_import import inspect, render
    try:
        mode, *args = sys.argv[1:]
        if mode == 'inspect':
            source, target = map(Path, args)
            result = inspect(source)
            with target.open('x', encoding='utf-8') as output:
                target.chmod(0o600)
                json.dump(result, output)
        elif mode == 'render':
            source, track, offset, target = args
            render(json.loads(Path(source).read_text()), track, Path(target), int(offset))
        else:
            raise ValueError('Invalid sequence processing operation')
        return 0
    except (ValueError, OSError, MemoryError, KeyError, TypeError) as exc:
        print(str(exc)[:400] or 'Sequence processing exceeded its resource limits', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
