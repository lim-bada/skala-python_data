"""
프로그램명: 종합실습 3 - 매출 리포트 자동 실행
작성자: 임해안
작성일: 2026-07-21

목적:
    - 설정된 판매 데이터를 읽어 HTML 매출 리포트를 한 번 생성한다.
    - --interval 인자를 사용하면 지정한 초 간격으로 리포트를 반복 생성한다.
    - 실행 방식과 분석 로직을 분리해 이후 schedule·cron 방식에서도 재사용한다.

변경 이력:
    - 2026-07-21: STEP 4 run_once 함수와 interval 반복 실행 기능 작성.
    - 2026-07-21: STEP 5 schedule 라이브러리 기반 예약 실행 방식 추가.
    - 2026-07-21: STEP 7 모든 실행 방식이 동일한 run_once를 사용하도록 통합.
    - 2026-07-21: 경량 loop의 의존성 분리를 위해 schedule 지연 import 적용.
"""

import argparse
import time
from collections.abc import Callable, Sequence
from pathlib import Path

try:
    from .report import run_once
except ImportError:  # 파일 경로를 지정해 직접 실행하는 경우
    from report import run_once


# STEP 4 - 단순 while 루프 기반 interval 반복 실행
def run_interval_loop(
    interval: int,
    job: Callable[[], Path] | None = None,
) -> None:
    """작업을 즉시 실행한 뒤 지정한 초 간격으로 계속 반복한다."""
    if interval < 1:
        raise ValueError("실행 간격은 1초 이상이어야 합니다.")

    task = job or run_once
    print(f"반복 실행 시작: {interval}초 간격 (종료: Ctrl+C)")
    while True:
        task()
        time.sleep(interval)


# STEP 5 - schedule 라이브러리 기반 interval 예약 실행
def run_schedule(
    interval: int,
    job: Callable[[], Path] | None = None,
) -> None:
    """작업을 즉시 실행하고 schedule에 등록해 지정한 초마다 반복한다."""
    if interval < 1:
        raise ValueError("실행 간격은 1초 이상이어야 합니다.")

    # schedule 모드를 선택한 경우에만 외부 패키지를 불러온다.
    try:
        import schedule
    except ImportError as error:
        raise RuntimeError(
            "schedule 모드를 사용하려면 'pip install schedule'이 필요합니다."
        ) from error

    task = job or run_once
    schedule.clear()
    schedule.every(interval).seconds.do(task)
    print(f"schedule 실행 시작: {interval}초 간격 (종료: Ctrl+C)")

    # 첫 리포트를 기다리지 않도록 시작할 때 한 번 즉시 실행한다.
    task()
    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    finally:
        schedule.clear()


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """명령행에서 반복 실행 방식과 간격을 입력받는다."""
    parser = argparse.ArgumentParser(description="HTML 매출 리포트 자동 생성")
    parser.add_argument(
        "--mode",
        choices=("loop", "schedule"),
        default="loop",
        help="반복 실행 방식. 기본값은 loop입니다.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        metavar="SECONDS",
        help="리포트 반복 생성 간격(초). 생략하면 한 번만 실행합니다.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    """입력 옵션에 따라 한 번, 단순 반복 또는 schedule 방식으로 실행한다."""
    args = parse_args(argv)

    try:
        if args.interval is None:
            run_once()
        elif args.mode == "schedule":
            run_schedule(args.interval)
        else:
            run_interval_loop(args.interval)
    except KeyboardInterrupt:
        print("\n사용자 요청으로 반복 실행을 종료했습니다.")


if __name__ == "__main__":
    main()
