"""Atomic mode-0600 persistence for validated, non-secret feature settings."""
import os
from pathlib import Path
import tempfile


class ValidatedSettingsStore:
    def __init__(self, path: Path, model, defaults=None):
        self.path = Path(path)
        self.model = model
        self.defaults = defaults or model()

    def load(self):
        if not self.path.exists():
            return self.defaults.model_copy(deep=True)
        try:
            return self.model.model_validate_json(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            # Invalid data must never enable a feature.
            return self.model()

    def save(self, settings):
        settings = self.model.model_validate(settings)
        self.path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        fd, filename = tempfile.mkstemp(prefix='.'+self.path.stem+'-',dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                stream.write(settings.model_dump_json())
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(filename, self.path)
        finally:
            Path(filename).unlink(missing_ok=True)
