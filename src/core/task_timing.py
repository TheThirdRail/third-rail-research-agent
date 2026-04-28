"""Task timing logging for CrewAI tasks."""

import logging
import time

logger = logging.getLogger(__name__)
_registered = False
_task_start_times: dict[str, float] = {}


def _get_task_key(task) -> str:
    if task is None:
        return "unknown"
    task_id = getattr(task, "id", None)
    if task_id is not None:
        return str(task_id)
    fingerprint = getattr(task, "fingerprint", None)
    if fingerprint and getattr(fingerprint, "uuid_str", None):
        return str(fingerprint.uuid_str)
    return str(id(task))


def _get_agent_info(task):
    agent = getattr(task, "agent", None)
    role = getattr(agent, "role", "unknown") if agent else "unknown"
    llm = getattr(agent, "llm", None) if agent else None
    return role, llm


def _get_provider_model(llm) -> tuple[str, str]:
    if isinstance(llm, str) and "/" in llm:
        provider, model = llm.split("/", 1)
        return provider or "unknown", model or "unknown"
    if llm is None:
        return "unknown", "unknown"
    return "unknown", str(llm)


def _extract_event(args, kwargs):
    """Extract CrewAI event from variable callback signatures."""
    if "event" in kwargs and kwargs["event"] is not None:
        return kwargs["event"]
    for arg in args:
        if hasattr(arg, "task") or hasattr(arg, "error"):
            return arg
    return None


def register_task_timing() -> None:
    global _registered
    if _registered:
        return
    _registered = True

    try:
        from crewai.events.event_bus import crewai_event_bus
        from crewai.events.types.task_events import (
            TaskCompletedEvent,
            TaskFailedEvent,
            TaskStartedEvent,
        )
    except Exception:
        logger.warning(
            "CrewAI event bus unavailable; task timing disabled.",
            exc_info=True,
        )
        return

    @crewai_event_bus.on(TaskStartedEvent)
    def _on_task_started(*args, **kwargs):
        event = _extract_event(args, kwargs)
        task = getattr(event, "task", None)
        key = _get_task_key(task)
        _task_start_times[key] = time.monotonic()
        role, llm = _get_agent_info(task)
        provider, model = _get_provider_model(llm)
        desc = getattr(task, "description", "") or ""
        logger.info(
            "Task started: %s | role=%s | provider=%s | model=%s",
            desc[:80],
            role,
            provider,
            model,
        )

    @crewai_event_bus.on(TaskCompletedEvent)
    def _on_task_completed(*args, **kwargs):
        event = _extract_event(args, kwargs)
        task = getattr(event, "task", None)
        key = _get_task_key(task)
        start = _task_start_times.pop(key, None)
        duration = time.monotonic() - start if start else None
        role, llm = _get_agent_info(task)
        provider, model = _get_provider_model(llm)
        desc = getattr(task, "description", "") or ""
        if duration is not None:
            logger.info(
                "Task completed: %s | role=%s | provider=%s | model=%s | duration=%.2fs",
                desc[:80],
                role,
                provider,
                model,
                duration,
            )
        else:
            logger.info(
                "Task completed: %s | role=%s | provider=%s | model=%s",
                desc[:80],
                role,
                provider,
                model,
            )

    @crewai_event_bus.on(TaskFailedEvent)
    def _on_task_failed(*args, **kwargs):
        event = _extract_event(args, kwargs)
        task = getattr(event, "task", None)
        key = _get_task_key(task)
        start = _task_start_times.pop(key, None)
        duration = time.monotonic() - start if start else None
        role, llm = _get_agent_info(task)
        provider, model = _get_provider_model(llm)
        desc = getattr(task, "description", "") or ""
        error = getattr(event, "error", "unknown error")
        if duration is not None:
            logger.warning(
                "Task failed: %s | role=%s | provider=%s | model=%s | duration=%.2fs | error=%s",
                desc[:80],
                role,
                provider,
                model,
                duration,
                error,
            )
        else:
            logger.warning(
                "Task failed: %s | role=%s | provider=%s | model=%s | error=%s",
                desc[:80],
                role,
                provider,
                model,
                error,
            )
