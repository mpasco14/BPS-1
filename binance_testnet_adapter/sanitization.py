from __future__ import annotations

from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


SENSITIVE_KEYS = {
    "api_key",
    "api_secret",
    "secret",
    "apiSecret",
    "apiKey",
    "signature",
    "private_key",
    "password",
    "token",
}


PLACEHOLDER_VALUES = {
    "COLE_SUA_API_KEY_TESTNET_AQUI",
    "COLE_SUA_SECRET_KEY_TESTNET_AQUI",
    "SUA_KEY_TESTNET",
    "SEU_SECRET_TESTNET",
    "SUA_API_KEY_TESTNET",
    "SUA_SECRET_KEY_TESTNET",
    "YOUR_API_KEY",
    "YOUR_API_SECRET",
    "YOUR_KEY_HERE",
    "YOUR_SECRET_HERE",
    "CHANGE_ME",
    "CHANGEME",
}


def is_sensitive_key(key: str) -> bool:
    normalized = key.strip().lower()

    return (
        normalized in {item.lower() for item in SENSITIVE_KEYS}
        or "api_key" in normalized
        or "api_secret" in normalized
        or "secret" in normalized
        or "signature" in normalized
        or "private_key" in normalized
        or "password" in normalized
        or "token" in normalized
    )


def is_placeholder_secret(value: Any) -> bool:
    if not isinstance(value, str):
        return False

    return value.strip().upper() in PLACEHOLDER_VALUES


def mask_sensitive_url(value: str) -> str:
    if "signature=" not in value:
        return value

    try:
        parsed = urlsplit(value)
        query = parse_qsl(parsed.query, keep_blank_values=True)

        masked_query = [
            (key, "***" if key.lower() == "signature" else item_value)
            for key, item_value in query
        ]

        return urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                urlencode(masked_query, doseq=True),
                parsed.fragment,
            )
        )
    except ValueError:
        return value.replace("signature=", "signature=***")


def sanitize_artifact_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        sanitized: dict[str, Any] = {}

        for key, value in payload.items():
            if is_sensitive_key(str(key)):
                sanitized[key] = "***" if value else value
            else:
                sanitized[key] = sanitize_artifact_payload(value)

        return sanitized

    if isinstance(payload, list):
        return [sanitize_artifact_payload(item) for item in payload]

    if isinstance(payload, str):
        if is_placeholder_secret(payload):
            return "***"

        if "signature=" in payload:
            return mask_sensitive_url(payload)

        return payload

    return payload