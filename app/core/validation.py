from __future__ import annotations

from collections.abc import Iterable
from typing import Any


class InvalidChoiceError(Exception):
    """Raised when a value fails a hand-rolled "is this one of N allowed strings"
    check. A single global exception handler (see app/main.py) turns this into a
    response that always lists the valid options, so every call site gets
    consistent, self-documenting error messages without formatting its own.
    """

    def __init__(self, field: str, value: Any, allowed: Iterable[str], status_code: int = 422) -> None:
        self.field = field
        self.value = value
        self.allowed = sorted({str(item) for item in allowed})
        self.status_code = status_code
        super().__init__(f"Invalid {field}: {value!r}. Valid options: {', '.join(self.allowed)}")


def validate_choice(value: Any, allowed: Iterable[str], field: str, *, status_code: int = 422) -> Any:
    """Validate that `value` is a member of `allowed`, raising InvalidChoiceError
    (enriched with the full list of valid options) if not. Returns `value`
    unchanged so call sites can inline it: `status = validate_choice(status, STATUSES, "status")`.
    `status_code` defaults to 422 but can be overridden to preserve a call site's
    pre-existing status code (e.g. 400) without changing response semantics.
    """
    allowed_set = allowed if isinstance(allowed, (set, frozenset)) else set(allowed)
    if value not in allowed_set:
        raise InvalidChoiceError(field, value, allowed_set, status_code=status_code)
    return value
