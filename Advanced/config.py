"""웹 로그 장애 탐지 실습의 경로와 분석 기준을 정의한다."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Config:
    """실행 위치에 영향을 받지 않는 장애 탐지 설정."""

    data_path: Path = PROJECT_ROOT / "data" / "web_logs.csv"
    template_dir: Path = Path(__file__).resolve().parent / "templates"
    output_dir: Path = Path(__file__).resolve().parent / "output"
    report_title: str = "서비스 장애 조기탐지 및 원인 분석 리포트"
    chunk_size: int = 50_000
    window_minutes: int = 5
    anomaly_quantile: float = 0.999
    incident_start: datetime = datetime(2025, 3, 5, 14, 0)
    incident_end: datetime = datetime(2025, 3, 5, 14, 30)
    incident_path: str = "/api/v1/search"
    traffic_multiplier: int = 5
    inject_demo_incident: bool = True
    inject_demo_invalid: bool = True


CONFIG = Config()
