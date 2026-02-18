import json
from pathlib import Path

from app.reference_library.schema_models import MetricsArtifact, RecommendationsArtifact


def test_reference_library_seed_artifacts_match_schema():
    root = Path(__file__).resolve().parents[2]
    metrics_path = root / "Docs" / "TXT Governing Docs" / "Future Enhancements" / "reference_library" / "metrics" / "core_web_vitals.json"
    recommendations_path = (
        root
        / "Docs"
        / "TXT Governing Docs"
        / "Future Enhancements"
        / "reference_library"
        / "recommendations"
        / "perf_recommendations.json"
    )

    metrics_payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    recommendations_payload = json.loads(recommendations_path.read_text(encoding="utf-8"))

    metrics = MetricsArtifact.model_validate(metrics_payload)
    recommendations = RecommendationsArtifact.model_validate(recommendations_payload)

    rec_keys = {row.rec_key for row in recommendations.recommendations}
    for metric in metrics.metrics:
        for rec_key in metric.recommendations:
            assert rec_key in rec_keys
