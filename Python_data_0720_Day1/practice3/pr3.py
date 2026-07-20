"""
프로그램명: 실습 3 - asyncio 기반 비동기 수집기
작성자: 임해안
작성일: 2026-7-20

목적:
    - 동기 방식과 비동기 방식의 실행 시간을 비교한다.
    - async/await로 I/O 대기 시간을 중첩하는 원리를 익힌다.
    - 동시 요청 제한, 타임아웃, 재시도, 예외 격리를 단계적으로 구현한다.
    - 재시도 후에도 실패한 요청을 dead-letter 파일에 보존한다.

변경 이력:
    - 2026-07-20: 동기 방식의 모의 수집 및 실행 시간 측정 기능 작성.
    - 2026-07-20: async/await를 이용한 단일 비동기 수집 기능 추가.
    - 2026-07-20: asyncio.gather를 이용한 60건 동시 수집 기능 추가.
    - 2026-07-20: Semaphore를 이용한 최대 동시 요청 10건 제한 추가.
    - 2026-07-20: 요청별 타임아웃 처리 기능 추가.
    - 2026-07-20: 일시적 실패에 대한 지수 백오프 재시도 기능 추가.
    - 2026-07-20: gather의 return_exceptions를 이용한 예외 격리 추가.
    - 2026-07-20: 주요 함수의 역할, 매개변수, 반환 동작 설명 추가.
    - 2026-07-20: 최종 실패 요청을 dead_letter.json에 저장하는 기능 추가.
"""

import asyncio
import json
import time
from pathlib import Path


# STEP 0 - 동기 버전의 실행 시간 측정
def fetch_sync(item_id):
    """네트워크 대기를 흉내 내고 단일 항목을 동기 방식으로 반환한다."""
    time.sleep(0.1) # 네트워크 대기를 흉내
    return {'id': item_id, 'ok': True}


start = time.perf_counter()
results = [fetch_sync(i) for i in range(60)]
print(f'동기: {time.perf_counter() - start:.2f}초') # 약 6 초


# STEP 1 - async/await 기본 문법
async def fetch(item_id):
    """네트워크 대기를 흉내 내고 단일 항목을 비동기 방식으로 반환한다."""
    await asyncio.sleep(0.1) # 비동기 I/O 대기를 흉내
    return {'id': item_id, 'ok': True}


async def main_step1():
    """단일 비동기 요청을 실행해 async/await의 기본 동작을 확인한다."""
    result = await fetch(1)
    print('비동기 단일 요청:', result)


asyncio.run(main_step1())


# STEP 2 - gather로 60건을 동시에 실행
async def main_step2():
    """60개의 비동기 요청을 gather로 동시에 실행하고 결과를 반환한다."""
    tasks = [fetch(i) for i in range(60)]
    return await asyncio.gather(*tasks)


start = time.perf_counter()
async_results = asyncio.run(main_step2())
elapsed = time.perf_counter() - start
print(f'비동기: {len(async_results)}건, {elapsed:.2f}초')


# STEP 3 - Semaphore로 동시 요청 수 제한
MAX_CONCURRENT = 10


async def fetch_limited(item_id, semaphore):
    """Semaphore 입장권을 얻은 동안에만 단일 요청을 실행한다."""
    async with semaphore:
        await asyncio.sleep(0.1)
        return {'id': item_id, 'ok': True}


async def main_step3():
    """동시 요청을 최대 MAX_CONCURRENT건으로 제한해 60건을 수집한다."""
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    tasks = [fetch_limited(i, semaphore) for i in range(60)]
    return await asyncio.gather(*tasks)


start = time.perf_counter()
limited_results = asyncio.run(main_step3())
elapsed = time.perf_counter() - start
print(
    f'비동기 제한: {len(limited_results)}건, '
    f'최대 동시 {MAX_CONCURRENT}건, {elapsed:.2f}초'
)


# STEP 4 - timeout으로 요청별 최대 대기 시간 제한
REQUEST_TIMEOUT = 3.0


async def fetch_with_timeout(
    item_id,
    semaphore,
    timeout=REQUEST_TIMEOUT,
    delay=0.1,
):
    """제한 시간 안에 모의 요청을 수행하고 성공 또는 timeout 결과를 반환한다.

    Args:
        item_id: 수집할 항목의 식별자.
        semaphore: 동시 실행 수를 제한하는 Semaphore.
        timeout: 요청별 최대 대기 시간(초).
        delay: 모의 요청에 필요한 대기 시간(초).
    """
    async with semaphore:
        try:
            async with asyncio.timeout(timeout):
                await asyncio.sleep(delay)
                return {'id': item_id, 'ok': True}
        except TimeoutError:
            return {'id': item_id, 'ok': False, 'reason': 'timeout'}


async def main_step4():
    """60건에 Semaphore와 요청별 타임아웃을 함께 적용한다."""
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    tasks = [fetch_with_timeout(i, semaphore) for i in range(60)]
    return await asyncio.gather(*tasks)


start = time.perf_counter()
timeout_results = asyncio.run(main_step4())
elapsed = time.perf_counter() - start
success_count = sum(result['ok'] for result in timeout_results)
timeout_count = len(timeout_results) - success_count
print(
    f'타임아웃 적용: 성공 {success_count}건 / '
    f'타임아웃 {timeout_count}건, {elapsed:.2f}초'
)


async def timeout_demo():
    """대기 시간보다 짧은 제한을 적용해 timeout 동작을 의도적으로 확인한다."""
    semaphore = asyncio.Semaphore(1)
    return await fetch_with_timeout(
        999,
        semaphore,
        timeout=0.05,
        delay=0.1,
    )


print('타임아웃 동작 확인:', asyncio.run(timeout_demo()))


# STEP 5 - 일시적 실패를 지수 백오프로 재시도
MAX_RETRIES = 3
TRANSIENT_FAILURE_IDS = {7, 13}
PERMANENT_FAILURE_IDS = frozenset({55})


async def do_request(item_id, attempt, permanent_failure_ids=frozenset()):
    """모의 요청을 수행하고 지정 조건에 따라 일시적·영구 오류를 발생시킨다."""
    await asyncio.sleep(0.1)
    if item_id in permanent_failure_ids:
        raise ConnectionError('재시도로 복구되지 않는 연결 오류')
    if item_id in TRANSIENT_FAILURE_IDS and attempt == 0:
        raise ConnectionError('일시적 연결 오류')
    return {'id': item_id, 'ok': True, 'attempts': attempt + 1}


async def fetch_retry(
    item_id,
    semaphore,
    max_retries=MAX_RETRIES,
    permanent_failure_ids=frozenset(),
    backoff_scale=1.0,
):
    """연결 오류나 timeout 발생 시 지수 백오프로 요청을 재시도한다.

    성공하면 요청 결과와 시도 횟수를 반환하고, 마지막 시도까지 실패하면
    오류 메시지와 전체 시도 횟수가 포함된 실패 결과를 반환한다.
    """
    for attempt in range(max_retries):
        try:
            async with semaphore:
                async with asyncio.timeout(REQUEST_TIMEOUT):
                    return await do_request(
                        item_id,
                        attempt,
                        permanent_failure_ids,
                    )
        except (ConnectionError, TimeoutError) as error:
            if attempt == max_retries - 1:
                return {
                    'id': item_id,
                    'ok': False,
                    'error': str(error),
                    'attempts': attempt + 1,
                }

            wait = backoff_scale * (2 ** attempt)
            print(
                f'요청 {item_id} 실패({error}), '
                f'{wait:g}초 후 재시도'
            )
            await asyncio.sleep(wait)


async def main_step5():
    """60건에 동시 실행 제한, 타임아웃, 재시도 정책을 적용한다."""
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    tasks = [fetch_retry(i, semaphore) for i in range(60)]
    return await asyncio.gather(*tasks)


start = time.perf_counter()
retry_results = asyncio.run(main_step5())
elapsed = time.perf_counter() - start
success_count = sum(result['ok'] for result in retry_results)
failure_count = len(retry_results) - success_count
retried_count = sum(result['attempts'] > 1 for result in retry_results)
print(
    f'재시도 적용: 성공 {success_count}건 / 실패 {failure_count}건, '
    f'재시도 발생 {retried_count}건, {elapsed:.2f}초'
)


# STEP 6 - 하나의 예외가 전체 작업을 중단하지 않도록 격리
async def fetch_may_raise(item_id, semaphore):
    """예외 격리 확인을 위해 ID 42에서 예상하지 못한 오류를 발생시킨다."""
    async with semaphore:
        await asyncio.sleep(0.1)
        if item_id == 42:
            raise RuntimeError('예상하지 못한 수집 오류')
        return {'id': item_id, 'ok': True}


async def main_step6():
    """예외를 결과로 수집해 한 요청의 실패가 나머지 요청에 전파되지 않게 한다."""
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    tasks = [fetch_may_raise(i, semaphore) for i in range(60)]
    return await asyncio.gather(*tasks, return_exceptions=True)


isolated_results = asyncio.run(main_step6())
successful_results = [
    result for result in isolated_results
    if not isinstance(result, Exception)
]
failed_results = [
    result for result in isolated_results
    if isinstance(result, Exception)
]

print(
    f'예외 격리: 성공 {len(successful_results)}건 / '
    f'실패 {len(failed_results)}건'
)
for error in failed_results:
    print(f'격리된 오류: {type(error).__name__}: {error}')


# 한 걸음 더 - 최종 실패 요청을 dead-letter 파일에 보존
DEAD_LETTER_PATH = Path(__file__).resolve().parent / 'dead_letter.json'


async def main_dead_letter():
    """영구 실패를 포함한 60건을 수집해 재시도 결과를 반환한다."""
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    tasks = [
        fetch_retry(
            i,
            semaphore,
            permanent_failure_ids=PERMANENT_FAILURE_IDS,
            backoff_scale=0.1,
        )
        for i in range(60)
    ]
    return await asyncio.gather(*tasks)


def save_dead_letters(results, path):
    """실패 결과의 ID, 오류 사유, 시도 횟수를 JSON 파일에 저장한다."""
    dead_letters = [
        {
            'id': result['id'],
            'error': result['error'],
            'attempts': result['attempts'],
        }
        for result in results
        if not result['ok']
    ]
    path.write_text(
        json.dumps(dead_letters, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    return dead_letters


dead_letter_results = asyncio.run(main_dead_letter())
dead_letters = save_dead_letters(dead_letter_results, DEAD_LETTER_PATH)
print(f'dead-letter 저장: {len(dead_letters)}건 → {DEAD_LETTER_PATH}')
