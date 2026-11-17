from argon2 import PasswordHasher

_ph = PasswordHasher()


def hash_password(pw: str) -> str:
    return "argon2id$" + _ph.hash(pw)