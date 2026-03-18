"""Self-healing utilities for resilient workers and connectors."""

from __future__ import annotations

import asyncio
import functools
import random
import signal
import time
from enum import Enum
from typing import Any, Awaitable, Callable, TypeVar

import structlog
from prometheus_client import Counter, Gauge

log = structlog.get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])

pipeline_circuit_breaker_state = Gauge(
    "pipeline_circuit_breaker_state",
    "Circuit breaker state (0=CLOSED, 1=HALF_OPEN, 2=OPEN).",
    ["source"],
)

pipeline_retry_attempts_total = Counter(
    "pipeline_retry_attempts_total",
    "Total retry attempts for retried async callables.",
    ["function"],
)


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = 0
    HALF_OPEN = 1
    OPEN = 2


class CircuitBreaker:
    """Circuit breaker for guarding unstable external dependencies.

    Parameters
    ----------
    failure_threshold : int, default=5
        Consecutive failures required before transitioning to OPEN.
    recovery_timeout : float, default=120
        Seconds to wait in OPEN before allowing HALF_OPEN probes.
    success_threshold : int, default=2
        Consecutive successes in HALF_OPEN required to close the circuit.
    name : str, default=""
        Source label used in logs and Prometheus metrics.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 120,
        success_threshold: int = 2,
        name: str = "",
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        self.name = name

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_monotonic: float | None = None

        pipeline_circuit_breaker_state.labels(source=self.name).set(self._state.value)

    @property
    def state(self) -> CircuitState:
        """Return the current circuit state."""
        return self._state

    def is_available(self) -> bool:
        """Return whether a call is currently allowed through the circuit."""
        if self._state == CircuitState.CLOSED:
            return True

        if self._state == CircuitState.OPEN:
            if self._last_failure_monotonic is None:
                return False
            elapsed = time.monotonic() - self._last_failure_monotonic
            if elapsed >= self.recovery_timeout:
                self._transition(CircuitState.HALF_OPEN)
                self._success_count = 0
                return True
            return False

        return True

    def record_success(self) -> None:
        """Record a successful dependency call and update state transitions."""
        if self._state == CircuitState.CLOSED:
            self._failure_count = 0
            return

        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.success_threshold:
                self._failure_count = 0
                self._success_count = 0
                self._transition(CircuitState.CLOSED)

    def record_failure(self) -> None:
        """Record a failed dependency call and update state transitions."""
        self._last_failure_monotonic = time.monotonic()

        if self._state == CircuitState.HALF_OPEN:
            self._failure_count = self.failure_threshold
            self._success_count = 0
            self._transition(CircuitState.OPEN)
            return

        self._failure_count += 1
        self._success_count = 0

        if self._failure_count >= self.failure_threshold:
            self._transition(CircuitState.OPEN)

    def _transition(self, new_state: CircuitState) -> None:
        old_state = self._state
        if old_state == new_state:
            return
        self._state = new_state
        pipeline_circuit_breaker_state.labels(source=self.name).set(new_state.value)
        log.warning(
            "circuit_breaker.state_transition",
            source=self.name,
            from_state=old_state.name,
            to_state=new_state.name,
            failures=self._failure_count,
            successes=self._success_count,
        )


def retry_with_backoff(
    max_retries: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    jitter: bool = True,
) -> Callable[[F], F]:
    """Return a decorator for retrying async callables with exponential backoff.

    Parameters
    ----------
    max_retries : int, default=5
        Maximum number of retries after the initial attempt.
    base_delay : float, default=1.0
        Initial delay in seconds before the first retry.
    max_delay : float, default=60.0
        Maximum delay cap for exponential backoff.
    exceptions : tuple[type[Exception], ...], default=(Exception,)
        Exception classes that trigger retries.
    jitter : bool, default=True
        Whether to apply ±10 percent random jitter to each delay.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            delay = base_delay
            attempt = 0

            while True:
                try:
                    return await func(*args, **kwargs)
                except exceptions as exc:
                    if attempt >= max_retries:
                        log.error(
                            "retry.exhausted",
                            function=func.__name__,
                            max_retries=max_retries,
                            error=str(exc),
                        )
                        raise

                    sleep_for = delay
                    if jitter:
                        sleep_for += random.uniform(-sleep_for * 0.1, sleep_for * 0.1)
                        sleep_for = max(0.0, sleep_for)

                    pipeline_retry_attempts_total.labels(function=func.__name__).inc()
                    log.warning(
                        "retry.attempt",
                        function=func.__name__,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        delay_seconds=round(sleep_for, 3),
                        error=str(exc),
                    )

                    await asyncio.sleep(sleep_for)
                    delay = min(delay * 2, max_delay)
                    attempt += 1

        return wrapper  # type: ignore[return-value]

    return decorator


class GracefulShutdown:
    """Async context manager for coordinated SIGTERM and SIGINT shutdown."""

    def __init__(self) -> None:
        self.running = True
        self._stop_event = asyncio.Event()
        self._loop: asyncio.AbstractEventLoop | None = None

    async def __aenter__(self) -> "GracefulShutdown":
        self._loop = asyncio.get_running_loop()
        self._loop.add_signal_handler(signal.SIGTERM, self._on_signal)
        self._loop.add_signal_handler(signal.SIGINT, self._on_signal)
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._loop is not None:
            self._loop.remove_signal_handler(signal.SIGTERM)
            self._loop.remove_signal_handler(signal.SIGINT)

    def _on_signal(self) -> None:
        if not self.running:
            return
        self.running = False
        self._stop_event.set()
        log.info("shutdown.signal_received", running=self.running)

    async def wait_for_stop(self) -> None:
        """Wait until a shutdown signal is received."""
        await self._stop_event.wait()
