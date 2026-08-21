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
