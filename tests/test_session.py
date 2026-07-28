from localwhisper.session import DictationSession, DictationState, SessionState


def test_session_state_rejects_overlapping_recording():
    state = SessionState()
    assert state.transition(DictationState.RECORDING)
    assert state.transition(DictationState.RECORDING)
    assert state.transition(DictationState.PROCESSING)
    assert not state.transition(DictationState.RECORDING)
    assert state.transition(DictationState.IDLE)


def test_session_state_can_recover_from_error():
    state = SessionState()
    assert state.transition(DictationState.RECORDING)
    assert state.transition(DictationState.ERROR)
    assert state.transition(DictationState.IDLE)
    assert not state.busy


def test_runtime_events_are_isolated_per_dictation():
    first = DictationSession()
    second = DictationSession()
    first.stream_stop.set()
    first.engine_ready.set()

    assert not second.stream_stop.is_set()
    assert not second.engine_ready.is_set()
