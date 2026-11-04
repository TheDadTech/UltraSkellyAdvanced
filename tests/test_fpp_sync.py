import math
import struct

import pytest

from skelly_ai.fpp_sync import InvalidSyncPacket, MediaTimeline, decode_media_sync


def packet(event=2, name='Winter Workshop.wav', seconds=12.5, file_type=1):
    payload = struct.pack('<BBIf', event, file_type, 0, seconds) + name.encode() + b'\0'
    return struct.pack('<4sBH', b'FPPD', 1, len(payload)) + payload


def test_wire_media_and_non_media():
    result = decode_media_sync(packet())
    assert (result.event, result.filename, result.position) == ('sync', 'Winter Workshop.wav', 12.5)
    assert decode_media_sync(packet(file_type=0)) is None
    assert decode_media_sync(struct.pack('<4sBH', b'FPPD', 6, 0)) is None


@pytest.mark.parametrize('data', [b'', b'FPPD', packet()[:-1], b'XXXX'+packet()[4:],
    packet(name='../secret.wav'), packet(name='/etc/passwd'), packet(name='a\\b.wav'),
    packet(name='.'), packet(name=''), packet(name='a\0b.wav'), packet(name='a\nb.wav'),
    packet(seconds=math.nan), packet(seconds=math.inf), packet(seconds=-1),
    packet(seconds=86401), packet(event=9), packet(file_type=9)])
def test_reject_malformed_or_unsafe(data):
    with pytest.raises(InvalidSyncPacket):
        decode_media_sync(data)


def test_timeline_continues_during_foreground_and_resyncs(tmp_path):
    now = [10.0]
    (tmp_path/'Winter Workshop.wav').write_bytes(b'fixture')
    timeline = MediaTimeline(tmp_path, '10.10.10.19', clock=lambda: now[0])
    assert timeline.receive(packet(), '10.10.10.19')
    assert timeline.snapshot()['eligible']
    now[0] += 3  # a foreground interaction doesn't pause the FPP clock
    assert timeline.position() == 15.5
    timeline.receive(packet(seconds=16), '10.10.10.19')
    assert timeline.position() == 16
    now[0] += 6
    assert not timeline.snapshot()['eligible']  # stale sync fails closed


def test_no_match_wrong_master_and_safe_matching(tmp_path):
    timeline = MediaTimeline(tmp_path, '10.10.10.19')
    assert not timeline.receive(packet(), '10.10.10.2')
    assert timeline.filename is None
    timeline.receive(packet(), '10.10.10.19')
    assert not timeline.snapshot()['local_match']
    outside = tmp_path.parent/'outside.wav'
    outside.write_bytes(b'fixture')
    (tmp_path/'Winter Workshop.wav').symlink_to(outside)
    assert timeline.local_file() is None


def test_open_and_unrelated_stop_do_not_interrupt(tmp_path):
    now = [0.0]
    timeline = MediaTimeline(tmp_path, '10.10.10.19', clock=lambda: now[0])
    timeline.receive(packet(0), '10.10.10.19')
    timeline.receive(packet(3, 'Another.wav'), '10.10.10.19')
    timeline.receive(packet(1, 'Another.wav'), '10.10.10.19')
    assert timeline.filename == 'Winter Workshop.wav' and timeline.playing
    now[0] = 2
    timeline.receive(packet(1), '10.10.10.19')
    assert not timeline.playing and timeline.position() == 14.5


def test_api_reports_disabled_receiver_and_no_fake_playback(tmp_path):
    from fastapi.testclient import TestClient
    from skelly_ai.api import create_app
    from skelly_ai.config import Settings
    app = create_app(Settings(_env_file=None, simulation=True, data_dir=tmp_path))
    with TestClient(app) as client:
        status = client.get('/api/fpp/status').json()
        assert status == {'enabled': False, 'configured': False, 'listening': False, 'connected': False, 'override_ai': False}
        assert client.get('/api/status').json()['fpp_sync'] == status


def test_api_configured_receiver_and_invalid_master(tmp_path):
    from fastapi.testclient import TestClient
    from pydantic import ValidationError
    from skelly_ai.api import create_app
    from skelly_ai.config import Settings
    with pytest.raises(ValidationError):
        Settings(_env_file=None, fpp_master_ip='not-a-host')
    app = create_app(Settings(_env_file=None, simulation=True, data_dir=tmp_path,
                              fpp_master_ip='10.10.10.19'))
    with TestClient(app) as client:
        status = client.get('/api/fpp/status').json()
        assert status['configured'] and not status['listening']
        assert status['playback_implemented'] is False
        assert status['sync_recent'] is False


@pytest.mark.asyncio
async def test_datagram_receiver_closes_socket_without_hardware(tmp_path, monkeypatch):
    import asyncio
    from skelly_ai.fpp_sync import MultiSyncListener
    timeline = MediaTimeline(tmp_path, '127.0.0.1')
    listener = MultiSyncListener(timeline)
    listener.datagram_received(packet(), ('127.0.0.1', 12345))
    assert timeline.snapshot()['accepted_packets'] == 1
    listener.datagram_received(packet(), ('10.10.10.2', 12345))
    assert timeline.snapshot()['ignored_packets'] == 1
    class Transport:
        closed = False
        def close(self):
            self.closed = True
    transport = Transport()
    listener.transport = transport
    listener.close()
    listener.close()
    assert transport.closed and listener.transport is None


def test_real_fpp_10_3_media_packet_captured_on_usa():
    # Actual Main -> USA datagram captured during an authorized media-only test.
    wire = bytes.fromhex('465050440119000201000000003d0f023f48616c6c656c756a61682e6d703300')
    decoded = decode_media_sync(wire)
    assert decoded.filename == 'Hallelujah.mp3'
    assert decoded.event == 'sync'
    assert decoded.position == pytest.approx(.508045, abs=.000001)


def test_unrelated_preload_and_stop_do_not_keep_stale_audio_alive(tmp_path):
    now=[0.0];t=MediaTimeline(tmp_path,'10.10.10.19',clock=lambda:now[0])
    (tmp_path/'Winter Workshop.wav').write_bytes(b'fixture')
    t.receive(packet(seconds=0),'10.10.10.19');now[0]=6
    for event in [1,3]:
        t.receive(packet(event=event,name='Other song.wav'),'10.10.10.19')
        assert not t.snapshot()['playing'] and not t.snapshot()['eligible']
