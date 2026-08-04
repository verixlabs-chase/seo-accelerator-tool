import html as html_lib
import re
from urllib.parse import urljoin, urlparse


def parse_signals(url: str, html: str) -> dict:
    lower = html.lower()
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    title = _clean_visible_text(title_match.group(1), limit=320) if title_match else None
    canonical_match = re.search(
        r'<link[^>]+rel=["\']canonical["\'][^>]*href=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    )
    canonical = canonical_match.group(1).strip() if canonical_match else None
    meta_desc_match = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]*content=["\']([^"\']*)["\']',
        html,
        re.IGNORECASE,
    )
    meta_description = (
        _clean_visible_text(meta_desc_match.group(1), limit=500)
        if meta_desc_match
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
    body_text_excerpt = _clean_visible_text(body_html, limit=2000)
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
        "title": title,
        "canonical": canonical,
        "meta_description": meta_description,
        "heading_text": heading_text,
        "body_text_excerpt": body_text_excerpt,
        "h1_count": h1_count,
        "internal_links": internal_links,
        "is_indexable": is_indexable,
    }


def _clean_visible_text(value: str, *, limit: int) -> str | None:
    without_tags = re.sub(r"<[^>]+>", " ", str(value))
    cleaned = re.sub(r"\s+", " ", html_lib.unescape(without_tags)).strip()
    return cleaned[:limit] or None


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
        if parsed.netloc != origin.netloc:
            continue
        found.append(absolute)
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
    canonical = signals.get("canonical")
    if canonical and not canonical.startswith("http"):
        issues.append(_issue("invalid_canonical", "medium", {"canonical": canonical}))
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
