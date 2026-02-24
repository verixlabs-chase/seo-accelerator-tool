from __future__ import annotations

import base64
import json
import os
from typing import Any

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


_AES_GCM_NONCE_BYTES = 12


class CredentialCryptoError(RuntimeError):
    def __init__(self, message: str, *, reason_code: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


def encrypt_payload(data: dict[str, Any]) -> tuple[str, str, str]:
    plaintext = json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8")
    dek = os.urandom(32)
    payload_iv, payload_ciphertext = _aes256_gcm_encrypt(plaintext, dek)

    master_key = get_master_key()
    dek_iv, encrypted_dek = _aes256_gcm_encrypt(dek, master_key)

    blob = {
        "alg": "AES-256-GCM",
        "ciphertext_b64": _b64e(payload_ciphertext),
        "payload_iv_b64": _b64e(payload_iv),
        "encrypted_dek_b64": _b64e(encrypted_dek),
        "dek_iv_b64": _b64e(dek_iv),
    }
    key_reference = os.getenv("CREDENTIAL_MASTER_KEY_REFERENCE", "env:PLATFORM_MASTER_KEY")
    key_version = os.getenv("CREDENTIAL_MASTER_KEY_VERSION", "v1")
    return json.dumps(blob, separators=(",", ":"), sort_keys=True), key_reference, key_version


def decrypt_payload(encrypted_secret_blob: str) -> dict[str, Any]:
    try:
        payload = json.loads(encrypted_secret_blob)
    except Exception as exc:  # noqa: BLE001
        raise CredentialCryptoError(
            "Credential payload is not decryptable.",
            reason_code="invalid_credential_payload",
        ) from exc
    if not isinstance(payload, dict):
        raise CredentialCryptoError(
            "Credential payload must be a JSON object.",
            reason_code="invalid_credential_payload",
        )
    try:
        encrypted_dek = _b64d(str(payload["encrypted_dek_b64"]))
        dek_iv = _b64d(str(payload["dek_iv_b64"]))
        payload_iv = _b64d(str(payload["payload_iv_b64"]))
        ciphertext = _b64d(str(payload["ciphertext_b64"]))
    except Exception as exc:  # noqa: BLE001
        raise CredentialCryptoError(
            "Credential payload is not decryptable.",
            reason_code="invalid_credential_payload",
        ) from exc

    algorithm = str(payload.get("alg", "AES-256-CBC"))
    master_key = get_master_key()
    try:
        if algorithm == "AES-256-GCM":
            dek = _aes256_gcm_decrypt(encrypted_dek, master_key, dek_iv)
            plaintext = _aes256_gcm_decrypt(ciphertext, dek, payload_iv)
        elif algorithm == "AES-256-CBC":
            dek = _aes256_cbc_decrypt(encrypted_dek, master_key, dek_iv)
            plaintext = _aes256_cbc_decrypt(ciphertext, dek, payload_iv)
        else:
            raise CredentialCryptoError(
                f"Unsupported credential algorithm '{algorithm}'.",
                reason_code="invalid_credential_payload",
            )
    except CredentialCryptoError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise CredentialCryptoError(
            "Credential payload is not decryptable.",
            reason_code="invalid_credential_payload",
        ) from exc
    try:
        parsed = json.loads(plaintext.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise CredentialCryptoError(
            "Credential payload is not decryptable.",
            reason_code="invalid_credential_payload",
        ) from exc
    if not isinstance(parsed, dict):
        raise CredentialCryptoError(
            "Credential payload must be a JSON object.",
            reason_code="invalid_credential_payload",
        )
    return parsed


def get_master_key() -> bytes:
    raw = os.getenv("PLATFORM_MASTER_KEY", "").strip()
    if not raw:
        raise CredentialCryptoError(
            "PLATFORM_MASTER_KEY is required for credential encryption.",
            reason_code="master_key_missing",
        )
    try:
        key = base64.b64decode(raw)
    except Exception as exc:  # noqa: BLE001
        raise CredentialCryptoError(
            "PLATFORM_MASTER_KEY must be valid base64.",
            reason_code="master_key_invalid",
        ) from exc
    if len(key) != 32:
        raise CredentialCryptoError(
            "PLATFORM_MASTER_KEY must decode to 32 bytes for AES-256.",
            reason_code="master_key_invalid",
        )
    return key


def _b64e(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _b64d(raw: str) -> bytes:
    return base64.b64decode(raw.encode("ascii"))


def _aes256_gcm_encrypt(plaintext: bytes, key: bytes) -> tuple[bytes, bytes]:
    nonce = os.urandom(_AES_GCM_NONCE_BYTES)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
    return nonce, ciphertext


def _aes256_gcm_decrypt(ciphertext: bytes, key: bytes, nonce: bytes) -> bytes:
    return AESGCM(key).decrypt(nonce, ciphertext, None)


def _aes256_cbc_decrypt(ciphertext: bytes, key: bytes, iv: bytes) -> bytes:
    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
    return unpadder.update(padded) + unpadder.finalize()
