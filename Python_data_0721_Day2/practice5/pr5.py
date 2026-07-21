"""
프로그램명: 실습 5 - Pandas·Polars·DuckDB 성능 비교
작성자: 임해안
작성일: 2026-07-21

목적:
    - 동일한 집계를 Pandas, Polars Lazy API와 DuckDB SQL로 구현한다.
    - 세 엔진의 집계 결과가 같은지 검증한 뒤 실행 시간을 비교한다.
    - 데이터 규모와 분석 방식에 따른 엔진 선택 기준을 이해한다.

변경 이력:
    - 2026-07-21: STEP 0 입력 데이터 구조 확인 및 공통 비교 질의 정의.
    - 2026-07-21: STEP 1 Pandas 기준 집계 및 실행 시간 측정 추가.
    - 2026-07-21: STEP 2 Polars Lazy API 집계 및 실행 시간 측정 추가.
    - 2026-07-21: STEP 3 DuckDB SQL 집계 및 실행 시간 측정 추가.
    - 2026-07-21: STEP 4 세 엔진 집계 결과 일치 검증 추가.
    - 2026-07-21: STEP 5 세 엔진 반복 벤치마크 및 비교표 추가.
"""

import csv
import time
import timeit
from itertools import islice
from pathlib import Path
from statistics import median

import duckdb
import pandas as pd
import polars as pl


# 현재 실행 위치와 무관하게 프로젝트의 원본 데이터를 찾는다.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = PROJECT_ROOT / "data" / "events_large.csv"

REQUIRED_COLUMNS = {"event_id", "user_id", "event_type", "ts", "amount"}
QUERY_DESCRIPTION = (
    "amount가 0보다 큰 행만 선택하고, event_type별로 묶어 "
    "건수(cnt)와 평균 금액(avg)을 계산한 뒤 건수 내림차순으로 정렬한다."
)


# STEP 0 - 데이터 구조 확인
def inspect_source_data(
    path: Path, sample_size: int = 5
) -> tuple[list[str], list[dict[str, str]], int]:
    """CSV를 한 줄씩 읽어 컬럼, 앞부분 샘플과 전체 데이터 행 수를 반환한다."""
    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        columns = reader.fieldnames or []
        missing_columns = REQUIRED_COLUMNS - set(columns)
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise ValueError(f"필수 컬럼이 없습니다: {missing}")

        samples = list(islice(reader, sample_size))
        row_count = len(samples) + sum(1 for _ in reader)

    return columns, samples, row_count


# STEP 0 - 공통 비교 질의 및 데이터 확인 결과 출력
def print_step0_result(
    columns: list[str], samples: list[dict[str, str]], row_count: int
) -> None:
    """세 엔진이 공통으로 실행할 질의와 원본 데이터 구조를 출력한다."""
    print("\n-- STEP 0: 공통 비교 질의 정의 --")
    print(f"데이터 파일: {DATA_PATH}")
    print(f"전체 데이터 행 수: {row_count:,}")
    print(f"컬럼: {columns}")
    print(f"공통 질의: {QUERY_DESCRIPTION}")

    print("\n[앞 5건]")
    for index, row in enumerate(samples, start=1):
        print(f"{index}: {row}")


# STEP 1 - Pandas 기준선 집계
def run_pandas_query(path: Path) -> tuple[pd.DataFrame, float]:
    """CSV 로딩부터 집계 완료까지 수행하고 결과와 실행 시간(ms)을 반환한다."""
    start = time.perf_counter()
    df = pd.read_csv(path)
    result = (
        df.loc[df["amount"] > 0]
        .groupby("event_type")
        .agg(cnt=("amount", "count"), avg=("amount", "mean"))
        .sort_values("cnt", ascending=False)
        .reset_index()
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    return result, elapsed_ms


# STEP 1 - Pandas 실행 결과 출력
def print_pandas_result(result: pd.DataFrame, elapsed_ms: float) -> None:
    """Pandas 집계 결과와 파일 로딩을 포함한 실행 시간을 출력한다."""
    print("\n-- STEP 1: Pandas 기준선 --")
    print(result.to_string(index=False))
    print(f"Pandas 실행 시간: {elapsed_ms:,.2f} ms")


# STEP 2 - Polars Lazy API 집계
def run_polars_query(path: Path) -> tuple[pl.DataFrame, float]:
    """Lazy 쿼리를 구성해 collect하고 결과와 전체 실행 시간(ms)을 반환한다."""
    start = time.perf_counter()
    result = (
        pl.scan_csv(path)
        .filter(pl.col("amount") > 0)
        .group_by("event_type")
        .agg(
            pl.len().alias("cnt"),
            pl.col("amount").mean().alias("avg"),
        )
        .sort("cnt", descending=True)
        .collect()
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    return result, elapsed_ms


# STEP 2 - Polars 실행 결과 출력
def print_polars_result(result: pl.DataFrame, elapsed_ms: float) -> None:
    """Polars 집계 결과와 collect까지 포함한 실행 시간을 출력한다."""
    print("\n-- STEP 2: Polars Lazy API --")
    print(result)
    print(f"Polars 실행 시간: {elapsed_ms:,.2f} ms")


# STEP 3 - DuckDB SQL 집계
def run_duckdb_query(path: Path) -> tuple[pd.DataFrame, float]:
    """CSV를 직접 조회하는 SQL을 실행하고 결과와 전체 실행 시간(ms)을 반환한다."""
    query = """
        SELECT
            event_type,
            COUNT(*) AS cnt,
            AVG(amount) AS avg
        FROM read_csv_auto(?)
        WHERE amount > 0
        GROUP BY event_type
        ORDER BY cnt DESC
    """

    start = time.perf_counter()
    with duckdb.connect() as connection:
        result = connection.execute(query, [str(path)]).df()
    elapsed_ms = (time.perf_counter() - start) * 1000
    return result, elapsed_ms


# STEP 3 - DuckDB 실행 결과 출력
def print_duckdb_result(result: pd.DataFrame, elapsed_ms: float) -> None:
    """DuckDB SQL 집계 결과와 DataFrame 변환까지 포함한 시간을 출력한다."""
    print("\n-- STEP 3: DuckDB SQL --")
    print(result.to_string(index=False))
    print(f"DuckDB 실행 시간: {elapsed_ms:,.2f} ms")


# STEP 4 - 세 엔진 결과 일치 검증
def normalize_result(df: pd.DataFrame) -> pd.DataFrame:
    """엔진별 결과를 event_type 기준으로 정렬해 비교 가능한 형태로 만든다."""
    return (
        df[["event_type", "cnt", "avg"]]
        .sort_values("event_type")
        .reset_index(drop=True)
    )


def verify_engine_results(
    pandas_result: pd.DataFrame,
    polars_result: pl.DataFrame,
    duckdb_result: pd.DataFrame,
) -> None:
    """정렬·타입·부동소수점 차이를 고려해 세 엔진의 결과가 같은지 검증한다."""
    expected = normalize_result(pandas_result)
    polars_normalized = normalize_result(polars_result.to_pandas())
    duckdb_normalized = normalize_result(duckdb_result)

    pd.testing.assert_frame_equal(
        expected,
        polars_normalized,
        check_dtype=False,
        check_exact=False,
        atol=1e-6,
    )
    pd.testing.assert_frame_equal(
        expected,
        duckdb_normalized,
        check_dtype=False,
        check_exact=False,
        atol=1e-6,
    )


# STEP 4 - 검증 성공 결과 출력
def print_verification_result() -> None:
    """세 엔진의 결과 일치 검증이 모두 통과했음을 출력한다."""
    print("\n-- STEP 4: 세 엔진 결과 일치 검증 --")
    print("세 엔진 결과 일치: assert_frame_equal 통과")


# STEP 5 - 동일 반복 횟수로 세 엔진 벤치마크
def benchmark_engines(path: Path, repeat: int = 3) -> dict[str, list[float]]:
    """각 엔진의 전체 집계를 같은 횟수로 반복하고 실행 시간(ms)을 반환한다."""
    if repeat < 1:
        raise ValueError("벤치마크 반복 횟수는 1 이상이어야 합니다.")

    runners = {
        "Pandas": run_pandas_query,
        "Polars": run_polars_query,
        "DuckDB": run_duckdb_query,
    }
    measurements = {}

    for name, runner in runners.items():
        timer = timeit.Timer(lambda selected=runner: selected(path))
        measurements[name] = [
            elapsed * 1000 for elapsed in timer.repeat(repeat=repeat, number=1)
        ]

    return measurements


# STEP 5 - 벤치마크 비교표 출력
def print_benchmark_result(measurements: dict[str, list[float]]) -> None:
    """개별 측정값, 중앙값과 Pandas 대비 배속을 실행 시간순으로 출력한다."""
    pandas_median = median(measurements["Pandas"])
    rows = []

    for name, times in measurements.items():
        median_ms = median(times)
        rows.append(
            {
                "엔진": name,
                "반복별 시간(ms)": ", ".join(f"{value:.2f}" for value in times),
                "중앙값(ms)": median_ms,
                "Pandas 대비": pandas_median / median_ms,
            }
        )

    comparison = pd.DataFrame(rows).sort_values("중앙값(ms)")
    comparison["중앙값(ms)"] = comparison["중앙값(ms)"].map(
        lambda value: f"{value:.2f}"
    )
    comparison["Pandas 대비"] = comparison["Pandas 대비"].map(
        lambda value: f"{value:.1f}x"
    )

    print("\n-- STEP 5: 세 엔진 성능 비교 --")
    print(f"동일 반복 횟수: {len(next(iter(measurements.values())))}회")
    print(comparison.to_string(index=False))


def main() -> None:
    """입력을 확인하고 엔진별 집계를 단계적으로 실행한다."""
    try:
        columns, samples, row_count = inspect_source_data(DATA_PATH)
    except FileNotFoundError:
        print(f"오류: 데이터 파일을 찾을 수 없습니다: {DATA_PATH}")
        print("프로젝트 최상위 폴더에서 python data/generate_data.py를 실행하세요.")
        return
    except (UnicodeDecodeError, csv.Error, ValueError) as error:
        print(f"오류: 입력 데이터를 확인할 수 없습니다: {error}")
        return

    print_step0_result(columns, samples, row_count)

    # STEP 1 실행
    try:
        pandas_result, pandas_ms = run_pandas_query(DATA_PATH)
    except (OSError, pd.errors.ParserError) as error:
        print(f"오류: Pandas 집계를 실행할 수 없습니다: {error}")
        return

    print_pandas_result(pandas_result, pandas_ms)

    # STEP 2 실행
    try:
        polars_result, polars_ms = run_polars_query(DATA_PATH)
    except (OSError, pl.exceptions.PolarsError) as error:
        print(f"오류: Polars 집계를 실행할 수 없습니다: {error}")
        return

    print_polars_result(polars_result, polars_ms)

    # STEP 3 실행
    try:
        duckdb_result, duckdb_ms = run_duckdb_query(DATA_PATH)
    except (OSError, duckdb.Error) as error:
        print(f"오류: DuckDB 집계를 실행할 수 없습니다: {error}")
        return

    print_duckdb_result(duckdb_result, duckdb_ms)

    # STEP 4 실행
    try:
        verify_engine_results(pandas_result, polars_result, duckdb_result)
    except AssertionError as error:
        print(f"오류: 세 엔진의 집계 결과가 일치하지 않습니다: {error}")
        return

    print_verification_result()

    # STEP 5 실행
    try:
        benchmark_result = benchmark_engines(DATA_PATH, repeat=3)
    except (
        OSError,
        ValueError,
        pd.errors.ParserError,
        pl.exceptions.PolarsError,
        duckdb.Error,
    ) as error:
        print(f"오류: 성능 비교를 실행할 수 없습니다: {error}")
        return

    print_benchmark_result(benchmark_result)


if __name__ == "__main__":
    main()
