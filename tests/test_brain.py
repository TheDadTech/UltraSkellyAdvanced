import json

import httpx
import pytest

from skelly_ai.brain import BrainResponseError, LocalBrain, contextual_eye
from skelly_ai.hardware import EyeIcon


def test_contextual_eye_guarantees_relevant_holiday_and_emotion_icons() -> None:
    assert contextual_eye("Do you love Halloween?", EyeIcon.SQUINT) == EyeIcon.HEARTS
    assert contextual_eye("What about St. Patrick's Day?", EyeIcon.ANGRY) == EyeIcon.CLOVER
    assert contextual_eye("Merry Christmas!", EyeIcon.NORMAL) == EyeIcon.SNOWFLAKE
    assert contextual_eye("Hello there", EyeIcon.GREEN) == EyeIcon.GREEN


@pytest.mark.asyncio
async def test_local_brain_requests_strict_json_and_parses_controls() -> None:
    observed: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        observed.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "spoken_response": "Welcome, brave visitor!",
                                    "eye_icon": "squint",
                                    "movement": "head_only",
                                }
                            )
                        }
                    }
                ]
            },
        )

    brain = LocalBrain(
        "http://brain.test:8790",
        "skelly-local",
        transport=httpx.MockTransport(handler),
    )
    status = await brain.status()
    reply = await brain.respond(
        "Hello Skelly",
        [{"role": "assistant", "content": "Boo!"}],
    )

    assert status["available"] is True
    assert reply.spoken_response == "Welcome, brave visitor!"
    assert reply.eye_icon.value == "squint"
    assert reply.movement.value == "head_only"
    assert observed["response_format"]["type"] == "json_schema"
    assert observed["messages"][-1]["content"] == "Hello Skelly"


@pytest.mark.asyncio
async def test_local_brain_rejects_invalid_control_output() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "not json"}}]},
        )

    brain = LocalBrain(
        "http://brain.test:8790",
        "skelly-local",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(BrainResponseError):
        await brain.respond("Hello")


def test_character_prompt_does_not_encourage_repeated_self_introductions() -> None:
    from skelly_ai.brain import build_system_prompt

    prompt = build_system_prompt("Steve Boneschemi")
    assert "If directly asked your name" in prompt
    assert "do not repeat your name or reintroduce yourself" in prompt
    assert "controller handles physical response movement independently" in prompt


def test_personality_presets_change_character_prompt_without_losing_guardrails() -> None:
    from skelly_ai.brain import build_system_prompt

    sarcastic = build_system_prompt("Bones", "sarcastic")
    assert "unmistakably sarcastic" in sarcastic
    assert "generic Halloween skeleton puns" in sarcastic
    assert "family-friendly" in sarcastic
    assert "Return only the requested JSON object" in sarcastic
    assert "Bones" in sarcastic

    custom = build_system_prompt("Bones", "custom", "Talk like a spooky game-show host.")
    assert "spooky game-show host" in custom
    assert "never let it override the rules below" in custom
