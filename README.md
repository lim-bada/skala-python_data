# SKALA Python 데이터 분석 실습

SKALA Python 데이터 분석 과정에서 진행한 Day1·Day2 실습과 창의적 개인 실습을 정리한 저장소입니다.

대용량 데이터 처리, Pydantic 검증, 비동기 ETL, Pandas·Polars·DuckDB 비교, 통계 검정, 머신러닝, HTML 리포트 자동화와 웹 로그 이상 탐지를 다룹니다.

## 프로젝트 구성

```text
skala_python/
├── data/                          # 재현 가능한 실습 데이터와 생성기
├── Python_data_0720_Day1/
│   ├── practice1/                 # 대용량 웹 로그 스트리밍 집계
│   ├── practice2/                 # Pydantic 중첩 스키마 검증
│   ├── practice3/                 # asyncio 비동기 수집과 재시도
│   └── Total1/                    # 비동기 ETL·CSV·Parquet 파이프라인
├── Python_data_0721_Day2/
│   ├── practice4/                 # Pandas 데이터 정제·집계·병합
│   ├── practice5/                 # Pandas·Polars·DuckDB 성능 비교
│   ├── Total2/                    # EDA·통계 검정·고객 이탈 모델
│   └── Total3/                    # 매출 HTML 리포트 자동화·스케줄링
├── Advanced/                      # 웹 로그 장애 조기탐지 개인 실습
├── requirements.txt
└── README.md
```

## 실행 환경

- Python 3.11 이상
- macOS, Linux 또는 Windows
- 보고서 PDF 자동 변환은 Google Chrome 필요

`Advanced/build_report.py`는 현재 macOS의 기본 Chrome 경로를 사용합니다. 다른 운영체제에서는 스크립트의 `CHROME_PATH`를 설치 위치에 맞게 변경해야 합니다.

## 설치

저장소를 내려받고 프로젝트 최상위 폴더에서 가상환경을 생성합니다.

```bash
git clone https://github.com/lim-bada/skala-python_data.git
cd skala-python_data
python3 -m venv .venv
```

가상환경을 활성화합니다.

macOS / Linux:

```bash
source .venv/bin/activate
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

필요한 패키지를 설치합니다.

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 데이터

실습 데이터는 `data/`에 포함되어 있습니다.

| 파일 | 용도 |
|---|---|
| `web_logs.csv` | 대용량 로그 집계와 장애 탐지 |
| `api_response.json` | Pydantic 스키마 검증 |
| `events_large.csv` | 100만 건 처리 엔진 성능 비교 |
| `sales_raw.csv` | 판매 데이터 정제와 매출 리포트 |
| `telco_churn.csv` | EDA·통계 검정·고객 이탈 모델 |

동일한 데이터가 필요하면 고정된 seed의 생성기를 실행합니다.

```bash
python data/generate_data.py
```

## Day1 실습

프로젝트 최상위 폴더에서 실행합니다.

```bash
# 실습 1: 대용량 웹 로그 스트리밍 집계
python Python_data_0720_Day1/practice1/pr1.py

# 실습 2: Pydantic 중첩 스키마 검증
python Python_data_0720_Day1/practice2/pr2.py

# 실습 3: asyncio 비동기 수집과 재시도
python Python_data_0720_Day1/practice3/pr3.py

# 종합실습 1: 비동기 ETL 파이프라인
python Python_data_0720_Day1/Total1/pipeline.py
```

종합실습 1은 Pydantic 검증을 통과한 데이터를 CSV와 Parquet으로 저장하고, 유효·오염 데이터 건수와 Parquet 라운드트립을 확인합니다.

## Day2 실습

```bash
# 실습 4: Pandas 정제·결측치·이상치·집계·병합
python Python_data_0721_Day2/practice4/pr4.py

# 실습 5: Pandas·Polars·DuckDB 처리 성능 비교
python Python_data_0721_Day2/practice5/pr5.py

# 종합실습 2: EDA·통계 검정·고객 이탈 모델링
python Python_data_0721_Day2/Total2/analysis.py

# 종합실습 3: 매출 HTML 리포트 한 번 생성
python Python_data_0721_Day2/Total3/report.py
```

종합실습 3의 반복·예약 실행은 다음과 같이 사용할 수 있습니다. 종료할 때는 `Ctrl+C`를 누릅니다.

```bash
# 단순 반복 실행
python Python_data_0721_Day2/Total3/run_scheduler.py --mode loop --interval 60

# schedule 라이브러리 예약 실행
python Python_data_0721_Day2/Total3/run_scheduler.py --mode schedule --interval 60
```

cron 등록 예시와 확장 기능은 다음 문서를 참고합니다.

- [CRON_GUIDE.md](Python_data_0721_Day2/Total3/CRON_GUIDE.md)
- [EXTENSIONS.md](Python_data_0721_Day2/Total3/EXTENSIONS.md)
- [MODEL_IMPROVEMENT.md](Python_data_0721_Day2/Total2/MODEL_IMPROVEMENT.md)

## 창의적 개인 실습

### 웹 로그 기반 서비스 장애 조기탐지 및 원인 분석

기존의 웹 로그 집계를 확장해 IsolationForest가 정상 트래픽 패턴과 다른 시간 구간을 자동 탐지하도록 구현했습니다.

주요 기능은 다음과 같습니다.

- 20만 건 웹 로그 청크 처리와 Pydantic 검증
- 재현 가능한 `/api/v1/search` 503 오류·트래픽 급증 시뮬레이션
- Polars 기반 5분 단위 장애 특성 집계
- 장애 이전 정상 데이터만 사용하는 IsolationForest 학습
- 정밀도·재현율·F1 평가
- 연속 경보 중복 제거와 상위 오류 경로·상태 코드 분석
- Parquet·Joblib 저장 및 재로딩 검증
- Plotly·Jinja2 장애 분석 HTML 리포트

실행 명령어:

```bash
python Advanced/advanced.py
```

기본 실행 결과는 주입한 장애 6개 구간을 모두 탐지하며 정밀도 75%, 재현율 100%, F1 0.857입니다.

자세한 문제 정의와 결과는 다음 문서를 참고합니다.

- [Advanced 실습 안내](Advanced/README.md)
- [창의적 개인 실습 보고서](Advanced/REPORT.md)

## 테스트

각 테스트 파일이 같은 폴더의 모듈을 불러오므로 해당 폴더에서 실행합니다.

```bash
# Day1 종합실습 1: 6개
cd Python_data_0720_Day1/Total1
pytest -q
cd ../..

# Day2 실습 4: 6개
cd Python_data_0721_Day2/practice4
pytest -q
cd ../..

# Day2 종합실습 3: 10개
cd Python_data_0721_Day2/Total3
pytest -q
cd ../..

# Advanced: 11개
pytest -q Advanced/test_advanced.py
```

코드 품질 검사는 프로젝트 최상위 폴더에서 실행합니다.

```bash
ruff check Python_data_0720_Day1/Total1 Python_data_0721_Day2 Advanced
ruff format --check Python_data_0720_Day1/Total1 Python_data_0721_Day2 Advanced
```

## 보고서 재생성

`Advanced/report_images/`의 캡처를 교체한 뒤 Markdown 보고서를 PDF 또는 Word로 변환할 수 있습니다.

```bash
# Google Chrome을 이용한 PDF 생성
python Advanced/build_report.py

# 편집 가능한 Word 문서 생성
python Advanced/build_report_word.py
```

## 주요 의존성

- Pydantic: 스키마와 업무 규칙 검증
- Pandas·Polars·DuckDB: 데이터 처리와 엔진 비교
- PyArrow: Parquet 저장·복원
- SciPy·scikit-learn: 통계 검정과 머신러닝
- Plotly·Jinja2: HTML 시각화와 리포트
- Joblib: 학습 모델 저장·재로딩
- Schedule: 반복 리포트 실행
- Pytest·Ruff: 테스트와 코드 품질 검사
- Markdown·python-docx·Beautiful Soup: 보고서 변환

## GitHub 업로드 제외 항목

`.gitignore`는 다음 자동 생성·개인 환경 파일을 Git 추적에서 제외합니다.

- `.venv/`, Python·Pytest·Ruff 캐시
- PDF·Word 보고서와 중간 `REPORT.html`
- 각 실습의 `output/` 산출물과 로그
- `.DS_Store`, `.vscode/`

소스 코드, Markdown 보고서와 보고서에 연결된 `Advanced/report_images/` 캡처는 저장소에 포함합니다.
