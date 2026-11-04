import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from skelly_ai.audio_priority import AudioPriorityGate, BackgroundDeferred
from skelly_ai.fpp_sync import FppPlayback, MediaTimeline


@pytest.mark.asyncio
async def test_foreground_preempts_and_waits_for_cleanup():
    gate = AudioPriorityGate()
    started, cleaned = asyncio.Event(), asyncio.Event()
    async def background():
        async with gate.background():
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0)
                cleaned.set()
    task = asyncio.create_task(background())
    await started.wait()
    async with gate:
        assert cleaned.is_set() and gate.foreground_busy
        with pytest.raises(BackgroundDeferred):
            async with gate.background():
                pass
    with pytest.raises(asyncio.CancelledError):
        await task
    async with gate.background():
        assert not gate.foreground_busy


@pytest.mark.asyncio
async def test_cancelled_foreground_waiter_does_not_lock_gate():
    gate = AudioPriorityGate()
    async with gate:
        task = asyncio.create_task(gate.__aenter__())
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert not gate.foreground_busy
    async with gate.background():
        pass


@pytest.mark.asyncio
async def test_fpp_playback_yields_and_resumes_current_timeline(tmp_path):
    from test_fpp_sync import packet
    (tmp_path/'Winter Workshop.wav').write_bytes(b'fixture')
    now = [0.]
    timeline = MediaTimeline(tmp_path,'10.10.10.19',clock=lambda:now[0])
    timeline.receive(packet(seconds=10), '10.10.10.19')
    class Speech:
        _lock = AudioPriorityGate()
        starts = []
        async def play_audio_file(self,path,jaw,**kwargs):
            async with self._lock.background():
                self.starts.append(kwargs['start_seconds']())
                await asyncio.Event().wait()
    speech = Speech()
    playback = FppPlayback(timeline,speech,SimpleNamespace(snapshot=lambda:SimpleNamespace(armed=True)))
    await playback.start()
    try:
        await asyncio.sleep(.25)
        assert speech.starts == [10]
        async with speech._lock:
            now[0] = 2
            await asyncio.sleep(.25)
            assert speech.starts == [10]
        await asyncio.sleep(.25)
        assert speech.starts == [10,12]
        timeline.receive(packet(1), '10.10.10.19')
        await asyncio.sleep(.25)
        assert not playback.status()['audio_active']
    finally:
        await playback.close()


@pytest.mark.asyncio
async def test_silent_stock_fails_closed(tmp_path):
    from test_fpp_sync import packet
    (tmp_path/'Winter Workshop.wav').write_bytes(b'fixture')
    timeline = MediaTimeline(tmp_path,'10.10.10.19')
    timeline.receive(packet(),'10.10.10.19')
    class Speech:
        _lock = AudioPriorityGate()
        async def play_audio_file(self,*args,**kwargs):
            pytest.fail('Stock silent playback must not start')
    playback = FppPlayback(timeline,Speech(),SimpleNamespace(snapshot=lambda:SimpleNamespace(armed=False)))
    await playback.start()
    await asyncio.sleep(.25)
    await playback.close()
    assert 'failed hardware validation' in playback.last_error


def test_wav_seek_uses_frame_position_not_wall_clock(tmp_path):
    import wave
    from skelly_ai.speech import LocalSpeech
    path = tmp_path/'seek.wav'
    with wave.open(str(path),'wb') as out:
        out.setnchannels(1);out.setsampwidth(2);out.setframerate(1000)
        out.writeframes(b'\0\0'*3000)
    LocalSpeech._trim_wav_to_position(path,1.25)
    with wave.open(str(path),'rb') as source:
        assert source.getnframes() == 1750
    LocalSpeech._trim_wav_to_position(path,99)
    with wave.open(str(path),'rb') as source:
        assert source.getnframes() == 0


@pytest.mark.asyncio
async def test_silent_dac_never_starts_speaker_process(monkeypatch):
    from skelly_ai.speech import LocalSpeech, SpeechUnavailable
    calls=[]
    async def forbidden(*args,**kwargs):
        pytest.fail('Silent DAC singing must never launch pw-play')
    monkeypatch.setattr(asyncio,'create_subprocess_exec',forbidden)
    class Jaw:
        def snapshot(self):return SimpleNamespace(armed=True)
        async def set_position(self,**kwargs):calls.append(kwargs)
    speech=LocalSpeech(frame_seconds=.001)
    result=await speech._play(Path('unused.wav'),[True,False],.002,Jaw(),silent=True)
    assert result['jaw_animated'] and calls == [{'jaw':255},{'jaw':0}]
    with pytest.raises(SpeechUnavailable,match='stock silent jaw'):
        await speech._play(Path('unused.wav'),[True],.001,SimpleNamespace(snapshot=lambda:SimpleNamespace(armed=False)),silent=True)


@pytest.mark.asyncio
async def test_stock_muting_hooks_cannot_bypass_failed_physical_validation(tmp_path):
    from test_fpp_sync import packet
    (tmp_path/'Winter Workshop.wav').write_bytes(b'fixture')
    timeline=MediaTimeline(tmp_path,'10.10.10.19')
    timeline.receive(packet(),'10.10.10.19')
    calls=[]
    async def mute():calls.append('mute')
    async def restore():calls.append('restore')
    class Speech:
        _lock=AudioPriorityGate()
        async def play_audio_file(self,path,jaw,**kwargs):
            assert kwargs['silent'] is False  # real waveform must reach stock jaw
            assert kwargs['target_override']() == 'skelly-sink'
            assert kwargs['before_play'] is mute and kwargs['after_play'] is restore
            calls.append('play')
    playback=FppPlayback(timeline,Speech(),SimpleNamespace(snapshot=lambda:SimpleNamespace(armed=False)),stock_before=mute,stock_after=restore,stock_target=lambda:'skelly-sink')
    await playback.start();await asyncio.sleep(.25);await playback.close()
    assert calls == []
    assert 'failed hardware validation' in playback.last_error


@pytest.mark.asyncio
async def test_audio_file_cleanup_restores_volume_after_preemption(tmp_path,monkeypatch):
    import wave
    from skelly_ai.speech import LocalSpeech
    source=tmp_path/'tone.wav'
    with wave.open(str(source),'wb') as stream:
        stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(8000);stream.writeframes(b'\0\0'*800)
    speech=LocalSpeech()
    monkeypatch.setattr(speech,'status',lambda:{'player_available':True})
    monkeypatch.setattr(speech,'_jaw_envelope',lambda path:([False],.1))
    started=asyncio.Event();calls=[]
    async def before():calls.append('mute')
    async def after():calls.append('restore')
    async def play(*args,**kwargs):
        started.set();await asyncio.Event().wait()
    monkeypatch.setattr(speech,'_play',play)
    task=asyncio.create_task(speech.play_audio_file(source,object(),background=True,before_play=before,after_play=after))
    await started.wait()
    async with speech._lock:
        assert calls==['mute','restore']
    with pytest.raises(asyncio.CancelledError):await task


@pytest.mark.asyncio
async def test_two_foreground_requests_do_not_interrupt_background_cleanup():
    gate=AudioPriorityGate();started=asyncio.Event();cleaning=asyncio.Event();release=asyncio.Event();completed=[]
    async def background():
        async with gate.background():
            started.set()
            try:await asyncio.Event().wait()
            finally:
                cleaning.set();await release.wait();completed.append('restored')
    async def foreground(label):
        async with gate:completed.append(label)
    bg=asyncio.create_task(background());await started.wait()
    one=asyncio.create_task(foreground('one'));await cleaning.wait()
    two=asyncio.create_task(foreground('two'));await asyncio.sleep(0)
    release.set();await asyncio.gather(one,two)
    assert completed==['restored','one','two']
    with pytest.raises(asyncio.CancelledError):await bg


@pytest.mark.asyncio
async def test_fpp_suppression_preserves_timeline_until_interaction_ends(tmp_path):
    from test_fpp_sync import packet
    (tmp_path/'Winter Workshop.wav').write_bytes(b'fixture')
    now=[0.];allowed=[True];starts=[]
    timeline=MediaTimeline(tmp_path,'10.10.10.19',clock=lambda:now[0])
    timeline.receive(packet(seconds=3),'10.10.10.19')
    class Speech:
        _lock=AudioPriorityGate()
        async def play_audio_file(self,path,jaw,**kwargs):
            async with self._lock.background():
                starts.append(kwargs['start_seconds']());await asyncio.Event().wait()
    playback=FppPlayback(timeline,Speech(),SimpleNamespace(snapshot=lambda:SimpleNamespace(armed=True)),ready=lambda:allowed[0])
    await playback.start()
    try:
        await asyncio.sleep(.25);allowed[0]=False;now[0]=1
        await asyncio.sleep(.25);assert not playback.status()['audio_active']
        now[0]=2;allowed[0]=True
        await asyncio.sleep(.25);assert starts==[3,5]
    finally:await playback.close()


def test_fpp_reuses_signed_jaw_timing_compensation(tmp_path):
    from test_fpp_sync import packet
    timeline=MediaTimeline(tmp_path,'10.10.10.19',clock=lambda:0.)
    timeline.receive(packet(seconds=2),'10.10.10.19')
    playback=FppPlayback(timeline,object(),object(),offset_seconds=.75)
    assert playback.playback_position()==2.75
    playback.offset_seconds=-.75
    assert playback.playback_position()==1.25
    playback.offset_seconds=-3
    assert playback.playback_position()==0


@pytest.mark.asyncio
async def test_no_match_handoff_stops_previous_output_within_supervisor_tick(tmp_path):
    from test_fpp_sync import packet
    (tmp_path/'Winter Workshop.wav').write_bytes(b'fixture')
    timeline=MediaTimeline(tmp_path,'10.10.10.19')
    timeline.receive(packet(),'10.10.10.19')
    started=asyncio.Event();stopped=asyncio.Event();paths=[]
    class Speech:
        _lock=AudioPriorityGate()
        async def play_audio_file(self,path,jaw,**kwargs):
            async with self._lock.background():
                paths.append(path.name);started.set()
                try:await asyncio.Event().wait()
                finally:stopped.set()
    playback=FppPlayback(timeline,Speech(),SimpleNamespace(snapshot=lambda:SimpleNamespace(armed=True)))
    await playback.start()
    try:
        await asyncio.wait_for(started.wait(),1)
        timeline.receive(packet(name='Absent.wav'),'10.10.10.19')
        assert not timeline.snapshot()['local_match']
        # Packet receipt and cancellation are distinct operations; don't assert
        # an instantaneous stop before the supervisor has run.
        await asyncio.wait_for(stopped.wait(),.5)
        await asyncio.sleep(0)
        assert paths==['Winter Workshop.wav']
        assert not playback.status()['audio_active']
    finally:await playback.close()


@pytest.mark.asyncio
async def test_close_during_cancellation_waits_for_cleanup_and_exits(tmp_path):
    from test_fpp_sync import packet
    (tmp_path/'Winter Workshop.wav').write_bytes(b'fixture')
    timeline=MediaTimeline(tmp_path,'10.10.10.19');timeline.receive(packet(),'10.10.10.19')
    started=asyncio.Event();cleaning=asyncio.Event();release=asyncio.Event();restored=[]
    class Speech:
        _lock=AudioPriorityGate()
        async def play_audio_file(self,path,jaw,**kw):
            async with self._lock.background():
                started.set()
                try:await asyncio.Event().wait()
                finally:
                    cleaning.set();await release.wait();restored.append(True)
    playback=FppPlayback(timeline,Speech(),SimpleNamespace(snapshot=lambda:SimpleNamespace(armed=True)))
    await playback.start();await asyncio.wait_for(started.wait(),1)
    timeline.receive(packet(1),'10.10.10.19');await asyncio.wait_for(cleaning.wait(),1)
    closing=asyncio.create_task(playback.close());await asyncio.sleep(0)
    assert not closing.done()
    release.set();await asyncio.wait_for(closing,1)
    assert restored==[True] and playback._worker is None and playback._audio is None


@pytest.mark.asyncio
async def test_short_same_song_can_replay_after_eof(tmp_path):
    from test_fpp_sync import packet
    (tmp_path/'Winter Workshop.wav').write_bytes(b'fixture')
    timeline=MediaTimeline(tmp_path,'10.10.10.19');timeline.receive(packet(event=0,seconds=0),'10.10.10.19');starts=[]
    class Speech:
        _lock=AudioPriorityGate()
        async def play_audio_file(self,path,jaw,**kw):
            async with self._lock.background():starts.append(path.name)
    playback=FppPlayback(timeline,Speech(),SimpleNamespace(snapshot=lambda:SimpleNamespace(armed=True)))
    await playback.start()
    try:
        await asyncio.sleep(.25);assert len(starts)==1
        timeline.receive(packet(event=1,seconds=.25),'10.10.10.19')
        timeline.receive(packet(event=0,seconds=0),'10.10.10.19')
        await asyncio.sleep(.25);assert len(starts)==2
    finally:await playback.close()


@pytest.mark.asyncio
async def test_repeated_supervisor_start_stop_no_task_or_gate_leak(tmp_path):
    from test_fpp_sync import packet
    (tmp_path/'Winter Workshop.wav').write_bytes(b'fixture')
    for _ in range(100):
        timeline=MediaTimeline(tmp_path,'10.10.10.19');timeline.receive(packet(),'10.10.10.19')
        started=asyncio.Event();finished=[]
        class Speech:
            _lock=AudioPriorityGate()
            async def play_audio_file(self,path,jaw,**kw):
                async with self._lock.background():
                    started.set()
                    try:await asyncio.Event().wait()
                    finally:await asyncio.sleep(0);finished.append(True)
        speech=Speech();p=FppPlayback(timeline,speech,SimpleNamespace(snapshot=lambda:SimpleNamespace(armed=True)))
        await p.start();await asyncio.wait_for(started.wait(),1)
        await asyncio.wait_for(p.close(),1)
        assert finished==[True] and p._worker is None and p._audio is None
        async with speech._lock:pass


@pytest.mark.asyncio
async def test_override_preempts_ai_and_resumes_after_fpp_cleanup(tmp_path):
    from test_fpp_sync import packet
    from test_perception import FakeSensors
    from skelly_ai.perception import PerceptionEngine
    (tmp_path/'Winter Workshop.wav').write_bytes(b'fixture')
    started=asyncio.Event();cleaned=asyncio.Event();gate=AudioPriorityGate();pause_states=[]
    engine=PerceptionEngine(FakeSensors([False]*1000),show_locked=lambda:False,camera_interval_seconds=.005)
    await engine.start()
    class Speech:
        _lock=gate
        async def play_audio_file(self,path,jaw,**kw):
            async with gate.background():
                started.set()
                try:await asyncio.Event().wait()
                finally:await asyncio.sleep(.01);cleaned.set()
    async def priority(eligible):
        if not eligible and started.is_set():assert cleaned.is_set()
        await engine.set_fpp_pause(eligible);pause_states.append(eligible)
    timeline=MediaTimeline(tmp_path,'10.10.10.19');timeline.receive(packet(),'10.10.10.19')
    p=FppPlayback(timeline,Speech(),SimpleNamespace(snapshot=lambda:SimpleNamespace(armed=True)),priority_update=priority)
    try:
        await p.start();await asyncio.wait_for(started.wait(),1)
        assert engine.status()['phase']=='paused_for_fpp'
        timeline.receive(packet(event=1),'10.10.10.19');await asyncio.sleep(.3)
        assert engine.status()['running'] and True in pause_states and False in pause_states
    finally:await p.close();await engine.stop()
