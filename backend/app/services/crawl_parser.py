import html as html_lib
import hashlib
import json
import re
from urllib.parse import urljoin, urlparse


def parse_signals(url: str, html: str) -> dict:
    lower = html.lower()
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = _clean_visible_text(title_match.group(1), limit=320) if title_match else None
    raw_canonical = None
    for link_tag in re.findall(r"<link\b[^>]*>", html, re.IGNORECASE):
        attributes = _html_attributes(link_tag)
        rel_values = str(attributes.get("rel") or "").lower().split()
        if "canonical" in rel_values and attributes.get("href"):
            raw_canonical = str(attributes["href"]).strip()
            break
    canonical = _absolute_http_url(url, raw_canonical) if raw_canonical else None
    raw_meta_description = None
    for meta_tag in re.findall(r"<meta\b[^>]*>", html, re.IGNORECASE):
        attributes = _html_attributes(meta_tag)
        if str(attributes.get("name") or "").lower() == "description":
            raw_meta_description = str(attributes.get("content") or "")
            break
    meta_description = (
        _clean_visible_text(raw_meta_description, limit=500)
        if raw_meta_description is not None
        else None
    )
    h1_count = len(re.findall(r"<h1\b", lower))
    heading_values = []
    for match in re.finditer(r"<h[12]\b[^>]*>(.*?)</h[12]>", html, re.IGNORECASE | re.DOTALL):
        heading = _clean_visible_text(match.group(1), limit=320)
        if heading and heading not in heading_values:
            heading_values.append(heading)
        if len(heading_values) >= 12:
            break
    heading_text = " | ".join(heading_values)[:1000] or None
    body_html = re.sub(
        r"<(?:script|style|noscript|svg)\b[^>]*>.*?</(?:script|style|noscript|svg)>",
        " ",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    body_html = re.sub(r"<head\b[^>]*>.*?</head>", " ", body_html, flags=re.IGNORECASE | re.DOTALL)
    body_text = _clean_visible_text(body_html, limit=100000)
    body_text_excerpt = body_text[:2000] if body_text else None
    normalized_body = re.sub(r"\s+", " ", (body_text or "").lower()).strip()
    word_count = len(normalized_body.split()) if normalized_body else 0
    content_hash = (
        hashlib.sha256(normalized_body.encode("utf-8")).hexdigest()
        if len(normalized_body) >= 100 and word_count >= 20
        else None
    )
    structured_data_types, structured_data_errors = _structured_data(html)
    origin = urlparse(url)
    internal_links = len(
        re.findall(
            rf'<a[^>]+href=["\'](?:/|https?://{re.escape(origin.netloc)})',
            html,
            re.IGNORECASE,
        )
    )
    is_indexable = "noindex" not in lower
    return {
        "page_url": url,
        "title": title,
        "canonical": canonical,
        "raw_canonical": raw_canonical,
        "meta_description": meta_description,
        "heading_text": heading_text,
        "body_text_excerpt": body_text_excerpt,
        "content_hash": content_hash,
        "word_count": word_count,
        "h1_count": h1_count,
        "internal_links": internal_links,
        "is_indexable": is_indexable,
        "structured_data_types": structured_data_types,
        "structured_data_errors": structured_data_errors,
    }


def _clean_visible_text(value: str, *, limit: int) -> str | None:
    without_tags = re.sub(r"<[^>]+>", " ", str(value))
    cleaned = re.sub(r"\s+", " ", html_lib.unescape(without_tags)).strip()
    return cleaned[:limit] or None


def _html_attributes(tag: str) -> dict[str, str]:
    return {
        name.lower(): value
        for name, _quote, value in re.findall(
            r"([:\w-]+)\s*=\s*([\"'])(.*?)\2",
            tag,
            re.IGNORECASE | re.DOTALL,
        )
    }


def extract_internal_links(current_url: str, html: str, max_links: int = 50) -> list[str]:
    origin = urlparse(current_url)
    if not origin.scheme or not origin.netloc:
        return []
    pattern = re.compile(r'<a[^>]+href=["\']([^"\']+)["\']', re.IGNORECASE)
    found: list[str] = []
    for match in pattern.finditer(html):
        href = match.group(1).strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        absolute = urljoin(current_url, href)
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"}:
            continue
        if parsed.netloc.lower() != origin.netloc.lower():
            continue
        normalized = parsed._replace(fragment="").geturl()
        if normalized in found:
            continue
        found.append(normalized)
        if len(found) >= max_links:
            break
    return found


def build_issue_taxonomy(status_code: int | None, signals: dict) -> list[dict]:
    issues: list[dict] = []
    if status_code is None or status_code >= 400:
        issues.append(_issue("http_error", "high", {"status_code": status_code}))
    if not signals.get("title"):
        issues.append(_issue("missing_title", "high", {}))
    if not signals.get("meta_description"):
        issues.append(_issue("missing_meta_description", "medium", {}))
    raw_canonical = signals.get("raw_canonical")
    canonical = signals.get("canonical")
    if raw_canonical and not canonical:
        issues.append(_issue("invalid_canonical", "medium", {"canonical": raw_canonical}))
    elif canonical:
        page_host = urlparse(str(signals.get("final_url") or signals.get("page_url") or "")).netloc
        canonical_host = urlparse(canonical).netloc
        if page_host and canonical_host and page_host.lower() != canonical_host.lower():
            issues.append(
                _issue(
                    "canonical_external",
                    "medium",
                    {
                        "page_url": signals.get("page_url"),
                        "canonical_url": canonical,
                    },
                )
            )
        elif (
            signals.get("is_indexable", True)
            and _comparable_url(canonical)
            != _comparable_url(str(signals.get("final_url") or signals.get("page_url") or ""))
        ):
            issues.append(
                _issue(
                    "canonical_points_elsewhere",
                    "medium",
                    {
                        "page_url": signals.get("page_url"),
                        "canonical_url": canonical,
                    },
                )
            )
    redirect_chain = signals.get("redirect_chain")
    if isinstance(redirect_chain, list) and len(redirect_chain) > 1:
        issues.append(
            _issue(
                "redirect_chain",
                "medium",
                {
                    "requested_url": signals.get("page_url"),
                    "final_url": signals.get("final_url"),
                    "redirect_count": len(redirect_chain),
                    "redirect_chain": redirect_chain,
                },
            )
        )
    if signals.get("structured_data_errors", 0) > 0:
        issues.append(
            _issue(
                "invalid_structured_data",
                "medium",
                {
                    "invalid_blocks": signals.get("structured_data_errors"),
                    "detected_types": signals.get("structured_data_types", []),
                },
            )
        )
    if signals.get("h1_count", 0) == 0:
        issues.append(_issue("missing_h1", "medium", {}))
    if signals.get("h1_count", 0) > 1:
        issues.append(_issue("multiple_h1", "low", {"h1_count": signals.get("h1_count")}))
    if not signals.get("is_indexable", True):
        issues.append(_issue("non_indexable", "high", {}))
    if signals.get("internal_links", 0) == 0:
        issues.append(_issue("no_internal_links", "low", {}))
    return issues


def _issue(code: str, severity: str, details: dict) -> dict:
    return {"issue_code": code, "severity": severity, "details": details}


def _absolute_http_url(page_url: str, value: str) -> str | None:
    try:
        absolute = urljoin(page_url, value)
        parsed = urlparse(absolute)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return parsed._replace(fragment="").geturl()


def _comparable_url(value: str) -> str:
    try:
        parsed = urlparse(value)
    except ValueError:
        return value.rstrip("/").lower()
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    return parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        path=path,
        fragment="",
    ).geturl()


def _structured_data(html: str) -> tuple[list[str], int]:
    pattern = re.compile(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.IGNORECASE | re.DOTALL,
    )
    types: set[str] = set()
    errors = 0
    for match in pattern.finditer(html):
        payload = html_lib.unescape(match.group(1)).strip()
        try:
            parsed = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            errors += 1
            continue
        _collect_schema_types(parsed, types)
    return sorted(types), errors


def _collect_schema_types(value: object, types: set[str]) -> None:
    if isinstance(value, dict):
        raw_type = value.get("@type")
        if isinstance(raw_type, str) and raw_type.strip():
            types.add(raw_type.strip())
        elif isinstance(raw_type, list):
            types.update(str(item).strip() for item in raw_type if str(item).strip())
        for child in value.values():
            _collect_schema_types(child, types)
    elif isinstance(value, list):
        for child in value:
            _collect_schema_types(child, types)
