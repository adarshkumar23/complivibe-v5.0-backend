import threading

try:
    import spacy
except Exception:  # pragma: no cover - fallback when spaCy is unavailable
    spacy = None  # type: ignore[assignment]

_sm_model = None
_lg_model = None
_lock = threading.Lock()


class _SimpleDoc:
    def __init__(self, text: str) -> None:
        self.text = text


class _SimpleNLP:
    def __call__(self, text: str) -> _SimpleDoc:
        return _SimpleDoc(text)


def get_sm():
    global _sm_model
    if _sm_model is None:
        with _lock:
            if _sm_model is None:
                if spacy is None:
                    _sm_model = _SimpleNLP()
                else:
                    _sm_model = spacy.load("en_core_web_sm")
    return _sm_model


def get_lg():
    global _lg_model
    if _lg_model is None:
        with _lock:
            if _lg_model is None:
                try:
                    if spacy is None:
                        _lg_model = get_sm()
                    else:
                        _lg_model = spacy.load("en_core_web_lg")
                except OSError:
                    # Fall back to sm if lg not installed
                    _lg_model = get_sm()
    return _lg_model
