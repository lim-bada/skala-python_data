"""
프로그램명: 실습 4 - Pandas 2.x 데이터 정제
작성자: 임해안
작성일: 2026-07-21

목적:
    - 판매 원천 데이터의 구조, 타입, 결측치와 이상치 후보를 진단한다.
    - Pandas로 타입 정규화, 결측치 처리, 이상치 처리와 집계를 단계적으로 수행한다.
    - Copy-on-Write 환경에서 안전한 DataFrame 처리 방식을 익힌다.

변경 이력:
    - 2026-07-21: STEP 0 데이터 로딩 및 기초 진단 기능 작성.
    - 2026-07-21: STEP 1 숫자·날짜·범주형 타입 정규화 기능 추가.
    - 2026-07-21: STEP 2 가격 양수 규칙·중앙값 및 지역 최빈값 처리 추가.
    - 2026-07-21: STEP 3 IQR 기준 가격·수량 이상치 윈저라이징 추가.
    - 2026-07-21: STEP 4 카테고리별 매출 요약 집계 추가.
    - 2026-07-21: STEP 5 카테고리·지역별 매출 피벗 테이블 추가.
    - 2026-07-21: STEP 6 카테고리 기준정보 left merge 및 행 수 검증 추가.
    - 2026-07-21: STEP 7 Copy-on-Write와 .loc 안전 수정 검증 추가.
    - 2026-07-21: 확장 과제 정제 규칙 함수화 및 pytest 자동 테스트 6개 추가.
"""

from pathlib import Path
from math import ceil, floor

import pandas as pd


# 현재 실행 위치와 무관하게 프로젝트의 원본 데이터를 찾는다.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = PROJECT_ROOT / "data" / "sales_raw.csv"


def load_sales_data(path: Path) -> pd.DataFrame:
    """CSV 파일을 읽어 판매 원천 데이터를 DataFrame으로 반환한다."""
    return pd.read_csv(path)


# STEP 0 - 원본 데이터 진단
def diagnose_data(df: pd.DataFrame) -> None:
    """데이터 크기, 타입, 기술통계, 결측치와 실제 샘플을 출력한다."""
    print("\n-- STEP 0: 원본 데이터 진단 --")
    print(f"데이터 파일: {DATA_PATH}")
    print(f"행·열 개수: {df.shape}")

    print("\n[컬럼 타입·결측·메모리 정보]")
    df.info()

    print("\n[수치형 기술통계]")
    print(df.describe())

    print("\n[컬럼별 결측치 수]")
    print(df.isna().sum())

    print("\n[앞 5건]")
    print(df.head())


# STEP 1 - 숫자·날짜·범주형 타입 정규화
def normalize_types(df: pd.DataFrame) -> pd.DataFrame:
    """숫자·날짜·범주 컬럼을 분석에 적합한 타입으로 변환한다."""
    normalized = df.copy()

    # 변환할 수 없는 숫자와 날짜는 이후 결측 처리 대상으로 남긴다.
    normalized["unit_price"] = pd.to_numeric(normalized["unit_price"], errors="coerce")
    normalized["quantity"] = pd.to_numeric(normalized["quantity"], errors="coerce")
    normalized["order_date"] = pd.to_datetime(normalized["order_date"], errors="coerce")
    normalized["category"] = normalized["category"].astype("category")

    return normalized


# STEP 1 - 타입 정규화 결과 확인
def print_type_changes(before: pd.DataFrame, after: pd.DataFrame) -> None:
    """타입 정규화 전후의 자료형과 변환 과정에서 생긴 결측치를 출력한다."""
    print("\n-- STEP 1: 타입 정규화 --")
    type_changes = pd.DataFrame(
        {
            "변환 전": before.dtypes.astype(str),
            "변환 후": after.dtypes.astype(str),
        }
    )
    print(type_changes)

    added_missing = after.isna().sum() - before.isna().sum()
    print("\n[타입 변환으로 추가된 결측치 수]")
    print(added_missing)


# STEP 2 - 가격 업무 규칙 검증
def mark_invalid_prices_as_missing(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """0 이하 가격을 유효하지 않은 값으로 판단해 결측치로 표시한다."""
    validated = df.copy()
    invalid_mask = validated["unit_price"] <= 0
    invalid_count = int(invalid_mask.sum())
    validated.loc[invalid_mask, "unit_price"] = pd.NA
    return validated, invalid_count


# STEP 2 - 카테고리별 중앙값으로 가격 결측치 대치
def fill_missing_price(df: pd.DataFrame) -> pd.DataFrame:
    """unit_price 결측치를 같은 카테고리의 중앙값으로 채운다."""
    filled = df.copy()
    filled["unit_price"] = filled.groupby("category", observed=True)[
        "unit_price"
    ].transform(lambda series: series.fillna(series.median()))

    if filled["unit_price"].isna().any():
        raise ValueError("중앙값 대치 후에도 unit_price 결측치가 남아 있습니다.")

    return filled


# STEP 2 - 최빈값으로 지역 결측치 대치
def fill_missing_region(df: pd.DataFrame) -> pd.DataFrame:
    """region 결측치를 원본 데이터에서 가장 자주 나온 지역으로 채운다."""
    filled = df.copy()
    region_modes = filled["region"].mode(dropna=True)
    if region_modes.empty:
        raise ValueError("region 최빈값을 계산할 수 없습니다.")

    filled["region"] = filled["region"].fillna(region_modes.iloc[0])
    return filled


# STEP 2 - 결측치 처리 결과 확인
def print_missing_changes(
    before: pd.DataFrame, after: pd.DataFrame, invalid_price_count: int
) -> None:
    """결측 처리 전후의 컬럼별 결측치 수와 보존된 행 수를 출력한다."""
    print("\n-- STEP 2: 가격 중앙값·지역 최빈값 결측치 처리 --")
    missing_changes = pd.DataFrame(
        {
            "처리 전": before.isna().sum(),
            "처리 후": after.isna().sum(),
        }
    )
    missing_changes["처리 건수"] = (
        missing_changes["처리 전"] - missing_changes["처리 후"]
    )
    print(missing_changes)
    print(f"가격 업무규칙 위반(0 이하): {invalid_price_count:,}건 → 0건")
    filled_regions = after.loc[before["region"].isna(), "region"].unique()
    if len(filled_regions) == 1:
        print(f"지역 결측 대치값(최빈값): {filled_regions[0]}")
    print(f"행 수 확인: {len(before):,} → {len(after):,}")


# STEP 3 - IQR 기준 이상치 윈저라이징
def calculate_iqr_bounds(series: pd.Series, k: float = 1.5) -> tuple[float, float]:
    """수치형 Series의 IQR 하한과 상한을 계산한다."""
    q1 = series.quantile(0.25)
    q3 = series.quantile(0.75)
    iqr = q3 - q1
    return q1 - k * iqr, q3 + k * iqr


def winsorize_outliers(
    df: pd.DataFrame, columns: tuple[str, ...] = ("unit_price", "quantity")
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """지정한 컬럼의 IQR 이상치를 삭제하지 않고 경계값으로 조정한다."""
    winsorized = df.copy()
    records = []

    for column in columns:
        series = winsorized[column]
        lower, upper = calculate_iqr_bounds(series)

        # 정수형 수량은 IQR 범위 안의 정수 경계를 사용해 타입을 유지한다.
        applied_lower = ceil(lower) if pd.api.types.is_integer_dtype(series) else lower
        applied_upper = floor(upper) if pd.api.types.is_integer_dtype(series) else upper
        outlier_mask = ~series.between(lower, upper)

        records.append(
            {
                "컬럼": column,
                "IQR 하한": lower,
                "IQR 상한": upper,
                "이상치 수": int(outlier_mask.sum()),
                "처리 전 최솟값": series.min(),
                "처리 전 최댓값": series.max(),
            }
        )
        winsorized[column] = series.clip(lower=applied_lower, upper=applied_upper)

    result = pd.DataFrame(records).set_index("컬럼")
    result["처리 후 최솟값"] = winsorized[list(columns)].min()
    result["처리 후 최댓값"] = winsorized[list(columns)].max()
    return winsorized, result


# STEP 3 - 이상치 처리 결과 확인
def print_outlier_changes(
    before: pd.DataFrame, after: pd.DataFrame, result: pd.DataFrame
) -> None:
    """IQR 경계와 윈저라이징 전후 범위 및 행 수를 출력한다."""
    print("\n-- STEP 3: IQR 이상치 윈저라이징 --")
    print(result.round(2).to_string())
    print(f"행 수 확인: {len(before):,} → {len(after):,}")


# STEP 4 - 할인 후 매출액 계산 및 카테고리별 groupby.agg 요약
def summarize_by_category(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """할인 후 매출액을 계산하고 카테고리별 주요 지표를 집계한다."""
    sales = df.copy()
    sales["amount"] = (
        sales["quantity"] * sales["unit_price"] * (1 - sales["discount"])
    ).round(2)

    summary = (
        sales.groupby("category", observed=True)
        .agg(
            건수=("unit_price", "count"),
            평균가=("unit_price", "mean"),
            중앙값=("unit_price", "median"),
            총매출=("amount", "sum"),
        )
        .round(1)
    )
    return sales, summary


# STEP 4 - 카테고리별 집계 결과 확인
def print_category_summary(summary: pd.DataFrame) -> None:
    """카테고리별 건수·평균가·중앙값·총매출을 출력한다."""
    print("\n-- STEP 4: 카테고리별 매출 요약 --")
    print(summary.to_string())


# STEP 5 - 카테고리·지역별 매출 pivot_table 생성
def create_sales_pivot(df: pd.DataFrame) -> pd.DataFrame:
    """카테고리를 행, 지역을 열로 구성한 총매출 교차표를 반환한다."""
    return df.pivot_table(
        index="category",
        columns="region",
        values="amount",
        aggfunc="sum",
        fill_value=0,
        observed=True,
    ).round(1)


# STEP 5 - 피벗 테이블 결과 확인
def print_sales_pivot(df: pd.DataFrame, pivot: pd.DataFrame) -> None:
    """카테고리·지역별 총매출 교차표와 지역 결측 행 수를 출력한다."""
    print("\n-- STEP 5: 카테고리·지역별 매출 교차표 --")
    print(pivot.to_string())
    print(f"지역 결측으로 교차표에서 제외된 행: {df['region'].isna().sum():,}건")


# STEP 6 - 카테고리 기준정보 left merge
def merge_category_info(df: pd.DataFrame) -> pd.DataFrame:
    """판매 데이터에 카테고리 한국어 명칭을 다대일 방식으로 결합한다."""
    category_info = pd.DataFrame(
        {
            "category": ["Beauty", "Electronics", "Fashion", "Food", "Home"],
            "category_ko": ["뷰티", "전자제품", "패션", "식품", "생활용품"],
        }
    )

    merged = df.merge(
        category_info,
        on="category",
        how="left",
        validate="many_to_one",
        indicator=True,
    )

    if len(merged) != len(df):
        raise ValueError("merge 전후 행 수가 일치하지 않습니다.")

    return merged


# STEP 6 - merge 결과 확인
def print_merge_result(before: pd.DataFrame, after: pd.DataFrame) -> None:
    """결합 전후 행 수, 결합 상태와 추가된 카테고리 정보를 출력한다."""
    print("\n-- STEP 6: 카테고리 기준정보 결합 --")
    print(f"행 수 확인: {len(before):,} → {len(after):,}")
    print("\n[결합 상태]")
    print(after["_merge"].value_counts().to_string())
    print("\n[결합 결과 앞 5건]")
    print(after[["order_id", "category", "category_ko"]].head().to_string(index=False))


# STEP 7 - Copy-on-Write 설정과 .loc을 이용한 안전한 수정
def apply_safe_update(df: pd.DataFrame) -> tuple[pd.DataFrame, bool, int]:
    """고가 상품 플래그를 추가하고 슬라이스 수정이 원본과 격리되는지 확인한다."""
    pandas_major_version = int(pd.__version__.split(".")[0])
    if pandas_major_version < 3:
        pd.options.mode.copy_on_write = True

    updated = df.copy()
    high_price_threshold = 100_000
    updated["high_price_flag"] = 0
    updated.loc[updated["unit_price"] > high_price_threshold, "high_price_flag"] = 1

    # CoW에서는 슬라이스를 수정해도 원본 DataFrame의 같은 값은 바뀌지 않는다.
    seoul_slice = updated.loc[updated["region"] == "Seoul"]
    original_prices = updated.loc[seoul_slice.index, "unit_price"].copy()
    seoul_slice.loc[:, "unit_price"] *= 1.1
    original_unchanged = updated.loc[seoul_slice.index, "unit_price"].equals(
        original_prices
    )

    return updated, original_unchanged, high_price_threshold


# STEP 7 - Copy-on-Write 동작 확인
def print_copy_on_write_result(
    df: pd.DataFrame, original_unchanged: bool, threshold: int
) -> None:
    """Pandas 버전, 조건부 수정 건수와 CoW 원본 보호 여부를 출력한다."""
    print("\n-- STEP 7: Copy-on-Write와 .loc 안전 수정 --")
    print(f"Pandas 버전: {pd.__version__}")
    print(f"Copy-on-Write: {'원본 보호 확인' if original_unchanged else '확인 실패'}")
    print(f"unit_price > {threshold:,} 고가 플래그: {df['high_price_flag'].sum():,}건")


def main() -> None:
    """판매 데이터를 불러와 진단하고 단계별로 정제한다."""
    try:
        df = load_sales_data(DATA_PATH)
    except FileNotFoundError:
        print(f"오류: 데이터 파일을 찾을 수 없습니다: {DATA_PATH}")
        print("프로젝트 최상위 폴더에서 python data/generate_data.py를 실행하세요.")
        return
    except pd.errors.EmptyDataError:
        print(f"오류: 데이터 파일이 비어 있습니다: {DATA_PATH}")
        return
    except pd.errors.ParserError as error:
        print(f"오류: CSV 형식을 해석할 수 없습니다: {error}")
        return

    # STEP 0 실행
    diagnose_data(df)

    # STEP 1 실행
    normalized_df = normalize_types(df)
    print_type_changes(df, normalized_df)

    # STEP 2 실행
    price_validated_df, invalid_price_count = mark_invalid_prices_as_missing(
        normalized_df
    )
    price_filled_df = fill_missing_price(price_validated_df)
    filled_df = fill_missing_region(price_filled_df)
    print_missing_changes(normalized_df, filled_df, invalid_price_count)

    # STEP 3 실행
    winsorized_df, outlier_result = winsorize_outliers(filled_df)
    print_outlier_changes(filled_df, winsorized_df, outlier_result)

    # STEP 4 실행
    sales_df, category_summary = summarize_by_category(winsorized_df)
    print_category_summary(category_summary)

    # STEP 5 실행
    sales_pivot = create_sales_pivot(sales_df)
    print_sales_pivot(sales_df, sales_pivot)

    # STEP 6 실행
    merged_df = merge_category_info(sales_df)
    print_merge_result(sales_df, merged_df)

    # STEP 7 실행
    final_df, cow_verified, price_threshold = apply_safe_update(merged_df)
    print_copy_on_write_result(final_df, cow_verified, price_threshold)


if __name__ == "__main__":
    main()
