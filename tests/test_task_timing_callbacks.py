from types import SimpleNamespace

from src.core.task_timing import _extract_event


def test_extract_event_from_two_args():
    event = SimpleNamespace(task="task")
    extracted = _extract_event((object(), event), {})
    assert extracted is event


def test_extract_event_from_kwargs():
    event = SimpleNamespace(task="task")
    extracted = _extract_event((), {"event": event})
    assert extracted is event

