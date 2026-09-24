"""Local OpenID Connect signing key and public JWKS representation."""

import base64
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


KID = "numinar-mock-rs256-v1"
KEY_PATH = Path(os.environ.get(
    "PM_OIDC_KEY_PATH",
    Path(__file__).resolve().parent.parent / "mock-signing-key.pem",
))


def _load_or_create_private_key():
    try:
        pem = KEY_PATH.read_bytes()
    except FileNotFoundError:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = KEY_PATH.with_suffix(KEY_PATH.suffix + f".tmp.{os.getpid()}")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(pem)
        os.replace(temporary, KEY_PATH)
        return key
    return serialization.load_pem_private_key(pem, password=None)


def _base64url_uint(value):
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


PRIVATE_KEY = _load_or_create_private_key()
_PUBLIC_NUMBERS = PRIVATE_KEY.public_key().public_numbers()
JWKS = {
    "keys": [{
        "kty": "RSA",
        "kid": KID,
        "use": "sig",
        "alg": "RS256",
        "n": _base64url_uint(_PUBLIC_NUMBERS.n),
        "e": _base64url_uint(_PUBLIC_NUMBERS.e),
    }],
}
