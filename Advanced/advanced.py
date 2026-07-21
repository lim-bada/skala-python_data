"""
프로그램명: 창의적 개인 실습 - 서비스 장애 조기탐지 및 원인 분석
작성자: 임해안
작성일: 2026-07-21

프로그램 설명:
    - 대용량 웹 로그를 청크 단위로 읽고 Pydantic으로 입력 품질을 검증한다.
    - 5분 단위 트래픽·5xx 오류 특성을 만들고 IsolationForest로 이상을 탐지한다.
    - 연속 경보를 하나의 장애로 통합하고 경로·상태·IP 기준 원인 후보를 찾는다.
    - 탐지 결과, 모델, 오염 로그와 HTML 장애 분석 리포트를 자동 생성한다.

변경 이력:
    - 2026-07-21: 스트리밍 로그 검증과 재현 가능한 장애 주입 기능 작성.
    - 2026-07-21: 5분 집계, IsolationForest 기준 학습과 이상 탐지 추가.
    - 2026-07-21: 연속 경보 중복 제거 및 장애 원인·영향 분석 추가.
    - 2026-07-21: 탐지 성능 평가, Plotly·Jinja2 리포트와 산출물 저장 추가.
"""

import argparse
import json
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import polars as pl
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from pydantic import ValidationError
from sklearn.ensemble import IsolationForest

try:
    from .config import CONFIG, Config
    from .models import WebLog
except ImportError:  # 파일 경로를 지정해 직접 실행하는 경우
    from config import CONFIG, Config
    from models import WebLog


ANOMALY_FEATURES = [
    "request_count",
    "error_5xx_count",
    "error_rate_5xx",
    "unique_ips",
    "avg_bytes",
    "p95_bytes",
    "path_count",
]


# STEP 0 - 데이터와 템플릿 같은 실행 자원 및 설정 확인
def check_resources(config: Config) -> None:
    """필수 파일과 장애 탐지 설정값이 올바른지 검사한다."""
    missing = [
        path for path in (config.data_path, config.template_dir) if not path.exists()
    ]
    if missing:
        raise FileNotFoundError(
            "필수 실행 자원이 없습니다: " + ", ".join(str(path) for path in missing)
        )
    if config.chunk_size < 1 or config.window_minutes < 1:
        raise ValueError("chunk_size와 window_minutes는 1 이상이어야 합니다.")
    if not 0 < config.anomaly_quantile < 1:
        raise ValueError("anomaly_quantile은 0과 1 사이여야 합니다.")
    if config.incident_start >= config.incident_end:
        raise ValueError("장애 종료 시각은 시작 시각보다 늦어야 합니다.")
    if config.traffic_multiplier < 1:
        raise ValueError("traffic_multiplier는 1 이상이어야 합니다.")


# STEP 1 - 청크 기반 로그 검증 및 오염 데이터 격리
def validate_records(
    records: Iterable[dict[str, Any]], start_index: int = 0
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """로그 레코드를 검증해 유효 데이터와 필드별 오류 정보로 분리한다."""
    valid: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []

    for offset, record in enumerate(records):
        try:
            valid.append(WebLog.model_validate(record).model_dump(mode="json"))
        except ValidationError as error:
            invalid.append(
                {
                    "index": start_index + offset,
                    "data": record,
                    "errors": error.errors(include_url=False),
                }
            )
    return valid, invalid


def demo_invalid_records() -> list[dict[str, Any]]:
    """IP·상태 코드·전송량 검증을 확인할 수 있는 오염 로그 3건을 반환한다."""
    base = {
        "ip": "192.168.0.10",
        "timestamp": "2025-03-05T13:59:59",
        "method": "GET",
        "path": "/health",
        "status": 200,
        "bytes": 1024,
        "user_agent": "demo-client/1.0",
    }
    bad_ip = {**base, "ip": "999.1.1.1"}
    bad_status = {**base, "status": 999}
    bad_bytes = {**base, "bytes": -1}
    return [bad_ip, bad_status, bad_bytes]


def load_and_validate_logs(
    path: Path,
    chunk_size: int,
    *,
    include_demo_invalid: bool,
) -> tuple[pd.DataFrame, list[dict[str, Any]], int]:
    """CSV를 청크로 처리해 전체 파일을 원본 DataFrame으로 한 번에 읽지 않는다."""
    valid: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    input_count = 0

    for chunk in pd.read_csv(path, chunksize=chunk_size):
        records = chunk.to_dict("records")
        chunk_valid, chunk_invalid = validate_records(records, start_index=input_count)
        valid.extend(chunk_valid)
        invalid.extend(chunk_invalid)
        input_count += len(records)

    if include_demo_invalid:
        examples = demo_invalid_records()
        example_valid, example_invalid = validate_records(
            examples, start_index=input_count
        )
        valid.extend(example_valid)
        invalid.extend(example_invalid)
        input_count += len(examples)

    if not valid:
        raise ValueError("검증을 통과한 로그가 없습니다.")

    dataframe = pd.DataFrame(valid)
    dataframe["timestamp"] = pd.to_datetime(dataframe["timestamp"])
    dataframe["status"] = dataframe["status"].astype("int64")
    dataframe["bytes"] = dataframe["bytes"].astype("int64")
    return dataframe, invalid, input_count


# STEP 2 - 정답을 아는 장애 시나리오 생성
def inject_incident(logs: pd.DataFrame, config: Config) -> pd.DataFrame:
    """원본을 변경하지 않고 특정 API에 503 오류와 트래픽 급증을 재현한다."""
    injected = logs.copy()
    start = pd.Timestamp(config.incident_start)
    end = pd.Timestamp(config.incident_end)
    incident_mask = injected["timestamp"].between(
        start, end, inclusive="left"
    ) & injected["path"].eq(config.incident_path)
    if not incident_mask.any():
        raise ValueError("설정한 시간과 경로에 장애를 주입할 로그가 없습니다.")

    injected.loc[incident_mask, "status"] = 503
    affected = injected.loc[incident_mask].copy()
    extra_traffic = [affected.copy() for _ in range(config.traffic_multiplier - 1)]
    if extra_traffic:
        injected = pd.concat([injected, *extra_traffic], ignore_index=True)
    return injected.sort_values("timestamp").reset_index(drop=True)


# STEP 3 - Polars를 이용한 5분 단위 장애 탐지 특성 생성
def aggregate_time_windows(logs: pd.DataFrame, window_minutes: int) -> pd.DataFrame:
    """요청량, 오류율, IP 수와 전송량을 일정 시간 구간별로 집계한다."""
    if logs.empty:
        raise ValueError("집계할 로그가 없습니다.")

    interval = f"{window_minutes}m"
    frame = pl.from_pandas(logs)
    features = (
        frame.sort("timestamp")
        .group_by_dynamic(
            "timestamp",
            every=interval,
            period=interval,
            closed="left",
        )
        .agg(
            pl.len().alias("request_count"),
            (pl.col("status") >= 500).sum().alias("error_5xx_count"),
            pl.col("ip").n_unique().alias("unique_ips"),
            pl.col("bytes").mean().alias("avg_bytes"),
            pl.col("bytes").quantile(0.95).alias("p95_bytes"),
            pl.col("path").n_unique().alias("path_count"),
        )
        .with_columns(
            (pl.col("error_5xx_count") / pl.col("request_count")).alias(
                "error_rate_5xx"
            )
        )
        .sort("timestamp")
    )
    return features.to_pandas()


# STEP 4 - 정상 기준 학습 및 IsolationForest 이상 탐지
def detect_anomalies(
    features: pd.DataFrame,
    baseline_end: datetime,
    anomaly_quantile: float,
) -> tuple[pd.DataFrame, IsolationForest, float, float]:
    """장애 이전 구간만 학습하고 정상 점수 상위 분위수를 경보 기준으로 사용한다."""
    baseline_mask = features["timestamp"] < pd.Timestamp(baseline_end)
    baseline = features.loc[baseline_mask, ANOMALY_FEATURES]
    if len(baseline) < 100:
        raise ValueError("정상 기준을 학습하려면 최소 100개 시간 구간이 필요합니다.")
    if features[ANOMALY_FEATURES].isna().any().any():
        raise ValueError("이상 탐지 특성에 결측치가 있습니다.")

    detector = IsolationForest(
        n_estimators=200,
        contamination="auto",
        random_state=42,
        n_jobs=-1,
    )
    detector.fit(baseline)

    baseline_scores = -detector.score_samples(baseline)
    threshold = float(np.quantile(baseline_scores, anomaly_quantile))
    baseline_error_rate = float(
        features.loc[baseline_mask, "error_5xx_count"].sum()
        / features.loc[baseline_mask, "request_count"].sum()
    )

    detected = features.copy()
    detected["anomaly_score"] = -detector.score_samples(detected[ANOMALY_FEATURES])
    detected["is_anomaly"] = detected["anomaly_score"] >= threshold
    return detected, detector, threshold, baseline_error_rate


# STEP 5 - 정답 구간 기준 탐지 성능 평가
def evaluate_detection(
    detected: pd.DataFrame,
    incident_start: datetime,
    incident_end: datetime,
) -> dict[str, float | int]:
    """주입한 장애 구간을 정답으로 사용해 시간 구간 단위 성능을 계산한다."""
    actual = detected["timestamp"].between(
        pd.Timestamp(incident_start), pd.Timestamp(incident_end), inclusive="left"
    )
    predicted = detected["is_anomaly"].astype(bool)
    true_positive = int((actual & predicted).sum())
    false_positive = int((~actual & predicted).sum())
    false_negative = int((actual & ~predicted).sum())

    precision = (
        true_positive / (true_positive + false_positive) if predicted.any() else 0.0
    )
    recall = true_positive / (true_positive + false_negative) if actual.any() else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "actual_windows": int(actual.sum()),
        "predicted_windows": int(predicted.sum()),
        "true_positive_windows": true_positive,
    }


def severity_from_error_rate(max_error_rate: float) -> str:
    """장애 구간의 최대 5xx 오류율을 운영 심각도로 변환한다."""
    if max_error_rate >= 0.30:
        return "CRITICAL"
    if max_error_rate >= 0.15:
        return "HIGH"
    return "MEDIUM"


def mask_ip(ip: str) -> str:
    """리포트에서 IPv4의 마지막 옥텟을 가려 개인정보 노출을 줄인다."""
    parts = ip.split(".")
    if len(parts) == 4:
        return ".".join([*parts[:3], "***"])
    return "masked"


# STEP 6 - 연속 경보 중복 제거와 원인·영향 분석
def analyze_incidents(
    logs: pd.DataFrame,
    detected: pd.DataFrame,
    window_minutes: int,
    baseline_error_rate: float,
) -> list[dict[str, Any]]:
    """연속된 이상 구간을 한 경보로 합치고 오류 경로·상태·영향을 요약한다."""
    anomalies = detected.loc[detected["is_anomaly"]].sort_values("timestamp").copy()
    if anomalies.empty:
        return []

    interval = pd.Timedelta(minutes=window_minutes)
    anomalies["incident_group"] = (anomalies["timestamp"].diff() > interval).cumsum()
    incidents: list[dict[str, Any]] = []

    for _, windows in anomalies.groupby("incident_group", sort=True):
        start = windows["timestamp"].min()
        end = windows["timestamp"].max() + interval
        related = logs.loc[logs["timestamp"].between(start, end, inclusive="left")]
        errors = related.loc[related["status"] >= 500]

        top_error_path = (
            errors["path"].value_counts().index[0] if not errors.empty else "-"
        )
        top_status = int(errors["status"].mode().iloc[0]) if not errors.empty else "-"
        top_ip = related["ip"].value_counts().index[0] if not related.empty else "-"
        request_count = int(windows["request_count"].sum())
        error_count = int(windows["error_5xx_count"].sum())
        max_error_rate = float(windows["error_rate_5xx"].max())

        incidents.append(
            {
                "start": start.isoformat(sep=" "),
                "end": end.isoformat(sep=" "),
                "window_count": int(len(windows)),
                "severity": severity_from_error_rate(max_error_rate),
                "max_error_rate": max_error_rate,
                "max_anomaly_score": float(windows["anomaly_score"].max()),
                "request_count": request_count,
                "error_count": error_count,
                "excess_errors": max(
                    0.0, error_count - baseline_error_rate * request_count
                ),
                "top_error_path": top_error_path,
                "top_status": top_status,
                "top_ip_masked": mask_ip(str(top_ip)),
            }
        )
    return incidents


# STEP 7 - 탐지 모델과 분석 결과 저장 및 모델 라운드트립 검증
def save_outputs(
    detected: pd.DataFrame,
    incidents: list[dict[str, Any]],
    invalid: list[dict[str, Any]],
    detector: IsolationForest,
    threshold: float,
    baseline_end: datetime,
    output_dir: Path,
) -> dict[str, Path]:
    """시간 구간·경보·오염 로그·모델을 저장하고 재로딩 점수를 검증한다."""
    output_dir.mkdir(parents=True, exist_ok=True)
    windows_path = output_dir / "anomaly_windows.parquet"
    incidents_path = output_dir / "incidents.json"
    invalid_path = output_dir / "invalid_logs.json"
    model_path = output_dir / "isolation_forest.joblib"

    detected.to_parquet(windows_path, index=False)
    incidents_path.write_text(
        json.dumps(incidents, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    invalid_path.write_text(
        json.dumps(invalid, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    bundle = {
        "detector": detector,
        "threshold": threshold,
        "features": ANOMALY_FEATURES,
        "baseline_end": baseline_end,
    }
    joblib.dump(bundle, model_path)

    reloaded_windows = pd.read_parquet(windows_path)
    pd.testing.assert_frame_equal(detected, reloaded_windows, check_dtype=False)
    loaded = joblib.load(model_path)
    sample = detected[ANOMALY_FEATURES].head(20)
    if not np.allclose(
        detector.score_samples(sample), loaded["detector"].score_samples(sample)
    ):
        raise ValueError("저장 전후 IsolationForest의 점수가 일치하지 않습니다.")
    return {
        "windows": windows_path,
        "incidents": incidents_path,
        "invalid": invalid_path,
        "model": model_path,
    }


# STEP 8 - Plotly 시계열과 Jinja2 장애 분석 리포트 생성
def create_timeline_chart(detected: pd.DataFrame) -> str:
    """요청량·5xx 오류율과 탐지된 이상 구간을 한 시계열 차트에 표시한다."""
    anomalies = detected.loc[detected["is_anomaly"]]
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=detected["timestamp"],
            y=detected["request_count"],
            name="요청 수",
            line={"color": "#2563eb"},
        )
    )
    figure.add_trace(
        go.Scatter(
            x=detected["timestamp"],
            y=detected["error_rate_5xx"],
            name="5xx 오류율",
            yaxis="y2",
            line={"color": "#ef6c00"},
        )
    )
    figure.add_trace(
        go.Scatter(
            x=anomalies["timestamp"],
            y=anomalies["request_count"],
            name="이상 탐지",
            mode="markers",
            marker={"color": "#c62828", "size": 10, "symbol": "x"},
        )
    )
    figure.update_layout(
        title="5분 단위 트래픽·5xx 오류율 및 이상 탐지",
        xaxis={"title": "시간"},
        yaxis={"title": "요청 수"},
        yaxis2={
            "title": "5xx 오류율",
            "overlaying": "y",
            "side": "right",
            "tickformat": ".0%",
            "range": [0, max(0.5, float(detected["error_rate_5xx"].max()) * 1.1)],
        },
        legend={"orientation": "h", "y": 1.1},
    )
    return figure.to_html(full_html=False, include_plotlyjs=True)


def render_report(
    *,
    detected: pd.DataFrame,
    incidents: list[dict[str, Any]],
    evaluation: dict[str, float | int],
    valid_logs: int,
    invalid_logs: int,
    config: Config,
    generated_at: datetime | None = None,
) -> Path:
    """탐지 KPI, 시계열, 원인 분석과 성능을 타임스탬프 HTML로 저장한다."""
    report_time = generated_at or datetime.now().astimezone()
    environment = Environment(
        loader=FileSystemLoader(config.template_dir),
        autoescape=select_autoescape(("html", "xml")),
        undefined=StrictUndefined,
    )
    template = environment.get_template("incident_report.html")
    html = template.render(
        title=config.report_title,
        generated_at=report_time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        kpi={
            "valid_logs": valid_logs,
            "invalid_logs": invalid_logs,
            "anomaly_windows": int(detected["is_anomaly"].sum()),
            "incident_count": len(incidents),
        },
        timeline_html=create_timeline_chart(detected),
        incidents=incidents,
        evaluation=evaluation,
    )

    config.output_dir.mkdir(parents=True, exist_ok=True)
    report_path = (
        config.output_dir / f"incident_report_{report_time:%Y%m%d_%H%M%S}.html"
    )
    report_path.write_text(html, encoding="utf-8")
    return report_path


def run(config: Config = CONFIG) -> dict[str, Any]:
    """로그 검증부터 장애 탐지, 평가, 원인 분석과 리포트까지 한 번 실행한다."""
    check_resources(config)
    logs, invalid, input_count = load_and_validate_logs(
        config.data_path,
        config.chunk_size,
        include_demo_invalid=config.inject_demo_invalid,
    )
    original_valid_count = len(logs)
    if config.inject_demo_incident:
        logs = inject_incident(logs, config)

    features = aggregate_time_windows(logs, config.window_minutes)
    detected, detector, threshold, baseline_error_rate = detect_anomalies(
        features,
        config.incident_start,
        config.anomaly_quantile,
    )
    if config.inject_demo_incident:
        evaluation = evaluate_detection(
            detected,
            config.incident_start,
            config.incident_end,
        )
    else:
        evaluation = {
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "actual_windows": 0,
            "predicted_windows": int(detected["is_anomaly"].sum()),
            "true_positive_windows": 0,
        }
    incidents = analyze_incidents(
        logs,
        detected,
        config.window_minutes,
        baseline_error_rate,
    )
    paths = save_outputs(
        detected,
        incidents,
        invalid,
        detector,
        threshold,
        config.incident_start,
        config.output_dir,
    )
    report_path = render_report(
        detected=detected,
        incidents=incidents,
        evaluation=evaluation,
        valid_logs=original_valid_count,
        invalid_logs=len(invalid),
        config=config,
    )

    return {
        "input_count": input_count,
        "valid_count": original_valid_count,
        "invalid_count": len(invalid),
        "analyzed_count": len(logs),
        "window_count": len(detected),
        "threshold": threshold,
        "baseline_error_rate": baseline_error_rate,
        "demo_incident_enabled": config.inject_demo_incident,
        "evaluation": evaluation,
        "incidents": incidents,
        "paths": {**paths, "report": report_path},
    }


def find_demo_incident(
    incidents: list[dict[str, Any]], incident_start: datetime
) -> dict[str, Any] | None:
    """검증 출력용으로 주입 시각을 포함하는 통합 장애를 찾는다."""
    target = pd.Timestamp(incident_start)
    for incident in incidents:
        if pd.Timestamp(incident["start"]) <= target < pd.Timestamp(incident["end"]):
            return incident
    return None


def print_result(result: dict[str, Any], config: Config) -> None:
    """실행 화면 캡처에 적합하도록 단계별 핵심 결과를 출력한다."""
    evaluation = result["evaluation"]
    print("\n=== 창의적 개인 실습: 서비스 장애 조기탐지 ===")
    print("\n-- STEP 1~2: 스트리밍 검증 및 장애 시나리오 --")
    print(
        f"입력 {result['input_count']:,}건 → 유효 {result['valid_count']:,}건 / "
        f"오염 {result['invalid_count']:,}건"
    )
    if result["demo_incident_enabled"]:
        print(
            f"장애 시나리오: {config.incident_start:%Y-%m-%d %H:%M}~"
            f"{config.incident_end:%H:%M}, {config.incident_path}, "
            f"503 오류·트래픽 {config.traffic_multiplier}배"
        )
    else:
        print("장애 시나리오: 주입하지 않음")
    print(f"장애 주입 후 분석 로그: {result['analyzed_count']:,}건")

    print("\n-- STEP 3~5: 5분 집계 및 IsolationForest 탐지 --")
    print(f"시간 구간: {result['window_count']:,}개")
    print(f"정상 기준 5xx 오류율: {result['baseline_error_rate']:.1%}")
    print(f"이상 점수 임계값: {result['threshold']:.4f}")
    if result["demo_incident_enabled"]:
        print(
            f"탐지 성능: 정밀도 {evaluation['precision']:.1%} / "
            f"재현율 {evaluation['recall']:.1%} / F1 {evaluation['f1']:.3f}"
        )
        print(
            f"실제 장애 {evaluation['actual_windows']}개 구간 중 "
            f"{evaluation['true_positive_windows']}개 탐지"
        )
    else:
        print("탐지 성능: 정답 장애를 주입하지 않아 평가하지 않음")

    print("\n-- STEP 6: 중복 경보 제거 및 원인 분석 --")
    print(
        f"이상 구간 {evaluation['predicted_windows']}개 → "
        f"통합 장애 경보 {len(result['incidents'])}건"
    )
    demo_incident = None
    if result["demo_incident_enabled"]:
        demo_incident = find_demo_incident(result["incidents"], config.incident_start)
    if demo_incident:
        print(
            f"주입 장애: {demo_incident['severity']} | "
            f"상위 오류 경로 {demo_incident['top_error_path']} | "
            f"상태 {demo_incident['top_status']} | "
            f"최대 5xx율 {demo_incident['max_error_rate']:.1%} | "
            f"초과 오류 {demo_incident['excess_errors']:.1f}건"
        )

    print("\n-- STEP 7~8: 저장·재로딩 및 HTML 리포트 --")
    for name, path in result["paths"].items():
        print(f"{name:>9}: {path}")
    print("Parquet·IsolationForest 저장 전후 일치: 확인")


def parse_args() -> argparse.Namespace:
    """데모 장애와 오염 로그 주입 여부를 명령행 인자로 받는다."""
    parser = argparse.ArgumentParser(description="웹 로그 서비스 장애 조기탐지 실습")
    parser.add_argument(
        "--no-demo-incident",
        action="store_true",
        help="503 오류·트래픽 급증 장애를 주입하지 않습니다.",
    )
    parser.add_argument(
        "--no-demo-invalid",
        action="store_true",
        help="오염 로그 예시 3건을 추가하지 않습니다.",
    )
    return parser.parse_args()


def main() -> None:
    """명령행 설정을 반영해 전체 장애 탐지 파이프라인을 실행한다."""
    args = parse_args()
    config = Config(
        inject_demo_incident=not args.no_demo_incident,
        inject_demo_invalid=not args.no_demo_invalid,
    )
    try:
        result = run(config)
    except (FileNotFoundError, OSError, ValueError) as error:
        raise SystemExit(f"실행 실패: {error}") from error
    print_result(result, config)


if __name__ == "__main__":
    main()
