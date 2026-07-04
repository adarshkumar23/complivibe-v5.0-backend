import re


class PasswordValidationError(ValueError):
    pass


def validate_password_strength(password: str) -> str:
    if len(password) < 10:
        raise PasswordValidationError("Password must be at least 10 characters long")
    if re.search(r"[A-Z]", password) is None:
        raise PasswordValidationError("Password must include at least one uppercase letter")
    if re.search(r"[a-z]", password) is None:
        raise PasswordValidationError("Password must include at least one lowercase letter")
    if re.search(r"\d", password) is None:
        raise PasswordValidationError("Password must include at least one number")
    if re.search(r"[^A-Za-z0-9]", password) is None:
        raise PasswordValidationError("Password must include at least one symbol")
    return password
