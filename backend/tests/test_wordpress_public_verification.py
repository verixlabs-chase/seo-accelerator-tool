from __future__ import annotations

from app.services import wordpress_public_verification_service as verification


def _result(mutation_id: str, target_url: str = "/") -> dict:
    return {
        "mutation_id": mutation_id,
        "target_url": target_url,
        "after_state": {},
        "rollback_payload": {"restore": True},
    }


def test_public_verification_checks_approved_values_on_live_html(monkeypatch) -> None:
    fetches: list[str] = []
    html = """
    <html><head>
      <title>Reno Junk Removal</title>
      <meta name="description" content="Fast, careful junk removal in Reno.">
      <script type="application/ld+json">{"@context":"https://schema.org","@type":"Service"}</script>
    </head><body>
      <h2 id="junk-removal">Junk removal</h2>
      <a href="/services/junk-removal">Junk removal</a>
    </body></html>
    """

    def fake_fetch(url: str, *, timeout_seconds: int) -> str:
        fetches.append(url)
        assert timeout_seconds == 8
        return html

    monkeypatch.setattr(verification, "_fetch_public_html", fake_fetch)
    mutations = [
        {
            "mutation_id": "title",
            "action": "update_meta_title",
            "target_url": "/",
            "payload": {"title": "Reno Junk Removal"},
        },
        {
            "mutation_id": "description",
            "action": "update_meta_description",
            "target_url": "/",
            "payload": {"description": "Fast, careful junk removal in Reno."},
        },
        {
            "mutation_id": "link",
            "action": "insert_internal_link",
            "target_url": "/",
            "payload": {
                "target_url": "/services/junk-removal",
                "anchor_text": "Junk removal",
            },
        },
        {
            "mutation_id": "anchor",
            "action": "create_internal_anchor",
            "target_url": "/",
            "payload": {"anchor_text": "Junk removal"},
        },
        {
            "mutation_id": "schema",
            "action": "add_schema_markup",
            "target_url": "/",
            "payload": {"schema_type": "Service", "schema_json": {"@type": "Service"}},
        },
    ]

    result = verification.verify_public_mutation_delivery(
        base_url="https://example.com",
        mutations=mutations,
        results=[_result(item["mutation_id"]) for item in mutations],
        timeout_seconds=8,
    )

    assert result["passed"] is True
    assert result["pages_checked"] == 1
    assert result["checks_total"] == 5
    assert result["checks_passed"] == 5
    assert result["checks_failed"] == 0
    assert result["rollback_available"] is True
    assert len(fetches) == 1
    assert all(item["status"] == "verified" for item in result["results"])


def test_public_verification_records_failure_and_draft_exception(monkeypatch) -> None:
    monkeypatch.setattr(
        verification,
        "_fetch_public_html",
        lambda url, *, timeout_seconds: "<html><head><title>Old title</title></head></html>",
    )
    mutations = [
        {
            "mutation_id": "title",
            "action": "update_meta_title",
            "target_url": "/",
            "payload": {"title": "Approved title"},
        },
        {
            "mutation_id": "draft",
            "action": "publish_content_page",
            "target_url": "/new-page",
            "payload": {"title": "New page", "publication_state": "draft"},
        },
    ]
    results = [
        _result("title"),
        {
            **_result("draft", "/new-page"),
            "after_state": {"post_id": 123, "target_url": "https://example.com/new-page"},
        },
    ]

    result = verification.verify_public_mutation_delivery(
        base_url="https://example.com",
        mutations=mutations,
        results=results,
        timeout_seconds=5,
    )

    assert result["passed"] is False
    assert result["checks_failed"] == 1
    assert result["rollback_available"] is True
    assert result["results"][0]["status"] == "failed"
    assert result["results"][1]["status"] == "not_public"
    assert "draft" in result["results"][1]["message"].lower()


def test_public_verification_rejects_a_result_url_on_another_host(monkeypatch) -> None:
    monkeypatch.setattr(
        verification,
        "_fetch_public_html",
        lambda url, *, timeout_seconds: (_ for _ in ()).throw(AssertionError("must not fetch")),
    )
    result = verification.verify_public_mutation_delivery(
        base_url="https://example.com",
        mutations=[
            {
                "mutation_id": "host-check",
                "action": "update_meta_title",
                "target_url": "/",
                "payload": {"title": "Approved title"},
            }
        ],
        results=[
            {
                **_result("host-check"),
                "after_state": {"target_url": "https://attacker.example/changed"},
            }
        ],
        timeout_seconds=5,
    )

    assert result["passed"] is False
    assert result["checks_failed"] == 1
    assert "connected website" in result["results"][0]["message"]
