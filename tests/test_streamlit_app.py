"""Tests for Streamlit-specific rendering helpers."""

from toolbox_pb.ui.streamlit_app import ACTIVE_PROGRESS_PANEL, StreamlitProgressSlots, StreamlitTqdm


class _FakeProgressBar:
    def __init__(self) -> None:
        self.html_calls: list[str] = []

    def html(self, body: str) -> None:
        self.html_calls.append(body)


class _FakeProgressPanel:
    def __init__(self) -> None:
        self.slots: list[_FakeProgressBar] = []

    def empty(self) -> _FakeProgressBar:
        slot = _FakeProgressBar()
        self.slots.append(slot)
        return slot


def test_streamlit_tqdm_keeps_current_and_overall_progress_separate():
    """Nested Video Assembler bars must not replace one another in Streamlit."""
    panel = _FakeProgressPanel()
    slots = StreamlitProgressSlots(panel)
    token = ACTIVE_PROGRESS_PANEL.set(slots)
    try:
        overall = StreamlitTqdm(total=2, desc="Progression globale", position=1)
        current = StreamlitTqdm(total=10, desc="Vidéo en cours", position=0)
        current.update(5)
        overall.update(1)
    finally:
        ACTIVE_PROGRESS_PANEL.reset(token)

    assert len(panel.slots) == 2
    assert "50 %" in panel.slots[0].html_calls[-1]
    assert "Vidéo en cours" in panel.slots[0].html_calls[-1]
    assert "50 %" in panel.slots[1].html_calls[-1]
    assert "Progression globale" in panel.slots[1].html_calls[-1]
