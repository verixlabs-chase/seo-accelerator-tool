from __future__ import annotations

import json
import httpx

from app.providers.google_reviews import (
    GoogleBusinessProfileReviewsProvider,
    GoogleReviewsProviderError,
)


def test_google_reviews_provider_normalizes_owned_review_and_reply():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("Authorization")
        return httpx.Response(
            200,
            json={
                "reviews": [
                    {
                        "name": "accounts/123/locations/456/reviews/review-1",
                        "reviewId": "review-1",
                        "reviewer": {"displayName": "Alex R."},
                        "starRating": "FIVE",
                        "comment": "Fast and professional.",
                        "createTime": "2026-08-01T12:00:00Z",
                        "updateTime": "2026-08-02T12:00:00Z",
                        "reviewReply": {
                            "comment": "Thank you, Alex!",
                            "updateTime": "2026-08-03T12:00:00Z",
                        },
                    }
                ],
                "averageRating": 4.8,
                "totalReviewCount": 142,
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = GoogleBusinessProfileReviewsProvider(
            access_token="token",
            client=client,
        )
        result = provider.list_reviews(parent="accounts/123/locations/456")

    assert captured["authorization"] == "Bearer token"
    assert "pageSize=50" in captured["url"]
    assert "orderBy=updateTime" in captured["url"]
    review = result["items"][0]
    assert review["external_review_id"] == "review-1"
    assert review["source_name"] == "Google Business Profile"
    assert review["rating"] == 5.0
    assert review["response_status"] == "responded"
    assert review["response_text"] == "Thank you, Alex!"
    assert result["average_rating"] == 4.8
    assert result["total_review_count"] == 142


def test_google_reviews_provider_uses_safe_connection_errors():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": {"code": 403}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = GoogleBusinessProfileReviewsProvider(
            access_token="expired",
            client=client,
        )
        try:
            provider.list_reviews(parent="accounts/123/locations/456")
        except ValueError as exc:
            message = str(exc)
        else:
            raise AssertionError("Expected rejected access to fail.")

    assert "access needs attention" in message.lower()
    assert "token" not in message.lower()


def test_google_reviews_provider_posts_exact_approved_reply_and_returns_receipt():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["body"] = request.content.decode("utf-8")
        return httpx.Response(
            200,
            json={
                "comment": "Thank you for the feedback.",
                "updateTime": "2026-08-10T19:30:00Z",
                "reviewReplyState": "PUBLISHED",
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = GoogleBusinessProfileReviewsProvider(access_token="token", client=client)
        receipt = provider.update_reply(
            review_name="accounts/123/locations/456/reviews/review-1",
            comment="Thank you for the feedback.",
        )

    assert captured["method"] == "PUT"
    assert captured["url"].endswith("/accounts/123/locations/456/reviews/review-1/reply")
    assert json.loads(captured["body"]) == {"comment": "Thank you for the feedback."}
    assert receipt["reply_state"] == "PUBLISHED"
    assert receipt["update_time"].isoformat() == "2026-08-10T19:30:00+00:00"


def test_google_reviews_provider_categorizes_denied_write_access():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": {"code": 403}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = GoogleBusinessProfileReviewsProvider(access_token="token", client=client)
        try:
            provider.update_reply(
                review_name="accounts/123/locations/456/reviews/review-1",
                comment="Thank you.",
            )
        except GoogleReviewsProviderError as exc:
            error = exc
        else:
            raise AssertionError("Expected Google to reject write access.")

    assert error.reason_code == "review_reply_access_denied"
    assert error.retryable is False
    assert "token" not in str(error).lower()
