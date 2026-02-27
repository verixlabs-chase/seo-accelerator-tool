from app.services.portfolio.systemic_drift import detect_systemic_drift


def test_systemic_drift_detection():
    values = [-0.5, -0.2, -0.1, 0.3, -0.4]
    result = detect_systemic_drift(values)
    assert result["systemic_drift_detected"] is True