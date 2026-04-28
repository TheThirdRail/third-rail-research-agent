import threading
import time
from types import SimpleNamespace

import src.core.llm_provider_docker as llm
from src.core.llm_provider_docker import LLMRouter


class DummyBudget:
    def can_afford(self, model_is_free: bool = False) -> bool:
        return True

    def get_status(self) -> dict[str, float]:
        return {"current_spend": 0.0, "limit": 1.0}

    def track_spend(self, cost: float) -> None:
        return None


def test_free_tier_semaphore_blocks(monkeypatch):
    monkeypatch.setattr(llm, "get_budget_service", lambda: DummyBudget())
    monkeypatch.setattr(llm, "completion_cost", lambda completion_response: 0)

    semaphore = threading.BoundedSemaphore(1)
    monkeypatch.setattr(LLMRouter, "_get_provider_semaphore", lambda self: semaphore)

    started = threading.Event()
    allow_finish = threading.Event()

    def fake_completion(*_args, **_kwargs):
        if not started.is_set():
            started.set()
            allow_finish.wait(1)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
        )

    monkeypatch.setattr(llm, "completion", fake_completion)

    router = LLMRouter(provider="mistral", model="mistral-small-latest")
    router.free_tier = True

    def run():
        router.complete([{"role": "user", "content": "hi"}])

    t1 = threading.Thread(target=run)
    t2 = threading.Thread(target=run)
    t1.start()
    assert started.wait(0.2)
    t2.start()

    time.sleep(0.05)
    assert t2.is_alive()

    allow_finish.set()
    t1.join(1)
    t2.join(1)

    assert not t1.is_alive() and not t2.is_alive()
