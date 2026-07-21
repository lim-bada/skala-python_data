"""
프로그램명: 실습 4 - Pandas 데이터 정제 자동 테스트
작성자: 임해안
작성일: 2026-07-21

목적:
    - 타입 정규화, 결측치 대치와 IQR 이상치 처리 규칙을 자동 검증한다.
    - 각 정제 단계에서 전체 행 수와 필요한 데이터 타입이 보존되는지 확인한다.

변경 이력:
    - 2026-07-21: 실습 4 정제 함수의 pytest 테스트 작성.
"""

import pandas as pd

from pr4 import (
    fill_missing_price,
    fill_missing_region,
    mark_invalid_prices_as_missing,
    normalize_types,
    winsorize_outliers,
)


def test_normalize_types_converts_invalid_values_to_missing() -> None:
    """숫자·날짜 변환 실패값이 결측치가 되고 category 타입이 적용되는지 확인한다."""
    source = pd.DataFrame(
        {
            "unit_price": ["1000", "invalid"],
            "quantity": ["2", "invalid"],
            "order_date": ["2026-07-21", "invalid"],
            "category": ["Food", "Beauty"],
        }
    )

    result = normalize_types(source)

    assert result.loc[0, "unit_price"] == 1000
    assert pd.isna(result.loc[1, "unit_price"])
    assert pd.isna(result.loc[1, "quantity"])
    assert pd.isna(result.loc[1, "order_date"])
    assert isinstance(result["category"].dtype, pd.CategoricalDtype)


def test_fill_missing_price_uses_each_category_median() -> None:
    """가격 결측치가 전체값이 아닌 해당 카테고리의 중앙값으로 채워지는지 확인한다."""
    source = pd.DataFrame(
        {
            "category": pd.Series(
                ["Food", "Food", "Beauty", "Beauty"], dtype="category"
            ),
            "unit_price": [100.0, None, 1000.0, None],
        }
    )

    result = fill_missing_price(source)

    assert result["unit_price"].tolist() == [100.0, 100.0, 1000.0, 1000.0]
    assert len(result) == len(source)
    assert source["unit_price"].isna().sum() == 2


def test_invalid_prices_are_replaced_with_category_median() -> None:
    """0 이하 가격이 결측 처리된 후 카테고리 중앙값으로 대치되는지 확인한다."""
    source = pd.DataFrame(
        {
            "category": pd.Series(["Food", "Food", "Food"], dtype="category"),
            "unit_price": [100.0, -500.0, 300.0],
        }
    )

    validated, invalid_count = mark_invalid_prices_as_missing(source)
    result = fill_missing_price(validated)

    assert invalid_count == 1
    assert result["unit_price"].tolist() == [100.0, 200.0, 300.0]
    assert (result["unit_price"] <= 0).sum() == 0
    assert source.loc[1, "unit_price"] == -500.0


def test_fill_missing_region_uses_mode() -> None:
    """지역 결측치가 전체 지역 중 최빈값으로 채워지는지 확인한다."""
    source = pd.DataFrame({"region": ["Seoul", "Seoul", "Busan", None]})

    result = fill_missing_region(source)

    assert result["region"].tolist() == ["Seoul", "Seoul", "Busan", "Seoul"]
    assert source["region"].isna().sum() == 1


def test_winsorize_outliers_clips_values_and_preserves_rows() -> None:
    """IQR 범위 밖 가격·수량이 경계 안으로 조정되고 행 수가 유지되는지 확인한다."""
    source = pd.DataFrame(
        {
            "unit_price": [10.0, 11.0, 12.0, 13.0, 1000.0],
            "quantity": [1, 2, 3, 4, 100],
        }
    )

    result, report = winsorize_outliers(source)

    assert len(result) == len(source)
    assert report.loc["unit_price", "이상치 수"] == 1
    assert report.loc["quantity", "이상치 수"] == 1
    assert result["unit_price"].max() <= report.loc["unit_price", "IQR 상한"]
    assert result["quantity"].max() <= report.loc["quantity", "IQR 상한"]
    assert pd.api.types.is_integer_dtype(result["quantity"])


def test_cleaning_pipeline_keeps_all_input_rows() -> None:
    """타입 변환부터 이상치 처리까지 어느 단계에서도 입력 행이 사라지지 않는지 확인한다."""
    source = pd.DataFrame(
        {
            "unit_price": ["100", None, "-120", "10000"],
            "quantity": [1, 2, 3, 100],
            "order_date": ["2026-07-21"] * 4,
            "category": ["Food"] * 4,
            "region": ["Seoul", None, "Seoul", "Busan"],
        }
    )

    normalized = normalize_types(source)
    price_validated, _ = mark_invalid_prices_as_missing(normalized)
    price_filled = fill_missing_price(price_validated)
    filled = fill_missing_region(price_filled)
    result, _ = winsorize_outliers(filled)

    assert len(normalized) == len(source)
    assert len(filled) == len(source)
    assert len(result) == len(source)
    assert result["unit_price"].isna().sum() == 0
    assert result["region"].isna().sum() == 0
