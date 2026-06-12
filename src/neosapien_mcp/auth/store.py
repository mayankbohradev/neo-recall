"""Credential storage: OS keyring first, AES-GCM file fallback."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from neosapien_mcp.constants import KEYRING_SERVICE

ACCOUNT = "credentials"
FALLBACK_DIR = Path.home() / ".neo-recall"
FALLBACK_FILE = FALLBACK_DIR / "credentials.enc"


@dataclass
class StoredCredentials:
    refresh_token: str
    firebase_api_key: str
    uid: str = ""
    email: str = ""


def _scrypt_key() -> bytes:
    material = f"{KEYRING_SERVICE}:{os.uname().nodename}:{os.getlogin()}".encode()
    kdf = Scrypt(salt=b"neo-recall.v1", length=32, n=2**14, r=8, p=1)
    return kdf.derive(material)


def _encrypt(plaintext: str) -> bytes:
    key = _scrypt_key()
    aes = AESGCM(key)
    nonce = os.urandom(12)
    ct = aes.encrypt(nonce, plaintext.encode(), None)
    return nonce + ct


def _decrypt(blob: bytes) -> str:
    key = _scrypt_key()
    aes = AESGCM(key)
    nonce, ct = blob[:12], blob[12:]
    return aes.decrypt(nonce, ct, None).decode()


def _keyring_load() -> StoredCredentials | None:
    try:
        import keyring
    except ImportError:
        return None
    raw = keyring.get_password(KEYRING_SERVICE, ACCOUNT)
    if not raw:
        return None
    data = json.loads(raw)
    return StoredCredentials(**data)


def _keyring_save(creds: StoredCredentials) -> bool:
    try:
        import keyring

        keyring.set_password(KEYRING_SERVICE, ACCOUNT, json.dumps(asdict(creds)))
        return True
    except Exception:
        return False


def _keyring_clear() -> None:
    try:
        import keyring

        keyring.delete_password(KEYRING_SERVICE, ACCOUNT)
    except Exception:
        pass


def _file_load() -> StoredCredentials | None:
    if not FALLBACK_FILE.exists():
        return None
    data = json.loads(_decrypt(FALLBACK_FILE.read_bytes()))
    return StoredCredentials(**data)


def _file_save(creds: StoredCredentials) -> None:
    FALLBACK_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    FALLBACK_FILE.write_bytes(_encrypt(json.dumps(asdict(creds))))
    os.chmod(FALLBACK_FILE, 0o600)


def load() -> StoredCredentials | None:
    return _keyring_load() or _file_load()


def save(creds: StoredCredentials) -> None:
    if not _keyring_save(creds):
        _file_save(creds)


def clear() -> None:
    _keyring_clear()
    if FALLBACK_FILE.exists():
        FALLBACK_FILE.unlink()
