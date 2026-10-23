from pathlib import Path
from skelly_ai.sensors import SensorLab


def test_sensor_status_handles_unreadable_offline_model_directory(tmp_path, monkeypatch):
    sensor = SensorLab(speech_model_path=tmp_path/'protected'/'model')
    monkeypatch.setattr(sensor, '_device_inventory', lambda: {'cameras':[], 'microphones':[]})
    original = Path.is_dir
    def inaccessible(path):
        if path == sensor.speech_model_path:
            raise PermissionError('test denied')
        return original(path)
    monkeypatch.setattr(Path, 'is_dir', inaccessible)
    status = sensor.status()
    assert status['microphone']['offline_transcription_available'] is False
    assert status['microphone']['speech_model'] == 'model'
