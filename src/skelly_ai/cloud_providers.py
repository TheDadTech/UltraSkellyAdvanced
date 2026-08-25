import io
import json
import re
import sys
import wave
from array import array
from collections.abc import AsyncIterator, Sequence

import httpx
from pydantic import SecretStr, ValidationError

from .brain import (
    build_system_prompt,
    BrainReply,
    BrainResponseError,
    BrainUnavailable,
    ConversationMessage,
    contextual_eye,
)
from .hardware import EyeIcon, Movement


class CloudSpeechUnavailable(RuntimeError):
    pass


def _normalized_choice(value: object) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value).casefold()).strip("_")
    return normalized.removesuffix("_eyes").removesuffix("_eye")


def _parse_groq_reply(content: object, visitor_text: str) -> BrainReply:
    """Tolerate harmless JSON and enum variations from JSON-object mode."""

    if isinstance(content, dict):
        parsed = content
    else:
        text = str(content).strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
        first, last = text.find("{"), text.rfind("}")
        if first >= 0 and last > first:
            text = text[first : last + 1]
        parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise TypeError("Groq response was not a JSON object")

    spoken = next(
        (
            str(parsed[key]).strip()
            for key in ("spoken_response", "response", "spoken", "text")
            if parsed.get(key) is not None and str(parsed[key]).strip()
        ),
        "",
    )
    eye_value = _normalized_choice(parsed.get("eye_icon", "normal"))
    eye_value = {
        "red": "angry",
        "cat": "orange_cat",
        "orange": "orange_cat",
        "flag": "american_flag",
        "american": "american_flag",
        "heart": "hearts",
        "shamrock": "clover",
        "snow": "snowflake",
        "firework": "fireworks",
    }.get(eye_value, eye_value)
    try:
        eye = EyeIcon(eye_value)
    except ValueError:
        eye = EyeIcon.NORMAL

    movement_value = _normalized_choice(parsed.get("movement", "none"))
    movement_value = {
        "no": "none",
        "no_movement": "none",
        "still": "none",
        "head": "head_only",
        "arms": "arms_only",
        "torso": "torso_only",
        "body": "torso_and_arms",
        "torso_arms": "torso_and_arms",
        "full_body": "all",
        "everything": "all",
    }.get(movement_value, movement_value)
    try:
        movement = Movement(movement_value)
    except ValueError:
        movement = Movement.NONE

    reply = BrainReply(
        spoken_response=spoken,
        eye_icon=eye,
        movement=movement,
    )
    return reply.model_copy(
        update={"eye_icon": contextual_eye(visitor_text, reply.eye_icon)}
    )


def _provider_error(response: httpx.Response) -> tuple[str, str]:
    try:
        payload = response.json()
        error = payload.get("error", {}) if isinstance(payload, dict) else {}
        if not isinstance(error, dict):
            return "", ""
        return (
            str(error.get("code") or "").strip(),
            str(error.get("message") or "").strip()[:300],
        )
    except ValueError:
        return "", ""


class GroqBrain:
    """Fast OpenAI-compatible Groq brain with the same Skelly response contract."""

    def __init__(
        self,
        *,
        model: str = "openai/gpt-oss-20b",
        base_url: str = "https://api.groq.com/openai/v1",
        timeout_seconds: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._transport = transport
        self._skelly_name = "Skelly"

    def set_skelly_name(self, name: str) -> None:
        self._skelly_name = name.strip() or "Skelly"

    def status(self, api_key: SecretStr | None) -> dict[str, object]:
        return {
            "available": api_key is not None,
            "model": self._model,
            "provider": "groq",
            "local_only": False,
            "detail": "ready" if api_key else "Save a Groq API key in Setup",
        }

    async def respond(
        self,
        api_key: SecretStr,
        visitor_text: str,
        history: Sequence[ConversationMessage | dict[str, str]] = (),
    ) -> BrainReply:
        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": (
                    build_system_prompt(self._skelly_name)
                    + '\nThe exact JSON keys are "spoken_response", "eye_icon", and '
                    '"movement". eye_icon must be one of: '
                    + ", ".join(icon.value for icon in EyeIcon)
                    + ". movement must be one of: "
                    + ", ".join(movement.value for movement in Movement)
                    + ". Do not add keys or markdown."
                ),
            }
        ]
        for item in history[-4:]:
            validated = (
                item
                if isinstance(item, ConversationMessage)
                else ConversationMessage.model_validate(item)
            )
            messages.append(validated.model_dump())
        messages.append({"role": "user", "content": visitor_text.strip()[:600]})

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds, transport=self._transport
            ) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key.get_secret_value()}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._model,
                        "messages": messages,
                        "temperature": 0.55,
                        "max_completion_tokens": 256,
                        "reasoning_effort": "low",
                        "include_reasoning": False,
                        "response_format": {"type": "json_object"},
                    },
                )
                response.raise_for_status()
                body = response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {401, 403}:
                raise BrainUnavailable("Groq rejected the saved API key") from exc
            if exc.response.status_code == 429:
                raise BrainUnavailable("Groq free-tier limit reached; try again later") from exc
            if exc.response.status_code == 404:
                raise BrainUnavailable(
                    f"Groq model {self._model} is unavailable; update Skelly AI"
                ) from exc
            raise BrainUnavailable(
                f"Groq response failed with status {exc.response.status_code}"
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise BrainUnavailable("The Pi could not reach Groq") from exc

        try:
            content = body["choices"][0]["message"]["content"]
            return _parse_groq_reply(content, visitor_text)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError, ValidationError) as exc:
            raise BrainResponseError("Groq returned an invalid Skelly response") from exc


class GroqVoice:
    def __init__(
        self,
        *,
        model: str = "canopylabs/orpheus-v1-english",
        base_url: str = "https://api.groq.com/openai/v1",
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def generate(
        self,
        api_key: SecretStr,
        text: str,
        voice: str,
        style: str = "natural",
    ) -> bytes:
        directions = {
            "natural": "",
            "cartoon_skeleton_villain": "[nasal theatrical villain] ",
            "gravelly_whisper": "[gravelly whisper] ",
            "deadpan": "[deadpan] ",
        }
        prefix = directions.get(style, "")
        clean_text = " ".join(text.split())
        available = max(1, 200 - len(prefix))
        if len(clean_text) > available:
            clean_text = clean_text[:available].rsplit(" ", 1)[0]
        directed_text = prefix + clean_text
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds, transport=self._transport
            ) as client:
                response = await client.post(
                    f"{self._base_url}/audio/speech",
                    headers={"Authorization": f"Bearer {api_key.get_secret_value()}"},
                    json={
                        "model": self._model,
                        "voice": voice,
                        "input": directed_text,
                        "response_format": "wav",
                    },
                )
                response.raise_for_status()
                return response.content
        except httpx.HTTPStatusError as exc:
            code, message = _provider_error(exc.response)
            if code == "model_terms_required":
                raise CloudSpeechUnavailable(
                    "Accept the Groq Orpheus model terms using the Setup link, then retry"
                ) from exc
            if exc.response.status_code == 429:
                raise CloudSpeechUnavailable(
                    "Groq voice free-tier limit reached; use Local Voice or try later"
                ) from exc
            detail = f": {message}" if message else ""
            raise CloudSpeechUnavailable(
                f"Groq voice failed with status {exc.response.status_code}{detail}"
            ) from exc
        except httpx.HTTPError as exc:
            raise CloudSpeechUnavailable("The Pi could not reach Groq voice") from exc


class ElevenLabsVoice:
    def __init__(
        self,
        *,
        base_url: str = "https://api.elevenlabs.io/v1",
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def stream_pcm(
        self,
        api_key: SecretStr,
        text: str,
        voice_id: str,
        *,
        model: str = "eleven_v3",
        speed: float = 0.85,
    ) -> AsyncIterator[bytes]:
        """Yield ElevenLabs PCM as it arrives instead of waiting for the full clip."""

        if not voice_id.strip():
            raise CloudSpeechUnavailable("Enter an ElevenLabs Voice ID in Setup")
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds, transport=self._transport
            ) as client:
                async with client.stream(
                    "POST",
                    f"{self._base_url}/text-to-speech/{voice_id.strip()}/stream",
                    params={"output_format": "pcm_22050"},
                    headers={
                        "xi-api-key": api_key.get_secret_value(),
                        "Content-Type": "application/json",
                    },
                    json={
                        "text": text,
                        "model_id": model,
                        "voice_settings": {"speed": speed},
                    },
                ) as response:
                    response.raise_for_status()
                    async for chunk in response.aiter_bytes():
                        if chunk:
                            yield chunk
        except httpx.HTTPStatusError as exc:
            raise CloudSpeechUnavailable(
                f"ElevenLabs voice failed with status {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise CloudSpeechUnavailable("The Pi could not reach ElevenLabs voice") from exc

    async def generate(
        self,
        api_key: SecretStr,
        text: str,
        voice_id: str,
        *,
        model: str = "eleven_v3",
        speed: float = 0.85,
        volume_percent: int = 85,
    ) -> bytes:
        if not voice_id.strip():
            raise CloudSpeechUnavailable("Enter an ElevenLabs Voice ID in Setup")
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds, transport=self._transport
            ) as client:
                response = await client.post(
                    f"{self._base_url}/text-to-speech/{voice_id.strip()}",
                    params={"output_format": "pcm_22050"},
                    headers={
                        "xi-api-key": api_key.get_secret_value(),
                        "Content-Type": "application/json",
                    },
                    json={
                        "text": text,
                        "model_id": model,
                        "voice_settings": {"speed": speed},
                    },
                )
                response.raise_for_status()
                pcm = response.content
        except httpx.HTTPStatusError as exc:
            raise CloudSpeechUnavailable(
                f"ElevenLabs voice failed with status {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise CloudSpeechUnavailable("The Pi could not reach ElevenLabs voice") from exc

        if len(pcm) % 2:
            raise CloudSpeechUnavailable("ElevenLabs returned invalid PCM audio")
        volume = max(0.1, min(1.0, volume_percent / 100))
        if volume < 1.0:
            samples = array("h")
            samples.frombytes(pcm)
            if sys.byteorder == "big":
                samples.byteswap()
            for index, sample in enumerate(samples):
                samples[index] = round(sample * volume)
            if sys.byteorder == "big":
                samples.byteswap()
            pcm = samples.tobytes()

        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(22050)
            wav.writeframes(pcm)
        return output.getvalue()
