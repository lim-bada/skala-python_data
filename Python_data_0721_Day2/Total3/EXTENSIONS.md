# 종합실습 3 확장 과제 사용법

- 프로그램명: 종합실습 3 - 리포트 자동화 확장 기능
- 작성자: 임해안
- 작성일: 2026-07-21
- 변경 이력: 2026-07-21 Plotly·Slack·지수 백오프 확장 과제 추가

## 1. Plotly 차트 임베드

별도 설정 없이 리포트를 생성하면 카테고리별 매출 인터랙티브 막대 차트가 KPI와
표 사이에 포함됩니다. Plotly JavaScript도 HTML 안에 포함되므로 인터넷 연결 없이
차트를 열 수 있습니다.

```bash
python Python_data_0720_Day2/Total3/report.py
```

## 2. Slack 알림

Slack Incoming Webhook URL을 환경변수로 설정하면 리포트 생성 후 링크를 자동으로
전송합니다. 웹훅 주소는 비밀값이므로 코드나 Git에 저장하지 않습니다.

```bash
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/발급받은/웹훅/주소"
export REPORT_BASE_URL="https://리포트가-게시된-주소.example.com/daily"
python Python_data_0720_Day2/Total3/report.py
```

`REPORT_BASE_URL`은 선택 사항입니다. 생략하면 로컬 HTML의 `file://` URI가 메시지에
포함됩니다. 다른 사용자가 리포트를 열어야 한다면 HTML을 접근 가능한 서버에
게시하고 이 값을 설정해야 합니다.

웹훅이 설정되지 않은 평상시 실행에서는 네트워크 요청을 보내지 않습니다. 알림
전송만 실패한 경우에는 생성된 리포트를 보존하고 실패 메시지를 콘솔과 cron 로그에
남깁니다.

## 3. 지수 백오프 재시도

데이터 파일이 아직 준비되지 않았거나 일시적으로 읽기에 실패하면 기본적으로 최대
3번 시도합니다. 각 실패 후 대기 시간은 1초, 2초 순서로 증가합니다.

설정값은 `config.py`의 다음 항목에서 변경할 수 있습니다.

```python
retry_attempts: int = 3
retry_base_delay: float = 1.0
```

예를 들어 시도 횟수를 4번으로 설정하면 최초 실행을 포함해 최대 4번 시도하며,
실패 후 대기 시간은 1초 → 2초 → 4초가 됩니다. 마지막 시도까지 실패하면 예외를
다시 발생시켜 schedule 또는 cron 로그에서 실패 사실을 확인할 수 있습니다.
