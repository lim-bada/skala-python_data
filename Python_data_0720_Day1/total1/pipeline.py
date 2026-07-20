"""
프로그램명: 종합실습 1 - 비동기 ETL 파이프라인
작성자: 임해안
작성일: 2026-7-20

목적:
    - 상품 데이터를 비동기로 추출하고 Pydantic 모델로 검증한다.
    - 유효 데이터를 CSV와 Parquet 형식으로 저장한다.
    - Extract, Transform, Load 단계를 독립적으로 테스트 가능한 구조로 설계한다.

변경 이력:
    - 2026-07-20: 유효·오염 데이터를 분리하는 순수 transform 함수 작성.
    - 2026-07-20: 동시성 제한과 재시도를 적용한 비동기 extract 함수 작성.
    - 2026-07-20: 유효 데이터를 CSV와 Parquet으로 저장하는 load 함수 작성.
    - 2026-07-20: Extract·Transform·Load를 조율하는 run 함수 작성.
    - 2026-07-20: Ruff 정적 검사 및 코드 포맷 적용.
"""

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from models import Product


USE_REAL_HTTP = False
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "output"


async def fetch(product_id: int) -> dict:
    """네트워크 응답을 흉내 내어 결정적인 상품 딕셔너리를 반환한다."""
    await asyncio.sleep(0.05)
    categories = (" FOOD ", "TECH", "Home")
    return {
        "id": product_id,
        "name": f"Product {product_id}",
        "category": categories[product_id % len(categories)],
        "price": float((product_id + 1) * 10),
    }


async def extract(
    ids: list[int],
    max_concurrent: int = 10,
    max_retries: int = 3,
    fetcher: Callable[[int], Awaitable[dict]] | None = None,
    backoff_base: float = 1.0,
) -> list[dict]:
    """상품 ID를 제한된 동시성으로 수집하고 일시적 실패를 재시도한다.

    Args:
        ids: 수집할 상품 ID 목록.
        max_concurrent: 동시에 실행할 수 있는 최대 요청 수.
        max_retries: 항목별 최대 시도 횟수.
        fetcher: 테스트나 실제 수집 시 교체할 비동기 요청 함수.
        backoff_base: 지수 백오프 대기 시간의 기준값.

    Returns:
        성공적으로 수집한 원본 상품 딕셔너리 목록.
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    request = fetch if fetcher is None else fetcher

    async def one(product_id: int) -> dict:
        """상품 하나를 수집하고 연결 오류나 timeout 발생 시 재시도한다."""
        for attempt in range(max_retries):
            try:
                async with semaphore:
                    return await request(product_id)
            except (ConnectionError, TimeoutError):
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(backoff_base * (2**attempt))

        raise RuntimeError("재시도 횟수는 1 이상이어야 합니다")

    results = await asyncio.gather(
        *(one(product_id) for product_id in ids),
        return_exceptions=True,
    )
    return [result for result in results if not isinstance(result, Exception)]


def transform(
    raw: list[dict],
) -> tuple[list[Product], list[dict]]:
    """원본 상품을 검증해 유효한 모델과 오류 정보로 분리한다.

    네트워크 요청이나 파일 저장 없이 입력에 따른 결과만 반환하는 순수 함수다.

    Args:
        raw: 검증할 원본 상품 딕셔너리 목록.

    Returns:
        유효한 Product 목록과 원본·오류 정보를 담은 오염 데이터 목록.
    """
    valid = []
    invalid = []

    for row in raw:
        try:
            valid.append(Product.model_validate(row))
        except ValidationError as error:
            invalid.append(
                {
                    "data": row,
                    "errors": error.errors(),
                }
            )

    return valid, invalid


def load(
    valid: list[Product],
    out_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> pd.DataFrame:
    """유효한 상품을 DataFrame으로 변환하고 CSV·Parquet으로 저장한다.

    Args:
        valid: 검증을 통과한 Product 모델 목록.
        out_dir: 산출 파일을 저장할 디렉터리.

    Returns:
        파일 저장에 사용한 상품 DataFrame.
    """
    output_dir = Path(out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    dataframe = pd.DataFrame(product.model_dump() for product in valid)
    dataframe.to_csv(output_dir / "products.csv", index=False)
    dataframe.to_parquet(output_dir / "products.parquet", index=False)
    return dataframe


async def run(ids: list[int]) -> dict:
    """Extract, Transform, Load를 순서대로 호출하고 처리 요약을 반환한다."""
    raw = await extract(ids)
    valid, invalid = transform(raw)
    dataframe = load(valid)
    return {
        "total": len(raw),
        "valid": len(valid),
        "invalid": len(invalid),
        "rows_saved": len(dataframe),
    }


if __name__ == "__main__":
    summary = asyncio.run(run(list(range(60))))
    print(summary)
