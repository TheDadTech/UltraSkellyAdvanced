import pytest

from skelly_ai.state import InvalidTransition, Mode, StateController


@pytest.mark.asyncio
async def test_show_lock_blocks_interaction_and_restores_previous_mode() -> None:
    state = StateController()
    await state.ready()
    await state.set_interactive()

    snapshot = await state.begin_show("Thriller")
    assert snapshot.mode == Mode.SHOW_LOCKED
    assert snapshot.show_name == "Thriller"

    with pytest.raises(InvalidTransition):
        await state.set_interactive()

    snapshot = await state.end_show()
    assert snapshot.mode == Mode.INTERACTIVE
    assert snapshot.show_name is None


@pytest.mark.asyncio
async def test_second_show_cannot_replace_active_show() -> None:
    state = StateController()
    await state.ready()
    await state.begin_show("First")

    with pytest.raises(InvalidTransition):
        await state.begin_show("Second")

