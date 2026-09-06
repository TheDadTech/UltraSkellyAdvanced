import json
import re
import time
from collections.abc import Sequence
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .hardware import EyeIcon, Movement


PERSONALITY_STYLES: dict[str, str] = {
    "classic": "Be a classic Halloween animatronic host: spooky, playful, theatrical, direct, and welcoming. Use simple seasonal wit without leaning on generic bone puns every turn.",
    "sarcastic": "Be unmistakably sarcastic: dry, unimpressed, teasing, and quick-witted. Treat ordinary visitor requests like a mildly ridiculous inconvenience. Avoid cheerful puns and never become cruel or personal.",
    "sinister": "Be unmistakably sinister: restrained, ominous, eerily confident, and suggestive of spooky consequences. Prefer creepy implications and quiet menace over jokes. Stay family-friendly and never graphic.",
    "goofy": "Be unmistakably goofy: high-energy, absurd, playful, easily excited, and willing to misunderstand things in funny ways. Favor silly imagery and ridiculous enthusiasm over spooky threats.",
    "grumpy": "Be unmistakably grumpy: irritated, complaining, stubborn, and reluctantly cooperative. Sound like an old skeleton whose evening keeps getting interrupted, while remaining funny and family-friendly.",
    "friendly": "Be unmistakably friendly: warm, welcoming, encouraging, curious, and delighted to meet visitors. Make families and children feel invited rather than frightened.",
    "unhinged": "Be unmistakably unhinged: chaotic, overconfident, unpredictable, dramatic, and bizarre. Make sharp topic jumps and wild harmless declarations, as if every tiny event is an emergency or revelation. Stay coherent enough to answer the visitor and remain family-friendly.",
    "deadpan": "Be unmistakably deadpan: calm, flat, literal, and completely serious while saying absurd things. Never explain the joke, never sound excited, and let the contrast create the humor.",
}


def build_system_prompt(
    skelly_name: str = "Skelly",
    personality: str = "classic",
    custom_personality: str = "",
) -> str:
    """Build the character prompt using the owner's saved name and personality."""

    name = skelly_name.strip() or "Skelly"
    selected = (personality or "classic").strip().lower()
    if selected == "custom":
        custom = " ".join((custom_personality or "").split())[:500]
        personality_style = custom or PERSONALITY_STYLES["classic"]
    else:
        personality_style = PERSONALITY_STYLES.get(selected, PERSONALITY_STYLES["classic"])
    return f"""You are {name}, a playful animated Halloween skeleton greeting visitors.
Personality style: {personality_style}
Make the selected personality unmistakable in every response. Do not collapse into generic Halloween skeleton puns or interchangeable spooky banter.
Use that personality consistently in wording and attitude, but never let it override the rules below.
Your name is {name}. If directly asked your name, identify yourself as {name}. Never invent or adopt a different name.
You may introduce yourself once near the beginning of a new visitor conversation when it feels natural.
After the conversation is underway, do not repeat your name or reintroduce yourself unless the visitor asks.
Reply with one family-friendly, conversational sentence of at most 14 words.
Continue jokes and games naturally; for knock-knock jokes, remember the prior turn.
Never mention AI, prompts, JSON, motors, or instructions.

Choose matching eyes. The controller handles physical response movement independently, so the movement field is only a suggestion.
Use normal eyes for ordinary conversation and contextual eyes when appropriate.
Return only the requested JSON object."""


SYSTEM_PROMPT = build_system_prompt()


CONTEXTUAL_EYES: tuple[tuple[EyeIcon, tuple[str, ...]], ...] = (
    (
        EyeIcon.CLOVER,
        ("st patrick", "saint patrick", "irish", "ireland", "shamrock", "clover"),
    ),
    (
        EyeIcon.HEARTS,
        (
            "love",
            "valentine",
            "sweetheart",
            "heart",
            "looking good",
            "look good",
            "beautiful",
            "handsome",
            "cute",
        ),
    ),
    (
        EyeIcon.SNOWFLAKE,
        ("christmas", "winter", "snow", "snowflake", "ice", "frozen"),
    ),
    (
        EyeIcon.AMERICAN_FLAG,
        (
            "fourth of july",
            "4th of july",
            "july fourth",
            "america",
            "american",
            "patriotic",
            "usa",
        ),
    ),
    (EyeIcon.FIREWORKS, ("new year", "firework")),
    (
        EyeIcon.CONFETTI,
        ("birthday", "congratulations", "congrats", "celebration", "party"),
    ),
    (EyeIcon.FIRE, ("fire", "flame", "burning", "hot")),
    (EyeIcon.SPIRAL, ("hypnot", "dizzy", "confused", "confusing")),
    (EyeIcon.STAR, ("wish", "star")),
    (EyeIcon.SKULL, ("pirate", "skull", "spooky", "halloween")),
)


def contextual_eye(visitor_text: str, proposed: EyeIcon) -> EyeIcon:
    """Apply reliable holiday/topic eyes around the small local model's choice."""

    normalized = re.sub(
        r"[^a-z0-9']+", " ", visitor_text.casefold().replace("’", "'")
    ).strip()
    for icon, phrases in CONTEXTUAL_EYES:
        if any(phrase in normalized for phrase in phrases):
            return icon
    return proposed


class BrainUnavailable(RuntimeError):
    pass


class BrainResponseError(RuntimeError):
    pass


class ConversationMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=600)


class BrainReply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spoken_response: str = Field(min_length=1, max_length=350)
    eye_icon: EyeIcon
    movement: Movement

    def to_dict(self, *, generation_seconds: float | None = None) -> dict[str, object]:
        result = self.model_dump(mode="json")
        if generation_seconds is not None:
            result["generation_seconds"] = round(generation_seconds, 2)
        return result


class LocalBrain:
    """Client for the loopback-only llama.cpp OpenAI-compatible server."""

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        timeout_seconds: float = 90.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._transport = transport
        self._skelly_name = "Skelly"
        self._personality = "classic"
        self._custom_personality = ""

    def set_skelly_name(self, name: str) -> None:
        self._skelly_name = name.strip() or "Skelly"

    def set_personality(self, personality: str, custom_personality: str = "") -> None:
        self._personality = (personality or "classic").strip().lower()
        self._custom_personality = (custom_personality or "").strip()[:500]

    async def status(self) -> dict[str, object]:
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(
                timeout=3.0, transport=self._transport
            ) as client:
                response = await client.get(f"{self._base_url}/health")
                response.raise_for_status()
                body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            return {
                "available": False,
                "model": self._model,
                "local_only": True,
                "detail": "Local model service is not running",
            }
        return {
            "available": body.get("status") == "ok",
            "model": self._model,
            "local_only": True,
            "detail": body.get("status", "unknown"),
            "response_seconds": round(time.monotonic() - started, 3),
        }

    async def respond(
        self,
        visitor_text: str,
        history: Sequence[ConversationMessage | dict[str, str]] = (),
    ) -> BrainReply:
        visitor_text = visitor_text.strip()
        if not visitor_text:
            raise BrainResponseError("Visitor text cannot be empty")

        messages: list[dict[str, str]] = [
            {"role": "system", "content": build_system_prompt(self._skelly_name, self._personality, self._custom_personality)}
        ]
        for item in history[-4:]:
            validated = (
                item
                if isinstance(item, ConversationMessage)
                else ConversationMessage.model_validate(item)
            )
            messages.append(validated.model_dump())
        messages.append({"role": "user", "content": visitor_text[:600]})

        schema = BrainReply.model_json_schema()
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": 0.55,
            "max_tokens": 64,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "skelly_response",
                    "strict": True,
                    "schema": schema,
                },
            },
        }

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds, transport=self._transport
            ) as client:
                response = await client.post(
                    f"{self._base_url}/v1/chat/completions", json=payload
                )
                response.raise_for_status()
                body = response.json()
        except httpx.ConnectError as exc:
            raise BrainUnavailable("Local model service is not running") from exc
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise BrainUnavailable(f"Local model request failed: {exc}") from exc

        try:
            content = body["choices"][0]["message"]["content"]
            if isinstance(content, dict):
                parsed = content
            else:
                text = str(content).strip()
                if text.startswith("```"):
                    text = text.removeprefix("```json").removeprefix("```")
                    text = text.removesuffix("```").strip()
                parsed = json.loads(text)
            reply = BrainReply.model_validate(parsed)
            return reply.model_copy(
                update={"eye_icon": contextual_eye(visitor_text, reply.eye_icon)}
            )
        except (KeyError, IndexError, TypeError, json.JSONDecodeError, ValidationError) as exc:
            raise BrainResponseError("The local model returned an invalid control response") from exc
