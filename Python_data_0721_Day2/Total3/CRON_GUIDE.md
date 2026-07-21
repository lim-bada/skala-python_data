# 종합실습 3 cron 실행 가이드

- 프로그램명: 종합실습 3 - cron 기반 매출 리포트 자동 실행
- 작성자: 임해안
- 작성일: 2026-07-21
- 변경 이력: 2026-07-21 STEP 6 cron 설정·검증·주의사항 작성

cron은 정해진 시각마다 프로그램을 새로 실행합니다. 따라서 cron에서는
`--interval`이나 `--mode schedule`을 사용하지 않고, `run_once()`가 실행되는 기본
명령을 등록합니다.

## 1. cron에서 사용할 명령 먼저 확인

프로젝트 최상위 폴더에서 다음 명령을 실행합니다.

```bash
/Users/limhaean/workspace/skala_python/.venv/bin/python \
  /Users/limhaean/workspace/skala_python/Python_data_0720_Day2/Total3/run_scheduler.py
```

`리포트 생성 완료` 메시지가 나오고 `Total3/output`에 타임스탬프가 포함된 HTML
파일이 생기면 정상입니다.

## 2. 매일 오전 9시 실행 설정

다음 명령으로 현재 사용자의 crontab 편집기를 엽니다.

```bash
crontab -e
```

아래 한 줄을 추가합니다. 긴 명령이지만 줄바꿈하지 않고 한 줄로 입력해야 합니다.

```cron
0 9 * * * /bin/mkdir -p /Users/limhaean/workspace/skala_python/Python_data_0720_Day2/Total3/logs && /Users/limhaean/workspace/skala_python/.venv/bin/python /Users/limhaean/workspace/skala_python/Python_data_0720_Day2/Total3/run_scheduler.py >> /Users/limhaean/workspace/skala_python/Python_data_0720_Day2/Total3/logs/cron.log 2>&1
```

필드별 의미는 다음과 같습니다.

```text
분 시 일 월 요일 명령
0  9  *  *  *   매일 오전 9시에 실행
```

이 명령은 로그 폴더를 먼저 생성하고, 프로젝트 가상환경의 Python으로 리포트를
한 번 생성한 뒤 표준 출력과 오류를 `logs/cron.log`에 누적합니다.

## 3. 1분 간격으로 동작 테스트

최종 시간을 등록하기 전에 아래 설정으로 짧게 시험할 수 있습니다.

```cron
* * * * * /bin/mkdir -p /Users/limhaean/workspace/skala_python/Python_data_0720_Day2/Total3/logs && /Users/limhaean/workspace/skala_python/.venv/bin/python /Users/limhaean/workspace/skala_python/Python_data_0720_Day2/Total3/run_scheduler.py >> /Users/limhaean/workspace/skala_python/Python_data_0720_Day2/Total3/logs/cron.log 2>&1
```

한두 번 실행된 것을 확인한 뒤 반드시 매일 오전 9시 설정으로 되돌립니다.

## 4. 등록 및 실행 결과 확인

등록된 cron 작업을 확인합니다.

```bash
crontab -l
```

생성된 HTML과 로그를 확인합니다.

```bash
ls -lt Python_data_0720_Day2/Total3/output
tail -n 30 Python_data_0720_Day2/Total3/logs/cron.log
```

설정을 중단하려면 `crontab -e`에서 이 프로젝트에 해당하는 한 줄만 삭제합니다.
다른 cron 작업까지 모두 삭제하는 `crontab -r`은 사용하지 않습니다.

## 주의사항

- cron의 현재 작업 폴더와 `PATH`는 터미널과 다르므로 모든 경로를 절대 경로로
  작성합니다.
- 시스템의 `python`이 아니라 프로젝트의 `.venv/bin/python`을 사용합니다.
- cron 자체가 반복 실행하므로 `--interval` 옵션을 함께 사용하지 않습니다.
- 실행 결과는 고정 파일명이 아니라 `report_YYYYMMDD_HHMMSS.html`로 저장되어 기존
  리포트를 덮어쓰지 않습니다.
- macOS에서 권한 오류가 발생하면 cron 또는 Python이 프로젝트 폴더에 접근할 수
  있는지 시스템 설정의 개인정보 보호 및 보안 항목을 확인합니다.
- `cron.log`는 계속 커질 수 있으므로 장기 운영 환경에서는 로그 순환 정책을
  별도로 적용합니다.
