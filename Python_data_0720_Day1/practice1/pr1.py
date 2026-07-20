"""
프로그램명: 실습 1 - 대용량 웹 로그 스트리밍 집계
작성자: 임해안
작성일: 2026-7-20

목적:
    - web_logs.csv를 제너레이터로 한 행씩 읽어 메모리 사용을 줄인다.
    - 상태코드, 경로, 시간대, IP별 요청 수를 Counter로 집계한다.
    - 전체 요청 수, 5xx 오류율, 인기 경로, 시간대별 요청 수,
      접속 상위 IP를 리포트로 출력한다.
    - functools.reduce를 이용한 누적(fold) 패턴을 확인한다.

변경 이력:
    - 2026-07-20: 제너레이터 기반 로그 읽기와 온라인 집계 기능 작성.
    - 2026-07-20: 데이터 파일 경로를 __file__ 기준으로 변경.
    - 2026-07-20: 상태코드 TOP 5 제목과 시간대별 요청 수 출력 추가.
    - 2026-07-20: 주요 함수의 입력, 처리 방식, 반환값 설명 추가.
    - 2026-07-20: tracemalloc을 이용한 readlines·제너레이터 메모리 비교 추가.
"""

# step1 - 한 줄을 '딕셔너리 하나'로 바꾸는 제너레이터 만들기
import csv
import gc
import tracemalloc
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parents[2] / 'data' / 'web_logs.csv'

def read_logs(path):
    """CSV 로그를 한 행씩 읽어 딕셔너리로 전달하는 제너레이터.

    전체 파일을 리스트로 올리지 않으며, 각 행은 CSV 헤더를 키로 갖는
    딕셔너리 형태로 yield된다.

    Args:
        path: 읽을 CSV 로그 파일의 경로.
    """
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f) # 헤더를 키로 자동 인식
        for row in reader:
            yield row

# # 확인: 앞 3 건만 꺼내보기
# gen = read_logs(DATA_PATH)
# for _ in range(3):
#     print(next(gen))

#step2 - 가장 쉬운 집계 하나만 먼저 (상태코드 개수)
from collections import Counter

status_counter = Counter()
total = 0

for row in read_logs(DATA_PATH):
    total += 1
    status_counter[row['status']] += 1 # 지나갈 때마다 1 씩 누적

print('\n총 건수: ', total, '\n')
print('-- 상태코드 TOP 5 --')
print(status_counter.most_common(5))

#step3 - 지표를 늘린다 — 경로별 · 시간대별 · IP 별
from collections import Counter, defaultdict

total = 0
by_status = Counter()
by_path = Counter()
by_hour = Counter()
by_ip = Counter()

for row in read_logs(DATA_PATH): # ★ 단 한 번만 훑음
    total += 1
    by_status[row['status']] += 1
    by_path[row['path']] += 1
    by_ip[row['ip']] += 1
    hour = row['timestamp'][11:13] # 'YYYY-MM-DD HH:MM:SS' → HH
    by_hour[hour] += 1

#step4 - 5xx 비율 계산 — 체크포인트 맞추기
# 상태코드가 문자열일 수 있으니 int 로 변환해서 비교
err_5xx = sum(c for s, c in by_status.items() if str(s).startswith('5'))
ratio = err_5xx / total * 100
print(f'5xx: {err_5xx}건 ({ratio:.1f}%)')

#step5 - fold 패턴 — functools.reduce 로 '누적'을 함수로
from functools import reduce
from collections import Counter

def fold(acc, row):
    """로그 한 행의 요청 수와 상태코드를 누적기에 반영한다.

    Args:
        acc: total과 status Counter를 가진 누적 딕셔너리.
        row: CSV에서 읽은 로그 한 행.

    Returns:
        현재 로그가 반영된 동일한 누적 딕셔너리.
    """
    acc['total'] += 1
    acc['status'][row['status']] += 1
    return acc

init = {'total': 0, 'status': Counter()}
result = reduce(fold, read_logs(DATA_PATH), init)
print(result['total'], '\n')

#step6 - 리포트로 예쁘게 출력 + 상위 IP
print('=' * 40)
print(f'총 요청 수 : {total:,}', '\n')
print(f'5xx 오류율 : {ratio:.1f}%', '\n')
print('-- 인기 경로 TOP 5 --')
for path, cnt in by_path.most_common(5):
    print(f' {path:<20} {cnt:>7,}')
print('\n-- 시간대별 요청 수 --')
for hour, cnt in sorted(by_hour.items()):
    print(f' {hour}시 {cnt:>7,}')
print('\n-- 접속 상위 IP TOP 5 --')
for ip, cnt in by_ip.most_common(5):
    print(f' {ip:<20}{cnt:>7,}')


# 한 걸음 더 - readlines와 제너레이터의 최대 메모리 비교
def count_with_readlines(path):
    """CSV 전체 행을 리스트에 올린 뒤 헤더를 제외한 로그 건수를 반환한다."""
    with open(path, encoding="utf-8") as file:
        lines = file.readlines()
    return max(len(lines) - 1, 0)


def count_with_generator(path):
    """제너레이터로 CSV를 한 행씩 처리해 로그 건수를 반환한다."""
    return sum(1 for _ in read_logs(path))


def measure_peak_memory(counter, path):
    """집계 함수 실행 중 tracemalloc이 관찰한 건수와 최대 메모리를 반환한다."""
    gc.collect()
    tracemalloc.start()
    count = counter(path)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return count, peak / 1024 / 1024


list_count, list_peak = measure_peak_memory(count_with_readlines, DATA_PATH)
generator_count, generator_peak = measure_peak_memory(
    count_with_generator,
    DATA_PATH,
)
reduction = (1 - generator_peak / list_peak) * 100 if list_peak else 0

print('\n-- 한 걸음 더: 최대 메모리 비교 --')
print(f' readlines  : {list_count:>7,}건, {list_peak:>7.2f} MB')
print(f' generator  : {generator_count:>7,}건, {generator_peak:>7.2f} MB')
print(f' 메모리 절감률: {reduction:.1f}%')
