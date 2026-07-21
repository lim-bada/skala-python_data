"""창의적 개인 실습의 로그 검증·이상 탐지·원인 분석 동작을 검증한다."""

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import IsolationForest

from advanced import (
    ANOMALY_FEATURES,
    aggregate_time_windows,
    analyze_incidents,
    demo_invalid_records,
    detect_anomalies,
    evaluate_detection,
    inject_incident,
    mask_ip,
    render_report,
    save_outputs,
    severity_from_error_rate,
    validate_records,
)
from config import CONFIG, Config


def sample_log(timestamp: str = "2025-03-05T14:00:00") -> dict[str, object]:
    """단위 테스트에서 재사용할 정상 웹 로그를 반환한다."""
    return {
        "ip": "192.168.0.10",
        "timestamp": timestamp,
        "method": "GET",
        "path": "/api/v1/search",
        "status": 200,
        "bytes": 1024,
        "user_agent": "pytest/1.0",
    }


def test_validation_separates_valid_and_three_invalid_logs() -> None:
    """STEP 1에서 정상 1건과 서로 다른 오염 로그 3건을 정확히 분리한다."""
    valid, invalid = validate_records([sample_log(), *demo_invalid_records()])

    assert len(valid) == 1
    assert len(invalid) == 3
    invalid_fields = {entry["errors"][0]["loc"][0] for entry in invalid}
    assert invalid_fields == {"ip", "status", "bytes"}


def test_incident_injection_preserves_source_and_multiplies_only_target() -> None:
    """STEP 2가 원본을 바꾸지 않고 지정된 경로·시간 로그만 증폭한다."""
    source = pd.DataFrame(
        [
            sample_log("2025-03-05T14:00:00"),
            sample_log("2025-03-05T14:05:00"),
            {**sample_log("2025-03-05T14:00:00"), "path": "/health"},
        ]
    )
    source["timestamp"] = pd.to_datetime(source["timestamp"])
    original = source.copy(deep=True)
    config = Config(traffic_multiplier=3)

    injected = inject_incident(source, config)

    pd.testing.assert_frame_equal(source, original)
    target = injected[injected["path"] == "/api/v1/search"]
    assert len(injected) == 7
    assert len(target) == 6
    assert target["status"].eq(503).all()


def test_time_window_aggregation_calculates_error_rate() -> None:
    """STEP 3이 5분 구간 요청량과 5xx 오류율을 정확히 계산한다."""
    records = []
    for index in range(10):
        records.append(
            {
                **sample_log(f"2025-03-05T14:00:{index:02d}"),
                "status": 503 if index < 2 else 200,
                "ip": f"192.168.0.{index + 1}",
            }
        )
    logs = pd.DataFrame(records)
    logs["timestamp"] = pd.to_datetime(logs["timestamp"])

    result = aggregate_time_windows(logs, window_minutes=5)

    assert len(result) == 1
    assert result.loc[0, "request_count"] == 10
    assert result.loc[0, "error_5xx_count"] == 2
    assert result.loc[0, "error_rate_5xx"] == pytest.approx(0.2)


def test_detector_learns_only_rows_before_baseline_end() -> None:
    """STEP 4가 장애 이후 극단값을 학습하지 않고 이상으로 탐지한다."""
    rng = np.random.default_rng(42)
    timestamps = pd.date_range("2025-03-01", periods=153, freq="5min")
    normal = rng.normal(100, 3, size=(150, len(ANOMALY_FEATURES)))
    extreme = np.full((3, len(ANOMALY_FEATURES)), 1000.0)
    matrix = np.vstack([normal, extreme])
    features = pd.DataFrame(matrix, columns=ANOMALY_FEATURES)
    features["error_rate_5xx"] = np.r_[rng.normal(0.08, 0.005, 150), [0.8] * 3]
    features.insert(0, "timestamp", timestamps)
    baseline_end = timestamps[150].to_pydatetime()

    detected, _, _, _ = detect_anomalies(features, baseline_end, 0.999)

    assert detected.tail(3)["is_anomaly"].all()


def test_evaluation_calculates_interval_metrics() -> None:
    """STEP 5 정밀도·재현율이 시간 구간 혼동행렬과 일치한다."""
    start = datetime(2025, 3, 5, 14, 0)
    detected = pd.DataFrame(
        {
            "timestamp": [start + timedelta(minutes=5 * i) for i in range(4)],
            "is_anomaly": [True, True, False, True],
        }
    )

    result = evaluate_detection(detected, start, start + timedelta(minutes=15))

    assert result["true_positive_windows"] == 2
    assert result["precision"] == pytest.approx(2 / 3)
    assert result["recall"] == pytest.approx(2 / 3)


@pytest.mark.parametrize(
    ("error_rate", "expected"),
    [(0.30, "CRITICAL"), (0.15, "HIGH"), (0.14, "MEDIUM")],
)
def test_severity_boundaries(error_rate: float, expected: str) -> None:
    """STEP 6 장애 심각도 경계값이 포함 조건으로 처리된다."""
    assert severity_from_error_rate(error_rate) == expected


def test_incident_analysis_deduplicates_consecutive_windows_and_finds_cause() -> None:
    """연속 경보가 하나로 합쳐지고 503 오류의 상위 경로가 식별된다."""
    start = pd.Timestamp("2025-03-05T14:00:00")
    timestamps = [start + pd.Timedelta(minutes=5 * i) for i in range(7)]
    detected = pd.DataFrame(
        {
            "timestamp": timestamps,
            "request_count": [100] * 7,
            "error_5xx_count": [40, 35, 8, 8, 8, 8, 20],
            "error_rate_5xx": [0.4, 0.35, 0.08, 0.08, 0.08, 0.08, 0.2],
            "anomaly_score": [0.9, 0.8, 0.3, 0.3, 0.3, 0.3, 0.7],
            "is_anomaly": [True, True, False, False, False, False, True],
        }
    )
    logs = pd.DataFrame(
        [
            {
                **sample_log((start + pd.Timedelta(minutes=i)).isoformat()),
                "status": 503,
            }
            for i in range(10)
        ]
        + [
            {
                **sample_log((start + pd.Timedelta(minutes=30)).isoformat()),
                "path": "/health",
                "status": 500,
            }
        ]
    )
    logs["timestamp"] = pd.to_datetime(logs["timestamp"])

    incidents = analyze_incidents(logs, detected, 5, baseline_error_rate=0.08)

    assert len(incidents) == 2
    assert incidents[0]["window_count"] == 2
    assert incidents[0]["top_error_path"] == "/api/v1/search"
    assert incidents[0]["top_status"] == 503
    assert incidents[0]["severity"] == "CRITICAL"


def fitted_detector_and_windows() -> tuple[IsolationForest, pd.DataFrame]:
    """저장·리포트 테스트용으로 학습된 탐지기와 시간 구간을 만든다."""
    rng = np.random.default_rng(7)
    values = rng.normal(10, 1, size=(120, len(ANOMALY_FEATURES)))
    features = pd.DataFrame(values, columns=ANOMALY_FEATURES)
    detector = IsolationForest(n_estimators=10, random_state=42).fit(features)
    features.insert(
        0, "timestamp", pd.date_range("2025-03-01", periods=120, freq="5min")
    )
    features["anomaly_score"] = -detector.score_samples(features[ANOMALY_FEATURES])
    features["is_anomaly"] = False
    features.loc[0, "is_anomaly"] = True
    return detector, features


def test_save_outputs_verifies_parquet_and_model_roundtrip(tmp_path: Path) -> None:
    """STEP 7 산출물이 생성되고 Parquet·모델 재로딩 값이 보존된다."""
    detector, detected = fitted_detector_and_windows()
    incidents = [{"severity": "MEDIUM"}]
    invalid = [{"errors": ["bad log"]}]

    paths = save_outputs(
        detected,
        incidents,
        invalid,
        detector,
        threshold=0.6,
        baseline_end=datetime(2025, 3, 1, 8, 0),
        output_dir=tmp_path,
    )

    assert all(path.is_file() for path in paths.values())
    reloaded = pd.read_parquet(paths["windows"])
    pd.testing.assert_frame_equal(detected, reloaded, check_dtype=False)


def test_render_report_embeds_plotly_and_masks_ip(tmp_path: Path) -> None:
    """STEP 8 HTML에 Plotly와 마스킹 IP가 포함되고 원본 IP는 노출되지 않는다."""
    _, detected = fitted_detector_and_windows()
    incidents = [
        {
            "severity": "CRITICAL",
            "start": "2025-03-05 14:00:00",
            "end": "2025-03-05 14:30:00",
            "window_count": 6,
            "max_error_rate": 0.4,
            "top_error_path": "/api/v1/search",
            "top_status": 503,
            "excess_errors": 100.0,
            "top_ip_masked": mask_ip("192.168.0.10"),
        }
    ]
    evaluation = {
        "precision": 0.75,
        "recall": 1.0,
        "f1": 0.857,
        "actual_windows": 6,
        "true_positive_windows": 6,
    }
    config = Config(template_dir=CONFIG.template_dir, output_dir=tmp_path)

    report_path = render_report(
        detected=detected,
        incidents=incidents,
        evaluation=evaluation,
        valid_logs=200_000,
        invalid_logs=3,
        config=config,
        generated_at=datetime(2026, 7, 21, 22, 0, 0),
    )
    html = report_path.read_text(encoding="utf-8")

    assert report_path.name == "incident_report_20260721_220000.html"
    assert "plotly-graph-div" in html
    assert "192.168.0.***" in html
    assert "192.168.0.10" not in html
