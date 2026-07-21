"""
프로그램명: 창의적 개인 실습 - 웹 로그 검증 모델
작성자: 임해안
작성일: 2026-07-21

목적:
    - 장애 탐지에 사용하기 전에 웹 로그의 타입과 값 범위를 검증한다.
    - 잘못된 IP, 상태 코드, 음수 전송량 같은 오염 레코드를 차단한다.

변경 이력:
    - 2026-07-21: WebLog Pydantic 모델과 로그 검증 규칙 작성.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, IPvAnyAddress


class WebLog(BaseModel):
    """장애 탐지 파이프라인에 전달할 웹 로그 스키마."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    ip: IPvAnyAddress
    timestamp: datetime
    method: Literal["GET", "POST"]
    path: str = Field(pattern=r"^/", min_length=1, max_length=200)
    status: int = Field(ge=100, le=599)
    bytes: int = Field(ge=0)
    user_agent: str = Field(min_length=1, max_length=500)
