import json

from app.reference_library.paths import reference_library_file
from app.reference_library.schema_models import MetricsArtifact, RecommendationsArtifact


def test_reference_library_seed_artifacts_match_schema():
    metrics_path = reference_library_file("metrics", "core_web_vitals.json")
    recommendations_path = reference_library_file("metrics", "perf_recommendations.json")

    metrics_payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    recommendations_payload = json.loads(recommendations_path.read_text(encoding="utf-8"))

    metrics = MetricsArtifact.model_validate(metrics_payload)
    recommendations = RecommendationsArtifact.model_validate(recommendations_payload)

    rec_keys = {row.rec_key for row in recommendations.recommendations}
    for metric in metrics.metrics:
        for rec_key in metric.recommendations:
            assert rec_key in rec_keys
