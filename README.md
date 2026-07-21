# Python 데이터 분석 실습

SKALA Day 1 Python 데이터 분석 실습 프로젝트입니다. 대용량 로그 스트리밍 집계, Pydantic 데이터 검증, asyncio 기반 비동기 수집, 비동기 ETL 파이프라인을 다룹니다.

# 실행 화면

각 폴더(Python_data_0720_Day1, Python_data_0721_Day2, Advanced) 실습마다 실행 화면을 첨부하였고 보고서에 실행화면 및 설명이 있습니다.

## 프로젝트 구성

```text
skala_python/
├── data/                         # 실습용 재현 데이터와 생성기
├── Python_data_0720_Day1/
│   ├── practice1/                 # 대용량 로그 스트리밍 집계
│   ├── practice2/                 # Pydantic v2 중첩 스키마 검증
│   ├── practice3/                 # asyncio 비동기 수집기
│   └── Total1/                    # 종합실습 1: 비동기 ETL 파이프라인
├── requirements.txt
└── README.md
```

## 실행 환경

- Python 3.11 이상
- macOS, Linux 또는 Windows

## 설치

저장소를 내려받은 뒤 프로젝트 최상위 폴더에서 가상환경을 생성합니다.

```bash
git clone <저장소-주소>
cd skala_python
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

## 데이터 생성

실습 데이터는 이미 포함되어 있습니다. 동일한 데이터로 다시 생성하려면 다음 명령을 실행합니다.

```bash
python data/generate_data.py
```

생성기는 seed를 고정하므로 실행할 때마다 동일한 데이터를 만듭니다.

## 실습 실행

프로젝트 최상위 폴더에서 실행합니다.

```bash
# 실습 1: 대용량 로그 스트리밍 집계
python Python_data_0720_Day1/practice1/pr1.py

# 실습 2: Pydantic v2 중첩 스키마 검증
python Python_data_0720_Day1/practice2/pr2.py

# 실습 3: asyncio 기반 비동기 수집기
python Python_data_0720_Day1/practice3/pr3.py

# 종합실습 1: 비동기 ETL 파이프라인
python Python_data_0720_Day1/Total1/pipeline.py
```

실습 3은 외부 네트워크를 사용하지 않는 모의 요청으로 동작합니다. 종합실습 1을 실행하면 `Python_data_0720_Day1/Total1/output/`에 `products.csv`, `products.parquet`가 생성됩니다.

## 테스트와 코드 품질 검사

종합실습 1 폴더로 이동한 뒤 실행합니다.

```bash
cd Python_data_0720_Day1/Total1

# ETL 단위 테스트 6개
pytest -v

# Ruff 정적 검사 및 포맷 확인
ruff check .
ruff format --check .
```

예상 결과는 `6 passed`, `All checks passed!`입니다.

## 의존성

`requirements.txt`에는 다음 직접 의존성이 정의되어 있습니다.

- Pydantic: 데이터 스키마 검증
- Pandas, PyArrow: CSV·Parquet 적재
- Pytest: 자동 테스트
- Ruff: 정적 검사와 포맷

## GitHub 업로드 시 제외되는 파일

`.gitignore`는 가상환경, 캐시 파일, PDF 문서, 운영체제 메타데이터를 Git 추적에서 제외합니다. 따라서 `.venv/`는 저장소에 올리지 않고, 각 사용자가 위 설치 절차로 새로 생성합니다.
