import hashlib, hmac
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError

hasher = PasswordHasher()


def hash_password(password):
    return hasher.hash(password)


def verify_password(password, encoded):
    try:
        return hasher.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


def hash_key(key):
    return hashlib.sha256(key.encode()).hexdigest()


def verify_key(key, encoded):
    return hmac.compare_digest(hash_key(key), encoded)
