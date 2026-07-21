"""
프로그램명: 종합실습 3 - 리포트 알림
작성자: 임해안
작성일: 2026-07-21

목적:
    - 생성된 HTML 리포트의 위치를 Slack 웹훅으로 알린다.
    - 알림 기능을 분석·렌더링 로직과 분리하고 환경변수로 선택 활성화한다.

변경 이력:
    - 2026-07-21: 확장 과제 Slack 웹훅 알림 기능 작성.
"""

import json
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


def build_report_link(report_path: Path, report_base_url: str | None = None) -> str:
    """공개 기본 URL이 있으면 웹 링크를, 없으면 로컬 파일 URI를 반환한다."""
    if report_base_url:
        return f"{report_base_url.rstrip('/')}/{quote(report_path.name)}"
    return report_path.resolve().as_uri()


def send_slack_notification(
    report_path: Path,
    *,
    webhook_url: str,
    report_base_url: str | None = None,
    timeout: float = 10.0,
) -> None:
    """Slack Incoming Webhook으로 리포트 생성 완료 메시지를 전송한다."""
    report_link = build_report_link(report_path, report_base_url)
    payload = json.dumps(
        {"text": f"매출 리포트 생성 완료: {report_link}"},
        ensure_ascii=False,
    ).encode("utf-8")
    request = Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )

    with urlopen(request, timeout=timeout) as response:  # noqa: S310
        if not 200 <= response.status < 300:
            raise OSError(f"Slack 알림 전송 실패: HTTP {response.status}")
