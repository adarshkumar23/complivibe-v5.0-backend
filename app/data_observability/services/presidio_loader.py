import threading
from typing import Any

try:
    from presidio_analyzer import AnalyzerEngine
except Exception:  # pragma: no cover - optional dependency fallback
    AnalyzerEngine = None  # type: ignore[assignment]

_engine = None
_lock = threading.Lock()


def get_presidio() -> Any | None:
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                if AnalyzerEngine is None:
                    return None
                try:
                    _engine = AnalyzerEngine()
                    from app.data_observability.services.indian_pii_patterns import get_custom_recognizers

                    for recognizer in get_custom_recognizers():
                        _engine.registry.add_recognizer(recognizer)
                except Exception:
                    # Presidio not available — return None, callers handle.
                    return None
    return _engine
