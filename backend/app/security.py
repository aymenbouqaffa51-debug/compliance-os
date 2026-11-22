"""Authentication, password hashing, TOTP and credential encryption.

Deliberately implemented on the standard library where it matters, so the
security-critical path has no third-party surprises:

  - Password hashing: PBKDF2-HMAC-SHA256, 600k iterations, per-user salt.
    Stored as `pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>`.
  - TOTP: RFC 6238, HMAC-SHA1, 6 digits, 30-second step, +/-1 step skew.
  - Session tokens: HS256 JWT with an expiry.
  - Integration credentials: Fernet (AES-128-CBC + HMAC), key from env.

Nothing here accepts a secret as a CLI argument or writes one to disk in
plaintext.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import struct
import time

from cryptography.fernet import Fernet, InvalidToken

PBKDF2_ITERATIONS = 600_000
JWT_ALG = "HS256"
TOKEN_TTL_SECONDS = 12 * 3600


class AuthError(Exception):
    pass


# ------------------------------------------------------------------ passwords
def hash_password(password: str) -> str:
    if not password or len(password) < 10:
        raise AuthError("password must be at least 10 characters")
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return "pbkdf2_sha256$%d$%s$%s" % (
        PBKDF2_ITERATIONS, salt.hex(), dk.hex()
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iters)
        )
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


# ---------------------------------------------------------------------- JWT
# Implemented on the standard library (HMAC-SHA256 + base64url) rather than
# PyJWT, because the `jwt` distribution name is claimed by an incompatible
# package that shadows PyJWT on some systems. HS256 is a handful of lines and
# removes a dependency from the security-critical path.


def _jwt_secret() -> str:
    """Signing secret. Must be set in production.

    A generated secret is acceptable for a single-process development run, but
    it makes every issued token invalid on restart -- hence the startup warning.
    """
    secret = os.environ.get("COMPLIANCE_JWT_SECRET", "")
    if secret:
        return secret
    cached = getattr(_jwt_secret, "_cached", None)
    if cached is None:
        cached = secrets.token_urlsafe(48)
        setattr(_jwt_secret, "_cached", cached)
    return cached


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def _sign(signing_input: bytes, secret: str) -> str:
    sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return _b64url_encode(sig)


def issue_token(user_id: str, tenant_id: str, role: str, email: str) -> str:
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user_id,
        "tid": tenant_id,
        "role": role,
        "email": email,
        "iat": now,
        "exp": now + TOKEN_TTL_SECONDS,
    }
    h = _b64url_encode(json.dumps(header, separators=(",", ":"), sort_keys=True).encode())
    p = _b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signing_input = (h + "." + p).encode("ascii")
    return h + "." + p + "." + _sign(signing_input, _jwt_secret())


def decode_token(token: str) -> dict:
    try:
        h, p, s = token.split(".")
    except ValueError:
        raise AuthError("invalid token")

    expected = _sign((h + "." + p).encode("ascii"), _jwt_secret())
    if not hmac.compare_digest(expected, s):
        raise AuthError("invalid token signature")

    try:
        header = json.loads(_b64url_decode(h))
        payload = json.loads(_b64url_decode(p))
    except Exception:
        raise AuthError("invalid token payload")

    # Reject alg=none and any algorithm substitution.
    if header.get("alg") != JWT_ALG:
        raise AuthError("unsupported token algorithm")

    exp = payload.get("exp")
    if not isinstance(exp, int):
        raise AuthError("token has no expiry")
    if exp < int(time.time()):
        raise AuthError("token expired")

    return payload


# ---------------------------------------------------------------------- TOTP
TOTP_DIGITS = 6
TOTP_STEP = 30


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii")


def _hotp(key: bytes, counter: int, digits: int = TOTP_DIGITS) -> str:
    msg = struct.pack(">Q", counter)
    h = hmac.new(key, msg, hashlib.sha1).digest()
    offset = h[-1] & 0x0F
    code = struct.unpack(">I", h[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(code % (10 ** digits)).zfill(digits)


def totp_now(secret_b32: str, at: int | None = None) -> str:
    key = base64.b32decode(secret_b32, casefold=True)
    counter = int((at if at is not None else time.time()) // TOTP_STEP)
    return _hotp(key, counter)


def verify_totp(secret_b32: str, code: str, skew: int = 1) -> bool:
    """Accept the current step and +/- `skew` steps to tolerate clock drift."""
    if not secret_b32 or not code:
        return False
    code = code.strip().replace(" ", "")
    if not code.isdigit() or len(code) != TOTP_DIGITS:
        return False
    try:
        key = base64.b32decode(secret_b32, casefold=True)
    except Exception:
        return False
    counter = int(time.time() // TOTP_STEP)
    for delta in range(-skew, skew + 1):
        if hmac.compare_digest(_hotp(key, counter + delta), code):
            return True
    return False


def totp_uri(secret_b32: str, email: str, issuer: str = "Compliance OS") -> str:
    """otpauth:// URI for an authenticator app."""
    import urllib.parse
    label = urllib.parse.quote("%s:%s" % (issuer, email))
    return "otpauth://totp/%s?secret=%s&issuer=%s&period=%d&digits=%d" % (
        label, secret_b32, urllib.parse.quote(issuer), TOTP_STEP, TOTP_DIGITS)


# ------------------------------------------------------- credential encryption
def _fernet() -> Fernet:
    key = os.environ.get("COMPLIANCE_SECRET_KEY", "")
    if not key:
        # Derive a stable key from the JWT secret so a fresh install works, but
        # warn that production must set an explicit key.
        seed = os.environ.get("COMPLIANCE_JWT_SECRET", "") or _jwt_secret()
        key = base64.urlsafe_b64encode(hashlib.sha256(seed.encode()).digest()).decode()
    if isinstance(key, str):
        key = key.encode()
    try:
        return Fernet(key)
    except Exception:
        # Not a valid Fernet key: derive one deterministically.
        derived = base64.urlsafe_b64encode(hashlib.sha256(key).digest())
        return Fernet(derived)


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken:
        raise AuthError("stored credential could not be decrypted with the current key")


def generate_secret_key() -> str:
    return Fernet.generate_key().decode("ascii")
