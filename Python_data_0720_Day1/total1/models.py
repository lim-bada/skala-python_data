"""
프로그램명: 종합실습 1 - ETL 데이터 모델
작성자: 임해안
작성일: 2026-7-20

목적:
    - ETL 파이프라인에서 사용하는 상품 데이터의 스키마를 정의한다.
    - Pydantic으로 타입, 가격 범위, 카테고리 정규화 규칙을 검증한다.

변경 이력:
    - 2026-07-20: Product 모델과 카테고리 소문자 정규화 규칙 작성.
    - 2026-07-20: Ruff 정적 검사 및 코드 포맷 적용.
"""

from pydantic import BaseModel, Field, field_validator


class Product(BaseModel):
    """상품 필드의 타입과 가격·카테고리 규칙을 검증하는 모델."""

    id: int
    name: str
    category: str
    price: float = Field(gt=0)

    @field_validator("category")
    @classmethod
    def lower_category(cls, value: str) -> str:
        """카테고리 앞뒤 공백을 제거하고 소문자로 정규화한다."""
        return value.strip().lower()
