#!/usr/bin/env python3
"""InsightOS outbound local relay diagnostic and discovery agent.

This dependency-free release verifies signed synthetic receipts and checks for
supported software on loopback only. An explicit one-shot option can send one
fixed made-up check to one local model. Model names and output remain local;
customer prompts, database access, business execution, and publishing remain
refused.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from getpass import getpass
from hashlib import sha256
import hmac
import json
import os
import signal
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID, uuid4


AGENT_VERSION = "1.1.0"
PACKET_PROTOCOL_VERSION = "outbound-local-relay-packet-v1"
PACKET_KIND = "synthetic_connection_challenge"
HEARTBEAT_PROTOCOL_VERSION = "outbound-local-relay-v1"
DEFAULT_BASE_URL = "https://insightos.verixlabs.com"
MAX_RESPONSE_BYTES = 64 * 1024
MIN_INTERVAL_SECONDS = 30
MAX_INTERVAL_SECONDS = 300
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434/api/tags"
DEFAULT_LM_STUDIO_URL = "http://127.0.0.1:1234/v1/models"
MODEL_QUALIFICATION_PROMPT_VERSION = "local-model-synthetic-v1"
MODEL_QUALIFICATION_PROMPT = (
    "This is a made-up compatibility check with no customer data. "
    "Return only this exact JSON object with no markdown or extra keys: "
    '{"assessment":"needs_review","evidence":["synthetic_site_check"],'
    '"next_step":"review"}'
)
MODEL_QUALIFICATION_EXPECTED = {
    "assessment": "needs_review",
    "evidence": ["synthetic_site_check"],
    "next_step": "review",
}
EXPECTED_SAFETY = {
    "business_execution_requested": False,
    "customer_data_included": False,
    "database_access_requested": False,
    "model_execution_requested": False,
    "publishing_requested": False,
}
EXPECTED_HEARTBEAT_SAFETY = {
    "customer_prompts_allowed": False,
    "database_access_allowed": False,
    "decision_packets_enabled": False,
    "execution_allowed": False,
    "publishing_allowed": False,
}
EXPECTED_ACKNOWLEDGEMENT_SAFETY = {
    "business_work_executed": False,
    "customer_data_processed": False,
    "database_accessed": False,
    "model_called": False,
    "publishing_performed": False,
}
_STOP = False


class RelayAgentError(RuntimeError):
    """A customer-safe local relay validation or transport error."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        del req, fp, code, msg, headers, newurl
        return None


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def sign_payload(token: str, payload: dict[str, Any]) -> str:
    return hmac.new(
        token.encode("utf-8"),
        canonical_json(payload).encode("utf-8"),
        sha256,
    ).hexdigest()


def validate_local_runtime_url(value: str, *, expected_path: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
        "127.0.0.1",
        "::1",
    }:
        raise RelayAgentError("Local model discovery is restricted to loopback addresses.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise RelayAgentError("The local model discovery address is invalid.")
    if parsed.path != expected_path:
        raise RelayAgentError("The local model discovery path is not supported.")
    return value.strip()


def get_local_json(url: str, *, timeout_seconds: float = 2.0) -> dict[str, Any] | None:
    parsed = urlparse(url)
    if parsed.path not in {"/api/tags", "/v1/models"}:
        raise RelayAgentError("The local model discovery path is not supported.")
    expected_path = parsed.path
    validated = validate_local_runtime_url(url, expected_path=expected_path)
    request = Request(
        validated,
        headers={
            "Accept": "application/json",
            "User-Agent": f"InsightOS-Local-Relay/{AGENT_VERSION}",
        },
        method="GET",
    )
    try:
        with build_opener(_NoRedirect()).open(request, timeout=timeout_seconds) as response:
            if response.headers.get_content_type() != "application/json":
                return None
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, OSError):
        return None
    if len(raw) > MAX_RESPONSE_BYTES:
        return None
    try:
        parsed_body = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return parsed_body if isinstance(parsed_body, dict) else None


def post_local_json(
    url: str,
    *,
    payload: dict[str, Any],
    timeout_seconds: float = 120.0,
) -> dict[str, Any] | None:
    parsed = urlparse(url)
    if parsed.path not in {"/api/generate", "/v1/chat/completions"}:
        raise RelayAgentError("The local model qualification path is not supported.")
    validated = validate_local_runtime_url(url, expected_path=parsed.path)
    request = Request(
        validated,
        data=canonical_json(payload).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": f"InsightOS-Local-Relay/{AGENT_VERSION}",
        },
        method="POST",
    )
    try:
        with build_opener(_NoRedirect()).open(request, timeout=timeout_seconds) as response:
            if response.headers.get_content_type() != "application/json":
                return None
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, OSError):
        return None
    if len(raw) > MAX_RESPONSE_BYTES:
        return None
    try:
        parsed_body = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return parsed_body if isinstance(parsed_body, dict) else None


def discover_local_runtimes(
    *,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    lm_studio_url: str = DEFAULT_LM_STUDIO_URL,
    probe=get_local_json,  # noqa: ANN001
) -> dict[str, Any]:
    ollama_url = validate_local_runtime_url(ollama_url, expected_path="/api/tags")
    lm_studio_url = validate_local_runtime_url(lm_studio_url, expected_path="/v1/models")
    ollama_body = probe(ollama_url)
    lm_studio_body = probe(lm_studio_url)
    ollama_models = ollama_body.get("models") if isinstance(ollama_body, dict) else None
    lm_studio_models = lm_studio_body.get("data") if isinstance(lm_studio_body, dict) else None
    ollama_detected = isinstance(ollama_models, list)
    lm_studio_detected = isinstance(lm_studio_models, list)
    model_count = min(
        1000,
        (len(ollama_models) if ollama_detected else 0)
        + (len(lm_studio_models) if lm_studio_detected else 0),
    )
    if ollama_detected and lm_studio_detected:
        runtime_kind = "multiple"
    elif ollama_detected:
        runtime_kind = "ollama"
    elif lm_studio_detected:
        runtime_kind = "lm_studio"
    else:
        runtime_kind = "not_found"
    return {
        "agent_version": AGENT_VERSION,
        "runtime_kind": runtime_kind,
        "model_count": model_count,
        "ollama_detected": ollama_detected,
        "lm_studio_detected": lm_studio_detected,
        "loopback_only": True,
        "customer_data_sent": False,
        "model_called": False,
        "model_identifiers_included": False,
    }


def report_runtime_discovery(
    *,
    base_url: str,
    token: str,
    discovery: dict[str, Any],
    timeout_seconds: float = 15.0,
    now: datetime | None = None,
) -> dict[str, Any]:
    payload = {
        "discovery_id": str(uuid4()),
        **discovery,
        "observed_at": _as_utc(now or datetime.now(UTC)).isoformat(),
    }
    signature = sign_payload(token, payload)
    response = post_json(
        urljoin(f"{validate_base_url(base_url)}/", "api/v1/ai/relay/runtime-discovery"),
        token=token,
        payload={**payload, "signature": signature},
        timeout_seconds=timeout_seconds,
    )
    data = response.get("data")
    item = data.get("item") if isinstance(data, dict) else None
    if (
        not isinstance(item, dict)
        or data.get("accepted") is not True
        or item.get("runtime_kind") != discovery.get("runtime_kind")
        or item.get("model_count") != discovery.get("model_count")
        or item.get("loopback_only") is not True
        or item.get("customer_data_sent") is not False
        or item.get("model_called") is not False
        or item.get("model_identifiers_included") is not False
    ):
        raise RelayAgentError("InsightOS did not confirm the local software discovery report.")
    return item


def qualify_local_model(
    *,
    token: str,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    lm_studio_url: str = DEFAULT_LM_STUDIO_URL,
    preferred_runtime: str = "auto",
    probe=get_local_json,  # noqa: ANN001
    invoke=post_local_json,  # noqa: ANN001
) -> dict[str, Any]:
    ollama_url = validate_local_runtime_url(ollama_url, expected_path="/api/tags")
    lm_studio_url = validate_local_runtime_url(lm_studio_url, expected_path="/v1/models")
    ollama_body = probe(ollama_url)
    lm_studio_body = probe(lm_studio_url)
    ollama_models = ollama_body.get("models") if isinstance(ollama_body, dict) else None
    lm_studio_models = lm_studio_body.get("data") if isinstance(lm_studio_body, dict) else None
    candidates: list[tuple[str, str, str]] = []
    if isinstance(ollama_models, list):
        for item in ollama_models:
            name = item.get("name") if isinstance(item, dict) else None
            if isinstance(name, str) and 1 <= len(name) <= 300:
                candidates.append(("ollama", name, ollama_url.replace("/api/tags", "/api/generate")))
                break
    if isinstance(lm_studio_models, list):
        for item in lm_studio_models:
            name = item.get("id") if isinstance(item, dict) else None
            if isinstance(name, str) and 1 <= len(name) <= 300:
                candidates.append(
                    (
                        "lm_studio",
                        name,
                        lm_studio_url.replace("/v1/models", "/v1/chat/completions"),
                    )
                )
                break
    if preferred_runtime not in {"auto", "ollama", "lm_studio"}:
        raise RelayAgentError("Choose auto, ollama, or lm_studio for the local check.")
    selected = next(
        (
            candidate
            for candidate in candidates
            if preferred_runtime == "auto" or candidate[0] == preferred_runtime
        ),
        None,
    )
    if selected is None:
        raise RelayAgentError("No local model is available for the requested synthetic check.")
    runtime_kind, model_name, model_url = selected
    if runtime_kind == "ollama":
        request_payload = {
            "model": model_name,
            "prompt": MODEL_QUALIFICATION_PROMPT,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
        }
    else:
        request_payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": MODEL_QUALIFICATION_PROMPT}],
            "temperature": 0,
            "max_tokens": 120,
        }
    started = time.monotonic()
    response = invoke(model_url, payload=request_payload, timeout_seconds=120.0)
    latency_ms = min(120000, max(0, round((time.monotonic() - started) * 1000)))
    content: object = None
    if runtime_kind == "ollama" and isinstance(response, dict):
        content = response.get("response")
    elif runtime_kind == "lm_studio" and isinstance(response, dict):
        choices = response.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            message = choices[0].get("message")
            if isinstance(message, dict):
                content = message.get("content")
    model_response_received = isinstance(content, str)
    output_json_valid = False
    required_contract_matched = False
    if isinstance(content, str) and len(content.encode("utf-8")) <= 4096:
        try:
            parsed_output = json.loads(content)
        except json.JSONDecodeError:
            parsed_output = None
        output_json_valid = isinstance(parsed_output, dict)
        required_contract_matched = parsed_output == MODEL_QUALIFICATION_EXPECTED
    return {
        "agent_version": AGENT_VERSION,
        "runtime_kind": runtime_kind,
        "local_model_fingerprint": hmac.new(
            token.encode("utf-8"),
            f"{runtime_kind}:{model_name}".encode("utf-8"),
            sha256,
        ).hexdigest(),
        "prompt_version": MODEL_QUALIFICATION_PROMPT_VERSION,
        "status": (
            "passed" if output_json_valid and required_contract_matched else "failed"
        ),
        "latency_ms": latency_ms,
        "output_json_valid": output_json_valid,
        "required_contract_matched": required_contract_matched,
        "synthetic_input_only": True,
        "model_call_attempted": True,
        "model_response_received": model_response_received,
        "customer_data_sent": False,
        "raw_model_identifier_sent": False,
        "model_output_sent": False,
        "customer_work_allowed": False,
        "publishing_allowed": False,
    }


def report_model_qualification(
    *,
    base_url: str,
    token: str,
    qualification: dict[str, Any],
    timeout_seconds: float = 15.0,
    now: datetime | None = None,
) -> dict[str, Any]:
    payload = {
        "qualification_id": str(uuid4()),
        **qualification,
        "observed_at": _as_utc(now or datetime.now(UTC)).isoformat(),
    }
    signature = sign_payload(token, payload)
    response = post_json(
        urljoin(f"{validate_base_url(base_url)}/", "api/v1/ai/relay/model-qualification"),
        token=token,
        payload={**payload, "signature": signature},
        timeout_seconds=timeout_seconds,
    )
    data = response.get("data")
    item = data.get("item") if isinstance(data, dict) else None
    if (
        not isinstance(item, dict)
        or data.get("accepted") is not True
        or item.get("status") != qualification.get("status")
        or item.get("synthetic_input_only") is not True
        or item.get("model_call_attempted") is not True
        or item.get("model_response_received")
        is not qualification.get("model_response_received")
        or item.get("customer_data_sent") is not False
        or item.get("raw_model_identifier_sent") is not False
        or item.get("model_output_sent") is not False
        or item.get("customer_work_allowed") is not False
        or item.get("publishing_allowed") is not False
    ):
        raise RelayAgentError("InsightOS did not confirm the synthetic local model check.")
    return item


def build_acknowledgement(
    packet: dict[str, Any],
    *,
    token: str,
    now: datetime | None = None,
) -> tuple[str, dict[str, str]]:
    current_time = _as_utc(now or datetime.now(UTC))
    expected_keys = {
        "acknowledge_path",
        "artifact_hash",
        "expires_at",
        "id",
        "issued_at",
        "kind",
        "payload",
        "protocol_version",
        "safety",
        "signature",
        "signature_algorithm",
    }
    if set(packet) != expected_keys:
        raise RelayAgentError("Refused an unexpected relay packet shape.")
    packet_id = _required_text(packet, "id", maximum=36)
    try:
        UUID(packet_id)
    except ValueError as exc:
        raise RelayAgentError("Refused a relay packet with an invalid identity.") from exc
    if packet.get("kind") != PACKET_KIND:
        raise RelayAgentError("Refused a relay packet that is not a synthetic receipt check.")
    if packet.get("protocol_version") != PACKET_PROTOCOL_VERSION:
        raise RelayAgentError("Refused an unsupported relay packet version.")
    if packet.get("signature_algorithm") != "hmac-sha256":
        raise RelayAgentError("Refused an unsupported relay signature method.")
    if packet.get("safety") != EXPECTED_SAFETY:
        raise RelayAgentError("Refused a relay packet that requested customer or business work.")

    issued_at = _parse_timestamp(_required_text(packet, "issued_at", maximum=40))
    expires_at = _parse_timestamp(_required_text(packet, "expires_at", maximum=40))
    if issued_at > current_time + timedelta(seconds=60) or expires_at <= current_time:
        raise RelayAgentError("Refused a relay packet outside its short validity window.")
    if (expires_at - issued_at).total_seconds() > 5 * 60 + 1:
        raise RelayAgentError("Refused a relay packet with an excessive validity window.")

    artifact_hash = _hex_digest(packet.get("artifact_hash"), "packet fingerprint")
    signature = _hex_digest(packet.get("signature"), "packet signature")
    payload = packet.get("payload")
    if not isinstance(payload, dict) or set(payload) != {
        "challenge",
        "expected_action",
        "response_hash_input",
    }:
        raise RelayAgentError("Refused an unexpected synthetic challenge shape.")
    challenge = _required_text(payload, "challenge", minimum=16, maximum=64)
    if payload.get("expected_action") != "acknowledge_synthetic_receipt":
        raise RelayAgentError("Refused an unsupported synthetic receipt action.")
    if payload.get("response_hash_input") != f"{packet_id}:<challenge>:received":
        raise RelayAgentError("Refused a changed synthetic receipt formula.")
    acknowledge_path = _required_text(packet, "acknowledge_path", maximum=120)
    if acknowledge_path != f"/api/v1/ai/relay/packets/{packet_id}/acknowledge":
        raise RelayAgentError("Refused a changed relay acknowledgement destination.")

    signed_body = {
        key: value
        for key, value in packet.items()
        if key not in {"acknowledge_path", "signature", "signature_algorithm"}
    }
    expected_signature = sign_payload(token, signed_body)
    if not hmac.compare_digest(expected_signature, signature):
        raise RelayAgentError("Refused a relay packet with an invalid signature.")

    response_hash = sha256(f"{packet_id}:{challenge}:received".encode()).hexdigest()
    ack_signature_body = {
        "packet_id": packet_id,
        "packet_artifact_hash": artifact_hash,
        "response_hash": response_hash,
    }
    return acknowledge_path, {
        "packet_artifact_hash": artifact_hash,
        "response_hash": response_hash,
        "signature": sign_payload(token, ack_signature_body),
    }


def poll_once(
    *,
    base_url: str,
    token: str,
    timeout_seconds: float = 15.0,
    now: datetime | None = None,
) -> str:
    normalized_base = validate_base_url(base_url)
    heartbeat = post_json(
        urljoin(f"{normalized_base}/", "api/v1/ai/relay/heartbeat"),
        token=token,
        payload={},
        timeout_seconds=timeout_seconds,
    )
    data = heartbeat.get("data")
    if (
        not isinstance(data, dict)
        or data.get("accepted") is not True
        or data.get("protocol_version") != HEARTBEAT_PROTOCOL_VERSION
        or data.get("safety") != EXPECTED_HEARTBEAT_SAFETY
    ):
        raise RelayAgentError("InsightOS did not confirm the outbound relay connection.")
    work = data.get("work")
    if not isinstance(work, list) or len(work) > 1:
        raise RelayAgentError("Refused an unexpected relay work response.")
    if not work:
        return "connected"
    packet = work[0]
    if not isinstance(packet, dict):
        raise RelayAgentError("Refused an invalid relay packet.")
    acknowledge_path, acknowledgement = build_acknowledgement(
        packet,
        token=token,
        now=now,
    )
    response = post_json(
        urljoin(f"{normalized_base}/", acknowledge_path.lstrip("/")),
        token=token,
        payload=acknowledgement,
        timeout_seconds=timeout_seconds,
    )
    result = response.get("data")
    if (
        not isinstance(result, dict)
        or result.get("state") != "verified"
        or result.get("safety") != EXPECTED_ACKNOWLEDGEMENT_SAFETY
    ):
        raise RelayAgentError("InsightOS did not verify the synthetic receipt check.")
    return "diagnostic_verified"


def post_json(
    url: str,
    *,
    token: str,
    payload: dict[str, Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    request = Request(
        url,
        data=canonical_json(payload).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": f"InsightOS-Local-Relay/{AGENT_VERSION}",
        },
        method="POST",
    )
    opener = build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            content_type = response.headers.get_content_type()
            if content_type != "application/json":
                raise RelayAgentError("InsightOS returned an unexpected response type.")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        raise RelayAgentError(f"InsightOS returned HTTP {exc.code}.") from exc
    except URLError as exc:
        raise RelayAgentError("Could not reach InsightOS over the outbound connection.") from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise RelayAgentError("InsightOS returned an oversized relay response.")
    try:
        parsed = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RelayAgentError("InsightOS returned an invalid relay response.") from exc
    if not isinstance(parsed, dict):
        raise RelayAgentError("InsightOS returned an invalid relay response.")
    return parsed


def validate_base_url(value: str) -> str:
    parsed = urlparse(value.strip())
    local_http = parsed.scheme == "http" and parsed.hostname in {
        "127.0.0.1",
        "::1",
        "localhost",
    }
    if parsed.scheme != "https" and not local_http:
        raise RelayAgentError("The relay requires HTTPS except for local development.")
    if not parsed.hostname or parsed.username or parsed.password:
        raise RelayAgentError("The InsightOS address is invalid.")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise RelayAgentError("The InsightOS address must be an origin without a path or query.")
    return value.strip().rstrip("/")


def validate_token(value: str) -> str:
    token = value.strip()
    if not token.startswith("iosr_") or len(token) < 40 or len(token) > 100:
        raise RelayAgentError("INSIGHTOS_RELAY_TOKEN is missing or invalid.")
    return token


def _required_text(
    payload: dict[str, Any],
    key: str,
    *,
    minimum: int = 1,
    maximum: int,
) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not minimum <= len(value) <= maximum:
        raise RelayAgentError(f"Refused an invalid relay {key.replace('_', ' ')}.")
    return value


def _hex_digest(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdefABCDEF" for char in value)
    ):
        raise RelayAgentError(f"Refused an invalid {label}.")
    return value.lower()


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RelayAgentError("Refused an invalid relay timestamp.") from exc
    if parsed.tzinfo is None:
        raise RelayAgentError("Refused a relay timestamp without a timezone.")
    return parsed.astimezone(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _stop(_signum, _frame) -> None:  # noqa: ANN001
    global _STOP
    _STOP = True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify an outbound InsightOS local relay connection.",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("INSIGHTOS_BASE_URL", DEFAULT_BASE_URL),
        help="InsightOS origin. HTTPS is required except for localhost.",
    )
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument("--lm-studio-url", default=DEFAULT_LM_STUDIO_URL)
    parser.add_argument(
        "--skip-discovery",
        action="store_true",
        help="Skip the loopback-only local software check.",
    )
    parser.add_argument(
        "--check-model",
        action="store_true",
        help="Run one fixed made-up compatibility check against one local model.",
    )
    parser.add_argument(
        "--runtime",
        choices=("auto", "ollama", "lm_studio"),
        default="auto",
        help="Local runtime to use for the explicit synthetic model check.",
    )
    parser.add_argument("--once", action="store_true", help="Check once, then exit.")
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Seconds between outbound checks (30-300).",
    )
    args = parser.parse_args(argv)
    try:
        token_value = os.environ.get("INSIGHTOS_RELAY_TOKEN", "")
        if not token_value and sys.stdin.isatty():
            token_value = getpass("Paste the one-time InsightOS relay key: ")
        token = validate_token(token_value)
        base_url = validate_base_url(args.base_url)
        interval = max(MIN_INTERVAL_SECONDS, min(MAX_INTERVAL_SECONDS, args.interval))
        if args.check_model and not args.once:
            raise RelayAgentError("The local model check requires --once so it cannot repeat.")
        if not args.skip_discovery:
            discovery = discover_local_runtimes(
                ollama_url=args.ollama_url,
                lm_studio_url=args.lm_studio_url,
            )
    except RelayAgentError as exc:
        print(f"Relay setup error: {exc}", file=sys.stderr)
        return 2

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    print(
        "InsightOS relay started. Customer prompts and business work are disabled."
    )
    qualification_failed = False
    if not args.skip_discovery:
        try:
            report_runtime_discovery(
                base_url=base_url,
                token=token,
                discovery=discovery,
            )
            runtime_label = {
                "not_found": "No supported local model software found",
                "ollama": "Ollama found",
                "lm_studio": "LM Studio found",
                "multiple": "Ollama and LM Studio found",
            }[discovery["runtime_kind"]]
            print(f"{runtime_label} ({discovery['model_count']} local models). No model was called.")
        except RelayAgentError as exc:
            print(f"Local software discovery failed: {exc}", file=sys.stderr)
            if args.once:
                return 1
    if args.check_model:
        try:
            qualification = qualify_local_model(
                token=token,
                ollama_url=args.ollama_url,
                lm_studio_url=args.lm_studio_url,
                preferred_runtime=args.runtime,
            )
            report_model_qualification(
                base_url=base_url,
                token=token,
                qualification=qualification,
            )
            qualification_failed = qualification["status"] != "passed"
            if qualification_failed:
                print(
                    "Synthetic local model check needs attention. "
                    "No model output or customer data was sent."
                )
            else:
                print(
                    "Synthetic local model check passed. "
                    "The model name and output stayed on this computer."
                )
        except RelayAgentError as exc:
            print(f"Synthetic local model check failed: {exc}", file=sys.stderr)
            return 1
    while not _STOP:
        try:
            result = poll_once(base_url=base_url, token=token)
            if result == "diagnostic_verified":
                print("Signed synthetic connection check verified.")
            elif args.once:
                print("Outbound connection verified; no synthetic check was waiting.")
        except RelayAgentError as exc:
            print(f"Relay check failed: {exc}", file=sys.stderr)
            if args.once:
                return 1
        if args.once:
            return 1 if qualification_failed else 0
        time.sleep(interval)
    print("InsightOS relay stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
