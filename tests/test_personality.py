from skelly_ai.operation_settings import OperationSettings
from skelly_ai.brain import LocalBrain


def test_operation_settings_personality_defaults_and_custom_trim() -> None:
    settings = OperationSettings()
    assert settings.personality == "classic"
    assert settings.custom_personality == ""
    custom = OperationSettings(personality="custom", custom_personality="  spooky host  ")
    assert custom.custom_personality == "spooky host"


def test_local_brain_accepts_personality_configuration() -> None:
    brain = LocalBrain("http://127.0.0.1:8790", "test")
    brain.set_skelly_name("Bones")
    brain.set_personality("goofy")
    assert brain._skelly_name == "Bones"
    assert brain._personality == "goofy"


def test_personality_pool_defaults_to_classic_and_supports_mix() -> None:
    settings = OperationSettings()
    assert settings.personality_pool == ["classic"]
    mixed = OperationSettings(personality_pool=["classic", "unhinged", "deadpan", "custom"], custom_personality="strange librarian")
    assert mixed.personality_pool == ["classic", "unhinged", "deadpan", "custom"]
    assert mixed.personality == "classic"


def test_personality_pool_never_empty_and_deduplicates() -> None:
    settings = OperationSettings(personality_pool=[])
    assert settings.personality_pool == ["classic"]
    settings = OperationSettings(personality_pool=["goofy", "goofy", "sinister"])
    assert settings.personality_pool == ["goofy", "sinister"]


def test_deadpan_prompt_is_distinct() -> None:
    from skelly_ai.brain import build_system_prompt
    prompt = build_system_prompt("Bones", "deadpan")
    assert "unmistakably deadpan" in prompt
    assert "Never explain the joke" in prompt
