from __future__ import annotations

import asyncio
import functools
from typing import Any, Callable

from app.observability.tracing.tracer import span


def trace(name: str | None = None):
    """装饰同步/异步函数，自动包裹 span。"""

    def _wrap(fn: Callable[..., Any]) -> Callable[..., Any]:
        span_name = name or f"{fn.__module__}.{fn.__qualname__}"

        if asyncio.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def _async(*args, **kwargs):
                with span(span_name):
                    return await fn(*args, **kwargs)

            return _async

        @functools.wraps(fn)
        def _sync(*args, **kwargs):
            with span(span_name):
                return fn(*args, **kwargs)

        return _sync

    return _wrap


__all__ = ["trace"]
