"""
프로그램명: 종합실습 3 - 매출 리포트 생성
작성자: 임해안
작성일: 2026-07-21

목적:
    - 판매 원천 데이터를 정제하고 리포트용 KPI와 카테고리별 매출을 집계한다.
    - 집계 로직과 파일 I/O를 분리해 테스트 가능한 순수 함수를 구성한다.
    - 이후 Jinja2 템플릿으로 타임스탬프 HTML 리포트를 생성한다.

변경 이력:
    - 2026-07-21: STEP 1 판매 데이터 정제 및 순수 집계 함수 작성.
    - 2026-07-21: STEP 3 Jinja2 기반 타임스탬프 HTML 저장 기능 추가.
    - 2026-07-21: 성공 판정 기준에 맞춰 직접 실행 진입점과 공통 run_once 추가.
    - 2026-07-21: 확장 과제 Plotly 차트·Slack 알림·지수 백오프 재시도 추가.
"""

import time
from collections.abc import Callable, Mapping
from datetime import datetime
from math import ceil, floor
from pathlib import Path

import pandas as pd
import plotly.express as px
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

try:
    from .config import CONFIG, Config
    from .notifications import send_slack_notification
except ImportError:  # 파일 경로를 지정해 직접 실행하는 경우
    from config import CONFIG, Config
    from notifications import send_slack_notification


RAW_REQUIRED_COLUMNS = {
    "category",
    "quantity",
    "unit_price",
    "discount",
}


# STEP 1 - 원천 판매 데이터 정제 및 amount 생성
def prepare_sales_data(df: pd.DataFrame) -> pd.DataFrame:
    """원본을 변경하지 않고 가격·수량을 정제해 할인 후 매출액을 계산한다."""
    missing_columns = RAW_REQUIRED_COLUMNS - set(df.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"필수 컬럼이 없습니다: {missing}")
    if df.empty:
        raise ValueError("판매 데이터가 비어 있습니다.")

    prepared = df.copy()
    prepared["unit_price"] = pd.to_numeric(prepared["unit_price"], errors="coerce")
    prepared["quantity"] = pd.to_numeric(prepared["quantity"], errors="coerce")
    prepared["discount"] = pd.to_numeric(prepared["discount"], errors="coerce")

    # 가격은 0보다 커야 하며, 결측·비정상 가격은 카테고리별 중앙값으로 채운다.
    prepared.loc[prepared["unit_price"] <= 0, "unit_price"] = pd.NA
    prepared["unit_price"] = prepared.groupby("category", observed=True)[
        "unit_price"
    ].transform(lambda series: series.fillna(series.median()))

    # 수량 이상치는 행을 삭제하지 않고 IQR 정수 경계로 윈저라이징한다.
    q1 = prepared["quantity"].quantile(0.25)
    q3 = prepared["quantity"].quantile(0.75)
    iqr = q3 - q1
    lower = ceil(q1 - 1.5 * iqr)
    upper = floor(q3 + 1.5 * iqr)
    prepared["quantity"] = prepared["quantity"].clip(lower=lower, upper=upper)

    required_values = ["category", "quantity", "unit_price", "discount"]
    if prepared[required_values].isna().any().any():
        raise ValueError("정제 후 매출 계산에 필요한 결측치가 남아 있습니다.")

    prepared["amount"] = (
        prepared["quantity"] * prepared["unit_price"] * (1 - prepared["discount"])
    ).round(2)
    return prepared


# STEP 1 - 리포트용 KPI 및 카테고리별 매출 순수 집계
def aggregate(df: pd.DataFrame, top_n: int = 10) -> dict[str, object]:
    """정제된 DataFrame을 받아 파일을 쓰지 않고 리포트 데이터를 반환한다."""
    required_columns = {"category", "amount"}
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"집계에 필요한 컬럼이 없습니다: {missing}")
    if df.empty:
        raise ValueError("집계할 판매 데이터가 비어 있습니다.")
    if top_n < 1:
        raise ValueError("top_n은 1 이상이어야 합니다.")

    by_category = (
        df.groupby("category", observed=True, as_index=False)["amount"]
        .sum()
        .sort_values("amount", ascending=False)
        .head(top_n)
    )
    by_category["amount"] = by_category["amount"].round(2)

    return {
        "kpi": {
            "총매출": round(float(df["amount"].sum()), 2),
            "주문수": int(len(df)),
            "평균주문액": round(float(df["amount"].mean()), 1),
        },
        "by_category": by_category.to_dict("records"),
    }


# 확장 과제 1 - 카테고리별 매출 Plotly 차트 생성
def create_category_chart(by_category: list[dict[str, object]]) -> str:
    """카테고리별 매출을 인터랙티브 막대 차트 HTML 조각으로 반환한다."""
    if not by_category:
        return ""

    chart_data = pd.DataFrame(by_category)
    figure = px.bar(
        chart_data,
        x="category",
        y="amount",
        color="category",
        labels={"category": "카테고리", "amount": "매출액"},
        title="카테고리별 매출",
    )
    figure.update_layout(showlegend=False, yaxis_tickformat=",")
    return figure.to_html(full_html=False, include_plotlyjs=True)


# STEP 3 - 집계 결과를 Jinja2 템플릿으로 렌더링해 HTML 파일 저장
def render_report(
    report_data: Mapping[str, object],
    *,
    title: str,
    template_dir: Path,
    output_dir: Path,
    generated_at: datetime | None = None,
) -> Path:
    """집계 결과를 타임스탬프가 포함된 HTML 파일로 저장하고 경로를 반환한다."""
    required_keys = {"kpi", "by_category"}
    missing_keys = required_keys - set(report_data)
    if missing_keys:
        missing = ", ".join(sorted(missing_keys))
        raise ValueError(f"리포트 데이터에 필요한 항목이 없습니다: {missing}")

    if not template_dir.is_dir():
        raise FileNotFoundError(f"템플릿 폴더가 없습니다: {template_dir}")

    # 전달되지 않으면 시스템의 현지 시간대를 포함한 현재 시각을 사용한다.
    report_time = generated_at or datetime.now().astimezone()
    output_dir.mkdir(parents=True, exist_ok=True)

    environment = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(("html", "xml")),
        undefined=StrictUndefined,
    )
    template = environment.get_template("report.html")
    html = template.render(
        title=title,
        generated_at=report_time.strftime("%Y-%m-%d %H:%M:%S %Z"),
        **report_data,
    )

    output_path = output_dir / f"report_{report_time:%Y%m%d_%H%M%S}.html"
    output_path.write_text(html, encoding="utf-8")
    return output_path


# 확장 과제 3 - 실패 작업 지수 백오프 재시도
def run_with_retry(
    operation: Callable[[], Path],
    *,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    sleeper: Callable[[float], None] = time.sleep,
) -> Path:
    """실패한 작업을 base_delay, 2배, 4배 간격으로 정해진 횟수만큼 재시도한다."""
    if max_attempts < 1:
        raise ValueError("최대 시도 횟수는 1 이상이어야 합니다.")
    if base_delay < 0:
        raise ValueError("재시도 대기 시간은 0 이상이어야 합니다.")

    for attempt in range(1, max_attempts + 1):
        try:
            return operation()
        except Exception:
            if attempt == max_attempts:
                raise
            delay = base_delay * (2 ** (attempt - 1))
            print(
                f"리포트 생성 실패 ({attempt}/{max_attempts}), "
                f"{delay:g}초 후 재시도합니다.",
                flush=True,
            )
            sleeper(delay)

    raise RuntimeError("도달할 수 없는 재시도 상태입니다.")


def generate_report(config: Config) -> Path:
    """판매 데이터를 읽고 정제·집계해 Plotly 차트가 포함된 HTML을 생성한다."""
    raw_data = pd.read_csv(config.data_path)
    prepared_data = prepare_sales_data(raw_data)
    report_data = aggregate(prepared_data, top_n=config.top_n)
    by_category = report_data["by_category"]
    if not isinstance(by_category, list):
        raise TypeError("카테고리별 집계 결과는 list여야 합니다.")
    report_data["chart_html"] = create_category_chart(by_category)
    return render_report(
        report_data,
        title=config.title,
        template_dir=config.template_dir,
        output_dir=config.output_dir,
    )


# STEP 7 - 직접 실행·loop·schedule·cron이 함께 사용하는 단일 작업
def run_once(config: Config = CONFIG) -> Path:
    """재시도를 적용해 리포트를 생성하고 설정된 경우 Slack으로 알린다."""
    output_path = run_with_retry(
        lambda: generate_report(config),
        max_attempts=config.retry_attempts,
        base_delay=config.retry_base_delay,
    )

    # 확장 과제 2 - 웹훅이 설정된 경우에만 Slack 알림을 전송한다.
    if config.slack_webhook_url:
        try:
            send_slack_notification(
                output_path,
                webhook_url=config.slack_webhook_url,
                report_base_url=config.report_base_url,
            )
        except OSError as error:
            print(f"Slack 알림 실패: {error}", flush=True)

    print(f"리포트 생성 완료: {output_path}", flush=True)
    return output_path


def main() -> None:
    """report.py를 직접 실행하면 리포트를 한 번 생성한다."""
    run_once()


if __name__ == "__main__":
    main()
