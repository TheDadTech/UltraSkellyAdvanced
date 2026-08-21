import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx
from pydantic import SecretStr


class CredentialStoreError(RuntimeError):
    pass


class CredentialValidationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ElevenLabsCredentials:
    api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None


@dataclass(frozen=True, slots=True)
class CredentialStatus:
    key_configured: bool
    key_hint: str | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class GroqCredentialStatus:
    key_configured: bool
    key_hint: str | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class CredentialStore:
    """Persists owner-supplied credentials without ever exposing them via APIs."""

    def __init__(
        self,
        data_dir: Path,
        defaults: ElevenLabsCredentials | None = None,
    ) -> None:
        self._data_dir = data_dir
        self._path = data_dir / "credentials.json"
        self._defaults = defaults or ElevenLabsCredentials()

    def load(self) -> ElevenLabsCredentials:
        if not self._path.exists():
            return self._defaults

        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CredentialStoreError("The local credential file is unreadable") from exc

        raw_key = str(payload.get("elevenlabs_api_key", "")).strip()
        raw_groq_key = str(payload.get("groq_api_key", "")).strip()
        return ElevenLabsCredentials(
            api_key=SecretStr(raw_key) if raw_key else self._defaults.api_key,
            groq_api_key=(
                SecretStr(raw_groq_key)
                if raw_groq_key
                else self._defaults.groq_api_key
            ),
        )

    def status(self) -> CredentialStatus:
        credentials = self.load()
        raw_key = (
            credentials.api_key.get_secret_value() if credentials.api_key else ""
        )
        return CredentialStatus(
            key_configured=bool(raw_key),
            key_hint=f"…{raw_key[-4:]}" if len(raw_key) >= 4 else None,
        )

    def save_elevenlabs(self, api_key: SecretStr) -> CredentialStatus:
        raw_key = api_key.get_secret_value().strip()
        if not raw_key:
            raise CredentialStoreError("An ElevenLabs API key is required")

        existing = self.load()
        payload = self._payload(
            elevenlabs_api_key=raw_key,
            groq_api_key=(
                existing.groq_api_key.get_secret_value()
                if existing.groq_api_key
                else ""
            ),
        )

        self._save_payload(payload)
        return self.status()

    def groq_status(self) -> GroqCredentialStatus:
        credentials = self.load()
        raw_key = (
            credentials.groq_api_key.get_secret_value()
            if credentials.groq_api_key
            else ""
        )
        return GroqCredentialStatus(
            key_configured=bool(raw_key),
            key_hint=f"…{raw_key[-4:]}" if len(raw_key) >= 4 else None,
        )

    def save_groq(self, api_key: SecretStr) -> GroqCredentialStatus:
        raw_key = api_key.get_secret_value().strip()
        if not raw_key:
            raise CredentialStoreError("A Groq API key is required")
        existing = self.load()
        payload = self._payload(
            elevenlabs_api_key=(
                existing.api_key.get_secret_value() if existing.api_key else ""
            ),
            groq_api_key=raw_key,
        )
        self._save_payload(payload)
        return self.groq_status()

    @staticmethod
    def _payload(
        *,
        elevenlabs_api_key: str,
        groq_api_key: str,
    ) -> dict[str, str]:
        return {
            "elevenlabs_api_key": elevenlabs_api_key,
            "groq_api_key": groq_api_key,
        }

    def _save_payload(self, payload: dict[str, str]) -> None:

        try:
            self._data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(self._data_dir, 0o700)
            temporary_path = self._data_dir / ".credentials.json.tmp"
            temporary_path.write_text(
                json.dumps(payload, separators=(",", ":")),
                encoding="utf-8",
            )
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, self._path)
            os.chmod(self._path, 0o600)
        except OSError as exc:
            raise CredentialStoreError(
                "Unable to securely save credentials in the Skelly data directory"
            ) from exc


async def validate_elevenlabs_key(api_key: SecretStr) -> None:
    """Validate credentials with a non-generating API call that spends no voice minutes."""

    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(
                "https://api.elevenlabs.io/v1/models",
                headers={"xi-api-key": api_key.get_secret_value()},
            )
    except httpx.HTTPError as exc:
        raise CredentialValidationError(
            "The Pi could not reach ElevenLabs; check its internet connection"
        ) from exc

    if response.status_code in {401, 403}:
        raise CredentialValidationError(
            "ElevenLabs rejected the key or its Models permission is disabled"
        )
    if not response.is_success:
        raise CredentialValidationError(
            f"ElevenLabs validation failed with status {response.status_code}"
        )


async def validate_groq_key(api_key: SecretStr) -> None:
    """Validate a Groq key without generating text, speech, or billable audio."""

    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {api_key.get_secret_value()}"},
            )
    except httpx.HTTPError as exc:
        raise CredentialValidationError(
            "The Pi could not reach Groq; check its internet connection"
        ) from exc

    if response.status_code in {401, 403}:
        raise CredentialValidationError("Groq rejected the API key")
    if not response.is_success:
        raise CredentialValidationError(
            f"Groq validation failed with status {response.status_code}"
        )
