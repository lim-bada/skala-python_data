"""
프로그램명: 종합실습 3 - 분석 자동화 설정
작성자: 임해안
작성일: 2026-07-21

목적:
    - 분석 리포트 생성에 필요한 경로와 실행 설정을 한곳에서 관리한다.
    - frozen dataclass로 실행 중 설정값이 변경되는 것을 방지한다.
    - cron을 포함한 모든 실행 위치에서 동일한 절대 경로를 사용한다.

변경 이력:
    - 2026-07-21: STEP 0 불변 Config와 기본 리포트 설정 작성.
    - 2026-07-21: 확장 과제용 재시도와 Slack 알림 설정 추가.
"""

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODULE_DIR = Path(__file__).resolve().parent


# STEP 0 - 리포트 생성에 사용하는 불변 설정
@dataclass(frozen=True)
class Config:
    """데이터·템플릿·출력 경로와 리포트 옵션을 보관하는 불변 설정."""

    data_path: Path = PROJECT_ROOT / "data" / "sales_raw.csv"
    output_dir: Path = MODULE_DIR / "output"
    template_dir: Path = MODULE_DIR / "templates"
    title: str = "일일 매출 리포트"
    top_n: int = 10
    retry_attempts: int = 3
    retry_base_delay: float = 1.0
    slack_webhook_url: str | None = None
    report_base_url: str | None = None


CONFIG = Config(
    slack_webhook_url=os.getenv("SLACK_WEBHOOK_URL"),
    report_base_url=os.getenv("REPORT_BASE_URL"),
)
