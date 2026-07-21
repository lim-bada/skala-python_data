"""종합실습 3의 집계·렌더링·자동 실행 통합 동작을 검증한다."""

from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest
import schedule

import notifications
import report
import run_scheduler
from config import CONFIG, Config
from report import (
    aggregate,
    create_category_chart,
    prepare_sales_data,
    render_report,
    run_with_retry,
)


def test_aggregate_is_pure_and_returns_required_kpis() -> None:
    """STEP 1 집계 함수가 원본을 바꾸지 않고 필수 KPI를 반환하는지 확인한다."""
    raw = pd.DataFrame(
        {
            "category": ["Food", "Beauty"],
            "quantity": [2, 1],
            "unit_price": [1000, 2000],
            "discount": [0.1, 0.0],
        }
    )
    original = raw.copy(deep=True)

    prepared = prepare_sales_data(raw)
    result = aggregate(prepared, top_n=10)

    pd.testing.assert_frame_equal(raw, original)
    assert result["kpi"] == {
        "총매출": 3800.0,
        "주문수": 2,
        "평균주문액": 1900.0,
    }
    assert len(result["by_category"]) == 2


def test_render_report_creates_timestamp_html(tmp_path: Path) -> None:
    """STEP 2~3 템플릿이 타임스탬프 HTML로 저장되는지 확인한다."""
    report_time = datetime(2026, 7, 21, 9, 30, 45)
    data = {
        "kpi": {"총매출": 3800.0, "주문수": 2, "평균주문액": 1900.0},
        "by_category": [{"category": "Food", "amount": 1800.0}],
    }

    output_path = render_report(
        data,
        title="테스트 매출 리포트",
        template_dir=CONFIG.template_dir,
        output_dir=tmp_path / "nested" / "output",
        generated_at=report_time,
    )

    assert output_path.name == "report_20260721_093045.html"
    html = output_path.read_text(encoding="utf-8")
    assert "테스트 매출 리포트" in html
    assert "3,800.00원" in html
    assert "Food" in html


def test_plotly_chart_is_embeddable() -> None:
    """확장 과제 1 차트가 전체 문서가 아닌 HTML 조각으로 생성되는지 확인한다."""
    chart_html = create_category_chart([{"category": "Food", "amount": 1800.0}])

    assert "plotly-graph-div" in chart_html
    assert "Food" in chart_html
    assert not chart_html.lstrip().lower().startswith("<html")


def test_run_once_creates_report_with_shared_pipeline(tmp_path: Path) -> None:
    """STEP 7 공통 run_once가 전체 분석 흐름을 한 번 실행하는지 확인한다."""
    config = Config(
        data_path=CONFIG.data_path,
        output_dir=tmp_path,
        template_dir=CONFIG.template_dir,
        title="통합 테스트 리포트",
        top_n=3,
    )

    output_path = run_scheduler.run_once(config)

    assert output_path.is_file()
    assert output_path.parent == tmp_path
    html = output_path.read_text(encoding="utf-8")
    assert "통합 테스트 리포트" in html
    assert "plotly-graph-div" in html


def test_report_and_scheduler_share_same_run_once() -> None:
    """report 직접 실행과 스케줄러가 같은 run_once 함수 객체를 사용하는지 확인한다."""
    assert run_scheduler.run_once is report.run_once


def test_retry_uses_exponential_backoff() -> None:
    """확장 과제 3 작업이 성공할 때까지 1초, 2초 지수 백오프를 적용한다."""
    attempts: list[int] = []
    delays: list[float] = []

    def flaky_operation() -> Path:
        attempts.append(1)
        if len(attempts) < 3:
            raise FileNotFoundError("데이터 준비 중")
        return Path("report.html")

    result = run_with_retry(
        flaky_operation,
        max_attempts=3,
        base_delay=1.0,
        sleeper=delays.append,
    )

    assert result == Path("report.html")
    assert len(attempts) == 3
    assert delays == [1.0, 2.0]


def test_slack_notification_posts_report_link(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """확장 과제 2 Slack 웹훅에 공개 리포트 링크가 전송되는지 확인한다."""
    captured: dict[str, object] = {}

    class FakeResponse:
        status = 200

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    def fake_urlopen(request: object, timeout: float) -> FakeResponse:
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(notifications, "urlopen", fake_urlopen)
    report_path = tmp_path / "report_20260721_090000.html"

    notifications.send_slack_notification(
        report_path,
        webhook_url="https://hooks.slack.test/example",
        report_base_url="https://reports.example.com/daily",
    )

    request = captured["request"]
    payload = request.data.decode("utf-8")  # type: ignore[attr-defined]
    assert request.full_url == "https://hooks.slack.test/example"  # type: ignore[attr-defined]
    assert "https://reports.example.com/daily/report_20260721_090000.html" in payload
    assert captured["timeout"] == 10.0


def test_interval_loop_uses_shared_job(monkeypatch: pytest.MonkeyPatch) -> None:
    """STEP 4 loop 방식이 전달된 공통 작업을 실행하는지 확인한다."""
    calls: list[str] = []

    def fake_job() -> Path:
        calls.append("run_once")
        return Path("report.html")

    def stop_loop(_: int) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(run_scheduler.time, "sleep", stop_loop)

    with pytest.raises(KeyboardInterrupt):
        run_scheduler.run_interval_loop(60, job=fake_job)

    assert calls == ["run_once"]
    assert "schedule" not in vars(run_scheduler)


def test_schedule_uses_shared_job_and_clears_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """STEP 5 schedule 방식이 공통 작업을 예약하고 종료 시 정리하는지 확인한다."""
    calls: list[str] = []

    def fake_job() -> Path:
        calls.append("run_once")
        return Path("report.html")

    def stop_schedule(_: int) -> None:
        assert len(schedule.get_jobs()) == 1
        raise KeyboardInterrupt

    monkeypatch.setattr(run_scheduler.time, "sleep", stop_schedule)

    with pytest.raises(KeyboardInterrupt):
        run_scheduler.run_schedule(60, job=fake_job)

    assert calls == ["run_once"]
    assert schedule.get_jobs() == []


def test_main_routes_all_modes_to_the_shared_execution_functions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """기본(cron), loop, schedule CLI가 의도한 공통 실행 경로로 연결되는지 확인한다."""
    calls: list[tuple[str, int | None]] = []

    monkeypatch.setattr(
        run_scheduler,
        "run_once",
        lambda: calls.append(("once", None)),
    )
    monkeypatch.setattr(
        run_scheduler,
        "run_interval_loop",
        lambda interval: calls.append(("loop", interval)),
    )
    monkeypatch.setattr(
        run_scheduler,
        "run_schedule",
        lambda interval: calls.append(("schedule", interval)),
    )

    run_scheduler.main([])
    run_scheduler.main(["--mode", "loop", "--interval", "60"])
    run_scheduler.main(["--mode", "schedule", "--interval", "60"])

    assert calls == [("once", None), ("loop", 60), ("schedule", 60)]
