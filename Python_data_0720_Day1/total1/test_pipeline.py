"""
프로그램명: 종합실습 1 - ETL 파이프라인 테스트
작성자: 임해안
작성일: 2026-7-20

목적:
    - ETL 각 단계의 입력·출력과 데이터 규칙을 pytest로 자동 검증한다.

변경 이력:
    - 2026-07-20: 테스트 모듈 기본 구조 작성.
    - 2026-07-20: Transform 정규화, 가격 규칙, 건수 보존 테스트 추가.
    - 2026-07-20: 비동기 Extract의 수집 건수와 ID 보존 테스트 추가.
    - 2026-07-20: Load의 DataFrame 변환과 CSV·Parquet 생성 테스트 추가.
    - 2026-07-20: Parquet 저장·복원 라운드트립 테스트 추가.
    - 2026-07-20: Ruff 정적 검사 및 코드 포맷 적용.
"""

import asyncio

import pandas as pd

from models import Product
from pipeline import extract, load, transform


def test_parquet_round_trip(tmp_path):
    """Parquet 저장 후 다시 읽어도 DataFrame의 값과 타입이 같은지 검증한다."""
    dataframe = pd.DataFrame(
        {
            "id": [1, 2],
            "price": [10.5, 20.0],
        }
    )
    parquet_path = tmp_path / "test.parquet"

    dataframe.to_parquet(parquet_path, index=False)
    restored = pd.read_parquet(parquet_path)

    pd.testing.assert_frame_equal(dataframe, restored)


def test_load_writes_csv_and_parquet(tmp_path):
    """Load가 임시 폴더에 CSV·Parquet 파일을 생성하는지 검증한다."""
    products = [
        Product(id=1, name="A", category="food", price=10),
        Product(id=2, name="B", category="tech", price=20),
    ]

    dataframe = load(products, tmp_path)

    assert len(dataframe) == len(products)
    assert (tmp_path / "products.csv").is_file()
    assert (tmp_path / "products.parquet").is_file()


def test_extract_returns_all_requested_ids():
    """비동기 추출 결과가 요청한 모든 ID를 순서대로 포함하는지 검증한다."""
    ids = [1, 2, 3, 4]

    rows = asyncio.run(extract(ids, max_concurrent=2))

    assert len(rows) == len(ids)
    assert [row["id"] for row in rows] == ids


def test_category_is_normalized():
    """카테고리의 공백이 제거되고 소문자로 변환되는지 검증한다."""
    rows = [
        {
            "id": 1,
            "name": "A",
            "category": " FOOD ",
            "price": 10,
        }
    ]

    valid, invalid = transform(rows)

    assert valid[0].category == "food"
    assert len(invalid) == 0


def test_negative_price_is_rejected():
    """0보다 작은 가격이 오염 데이터로 분리되는지 검증한다."""
    rows = [
        {
            "id": 1,
            "name": "A",
            "category": "food",
            "price": -5,
        }
    ]

    valid, invalid = transform(rows)

    assert len(valid) == 0
    assert len(invalid) == 1
    assert invalid[0]["data"] == rows[0]


def test_valid_and_invalid_counts_match_input():
    """모든 입력이 누락 없이 유효 또는 오염 목록에 포함되는지 검증한다."""
    rows = [
        {"id": 1, "name": "A", "category": "food", "price": 10},
        {"id": 2, "name": "B", "category": "TECH", "price": 20},
        {"id": 3, "name": "C", "category": "etc", "price": -5},
    ]

    valid, invalid = transform(rows)

    assert len(valid) + len(invalid) == len(rows)
    assert len(valid) == 2
    assert len(invalid) == 1
