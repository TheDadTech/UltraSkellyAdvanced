"""Foreground speech/media preempts background FPP without overlapping players."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager


class BackgroundDeferred(RuntimeError):
    pass


class AudioPriorityGate:
    def __init__(self) -> None:
        self._mutex = asyncio.Lock()
        self._background: asyncio.Task | None = None
        self._foreground_waiters = 0
        self._foreground_active = False

    @property
    def foreground_busy(self) -> bool:
        return self._foreground_active or self._foreground_waiters > 0

    async def __aenter__(self):
        self._foreground_waiters += 1
        try:
            if self._background is not None and not self._background.cancelling():
                self._background.cancel()
            await self._mutex.acquire()
            self._foreground_active = True
        finally:
            self._foreground_waiters -= 1
        return self

    async def __aexit__(self, *args):
        self._foreground_active = False
        self._mutex.release()

    @asynccontextmanager
    async def background(self):
        if self.foreground_busy:
            raise BackgroundDeferred('Foreground audio owns playback')
        await self._mutex.acquire()
        if self.foreground_busy:
            self._mutex.release()
            raise BackgroundDeferred('Foreground audio is waiting')
        self._background = asyncio.current_task()
        try:
            yield
        finally:
            self._background = None
            self._mutex.release()
