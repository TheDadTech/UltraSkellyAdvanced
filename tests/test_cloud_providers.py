import io
import wave
from array import array

import httpx
import pytest
from pydantic import SecretStr

from skelly_ai.cloud_providers import ElevenLabsVoice, GroqBrain, GroqVoice


@pytest.mark.asyncio
async def test_groq_brain_uses_json_contract_and_contextual_eyes() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer groq-test"
        payload = __import__("json").loads(request.content)
        assert payload["model"] == "openai/gpt-oss-20b"
        assert payload["max_completion_tokens"] == 256
        assert payload["reasoning_effort"] == "low"
        assert payload["include_reasoning"] is False
        assert payload["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"spoken_response":"Love it!",'
                                '"eye_icon":"normal","movement":"head_only"}'
                            )
                        }
                    }
                ]
            },
        )

    brain = GroqBrain(transport=httpx.MockTransport(handler))
    reply = await brain.respond(SecretStr("groq-test"), "I love Halloween")

    assert reply.spoken_response == "Love it!"
    assert reply.eye_icon == "hearts"
    assert reply.movement == "head_only"


@pytest.mark.asyncio
async def test_groq_brain_explains_retired_model_error() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"message": "Model not found"}})

    brain = GroqBrain(transport=httpx.MockTransport(handler))
    with pytest.raises(Exception, match="Groq model openai/gpt-oss-20b is unavailable"):
        await brain.respond(SecretStr("groq-test"), "Hello")


@pytest.mark.asyncio
async def test_groq_brain_repairs_common_json_mode_variations() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                "Here you go:\n```json\n"
                                '{"response":"Rattle on!","eye_icon":"Skull Eyes",'
                                '"movement":"Head"}\n```'
                            )
                        }
                    }
                ]
            },
        )

    reply = await GroqBrain(transport=httpx.MockTransport(handler)).respond(
        SecretStr("groq-test"), "Hello"
    )

    assert reply.spoken_response == "Rattle on!"
    assert reply.eye_icon == "skull"
    assert reply.movement == "head_only"


@pytest.mark.asyncio
async def test_groq_brain_defaults_unknown_optional_controls_safely() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"spoken_response":"Boo!",'
                                '"eye_icon":"made_up","movement":"wild_dance",'
                                '"explanation":"extra"}'
                            )
                        }
                    }
                ]
            },
        )

    reply = await GroqBrain(transport=httpx.MockTransport(handler)).respond(
        SecretStr("groq-test"), "Hello"
    )

    assert reply.eye_icon == "normal"
    assert reply.movement == "none"


@pytest.mark.asyncio
async def test_groq_voice_returns_wav_bytes() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = __import__("json").loads(request.content)
        assert payload["voice"] == "troy"
        assert payload["response_format"] == "wav"
        assert payload["input"] == "[nasal theatrical villain] Hello"
        return httpx.Response(200, content=b"RIFF-test-wav")

    voice = GroqVoice(transport=httpx.MockTransport(handler))
    audio = await voice.generate(
        SecretStr("groq-test"),
        "Hello",
        "troy",
        "cartoon_skeleton_villain",
    )

    assert audio == b"RIFF-test-wav"


@pytest.mark.asyncio
async def test_groq_voice_explains_first_time_terms_requirement() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": {
                    "message": "The model requires terms acceptance.",
                    "type": "invalid_request_error",
                    "code": "model_terms_required",
                }
            },
        )

    voice = GroqVoice(transport=httpx.MockTransport(handler))
    with pytest.raises(Exception, match="Accept the Groq Orpheus model terms"):
        await voice.generate(SecretStr("groq-test"), "Hello", "troy")


@pytest.mark.asyncio
async def test_elevenlabs_voice_uses_selected_model_speed_and_safe_volume() -> None:
    source_samples = array("h", [10000, -10000, 20000, -20000])

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = __import__("json").loads(request.content)
        assert payload["model_id"] == "eleven_v3"
        assert payload["voice_settings"] == {"speed": 0.85}
        assert request.url.params["output_format"] == "pcm_22050"
        return httpx.Response(200, content=source_samples.tobytes())

    audio = await ElevenLabsVoice(transport=httpx.MockTransport(handler)).generate(
        SecretStr("eleven-test"),
        "Welcome!",
        "voice-123",
        model="eleven_v3",
        speed=0.85,
        volume_percent=50,
    )

    with wave.open(io.BytesIO(audio), "rb") as wav:
        output_samples = array("h")
        output_samples.frombytes(wav.readframes(wav.getnframes()))
        assert wav.getframerate() == 22050
    assert output_samples.tolist() == [5000, -5000, 10000, -10000]


@pytest.mark.asyncio
async def test_elevenlabs_voice_streams_pcm_from_low_latency_endpoint() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = __import__("json").loads(request.content)
        assert request.url.path.endswith("/text-to-speech/voice-123/stream")
        assert request.url.params["output_format"] == "pcm_22050"
        assert payload["model_id"] == "eleven_flash_v2_5"
        assert payload["voice_settings"] == {"speed": 0.9}
        return httpx.Response(200, content=b"\x01\x00\x02\x00")

    chunks = []
    voice = ElevenLabsVoice(transport=httpx.MockTransport(handler))
    async for chunk in voice.stream_pcm(
        SecretStr("eleven-test"),
        "Welcome!",
        "voice-123",
        model="eleven_flash_v2_5",
        speed=0.9,
    ):
        chunks.append(chunk)

    assert b"".join(chunks) == b"\x01\x00\x02\x00"
