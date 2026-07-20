"""
프로그램명: 실습 2 - Pydantic v2 중첩 스키마 검증
작성자: 임해안
작성일: 2026-7-20

목적:
    - api_response.json의 사용자 레코드 40건을 읽어 데이터 구조를 확인한다.
    - Pydantic 모델로 필드 타입, 나이 범위, 이메일 형식,
      중첩 프로필 점수를 검증한다.
    - 검증 결과를 유효 데이터와 오염 데이터로 분리하고 실패 사유를 보존한다.
    - 전체 40건을 유효 36건과 오염 4건으로 분리한다.

변경 이력:
    - 2026-07-20: 실제 API 응답의 results 목록을 읽도록 데이터 로딩 기능 작성.
    - 2026-07-20: 나이, 이메일, 프로필 점수 기반 의심 데이터 탐색 기능 추가.
    - 2026-07-20: 기본 모델과 나이 범위 Field 제약 추가.
    - 2026-07-20: 이메일 정규화 및 형식 검증 추가.
    - 2026-07-20: Profile 중첩 모델과 점수 범위 검증 추가.
    - 2026-07-20: 전체 데이터를 유효 36건과 오염 4건으로 분리.
    - 2026-07-20: 오염 데이터의 행, ID, 필드, 실패 사유 표 출력 추가.
    - 2026-07-20: Pydantic 모델과 검증 함수의 역할 설명 추가.
"""

import json
from datetime import date
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError, field_validator

DATA_PATH = Path(__file__).resolve().parents[2] / 'data' / 'api_response.json'

with DATA_PATH.open(encoding='utf-8') as f:
    payload = json.load(f)

data = payload['results']
print('응답 상태:', payload['status'])
print('전체 건수:', len(data)) # 40
print(json.dumps(data[0], indent=2, ensure_ascii=False)) # 정상 샘플 1 건

# 어떤 키들이 있는지, 값 타입이 뭔지 훑어보기
for i, row in enumerate(data[:10]):
    print(i, {k: type(v).__name__ for k, v in row.items()})

# 힌트: 음수 나이 / 이메일 형식·누락 / 프로필 점수 범위 초과를 의심하세요
# print('\n-- 의심 데이터 확인 --')
# for i, row in enumerate(data):
#     reasons = []

#     age = row.get('age')
#     if not isinstance(age, int) or not 0 <= age <= 120:
#         reasons.append(f'age={age!r}')

#     email = row.get('email')
#     if not isinstance(email, str) or '@' not in email:
#         reasons.append(f'email={email!r}')

#     profile = row.get('profile', {})
#     score = profile.get('score') if isinstance(profile, dict) else None
#     if not isinstance(score, (int, float)) or not 0 <= score <= 100:
#         reasons.append(f'profile.score={score!r}')

#     if reasons:
#         print(f"index={i}, id={row.get('id')}: {', '.join(reasons)}")

# STEP 1 - 가장 단순한 모델 만들기 (필드 2개)
class BasicUser(BaseModel):
    """사용자의 기본 식별자와 사용자명 타입을 검증하는 모델."""

    id: int
    username: str


print('\n-- STEP 1: 기본 모델 검증 --')
user = BasicUser(id=1, username='user_001')
print('정상 데이터:', user)

try:
    BasicUser(id='숫자아님', username='user_001')
except ValidationError as e:
    print('잘못된 데이터 감지:', e.errors()[0]['msg'])

# STEP 2 - Field로 값의 범위 제약 추가
class AgeValidatedUser(BasicUser):
    """기본 사용자 필드에 0~120 범위의 나이 검증을 추가한 모델."""

    age: int = Field(ge=0, le=120)


print('\n-- STEP 2: 나이 범위 검증 --')
user = AgeValidatedUser(id=1, username='user_001', age=30)
print('정상 데이터:', user)

try:
    AgeValidatedUser(id=7, username='user_007', age=-5)
except ValidationError as e:
    error = e.errors()[0]
    print(f"잘못된 데이터 감지: 필드={'.'.join(str(x) for x in error['loc'])}, 사유={error['msg']}")

# STEP 3 - field_validator로 이메일 형식 검증
class User(AgeValidatedUser):
    """나이 검증 모델에 필수 이메일과 형식 검증을 추가한 모델."""

    email: str

    @field_validator('email')
    @classmethod
    def validate_email(cls, value: str) -> str:
        """이메일을 소문자로 정규화하고 기본 주소 형식을 검증한다."""
        value = value.strip().lower()
        local, separator, domain = value.partition('@')
        if not separator or not local or '.' not in domain:
            raise ValueError('올바른 이메일 형식이 아닙니다')
        return value


print('\n-- STEP 3: 이메일 형식 검증 --')
user = User(
    id=1,
    username='user_001',
    age=30,
    email=' User1@Example.COM ',
)
print('정상 데이터:', user)

try:
    User(id=13, username='user_013', age=28, email='not-an-email')
except ValidationError as e:
    error = e.errors()[0]
    print(f"잘못된 데이터 감지: 필드={'.'.join(str(x) for x in error['loc'])}, 사유={error['msg']}")

# STEP 4 - 중첩 구조를 별도 모델로 검증
class Profile(BaseModel):
    """사용자 프로필과 0~100 범위의 점수를 검증하는 중첩 모델."""

    country: str
    tier: str
    score: float = Field(ge=0, le=100)


class UserRecord(User):
    """API 사용자 레코드 전체와 중첩 Profile 구조를 검증하는 최종 모델."""

    is_active: bool
    signup_date: date
    profile: Profile
    tags: list[str] = Field(default_factory=list)


print('\n-- STEP 4: 중첩 모델 검증 --')
user = UserRecord.model_validate(data[0])
print('정상 데이터:', user)
print('중첩 모델 타입:', type(user.profile).__name__)

try:
    UserRecord.model_validate(data[28])
except ValidationError as e:
    error = e.errors()[0]
    print(f"잘못된 데이터 감지: 필드={'.'.join(str(x) for x in error['loc'])}, 사유={error['msg']}")

# STEP 5 - 전체 데이터를 유효/오염으로 분리
valid, invalid = [], []

for i, row in enumerate(data):
    try:
        valid.append(UserRecord.model_validate(row))
    except ValidationError as e:
        invalid.append({
            'index': i,
            'data': row,
            'errors': e.errors(),
        })

print('\n-- STEP 5: 전체 데이터 검증 --')
print(f'전체 {len(data)}건 → 유효 {len(valid)}건 / 오염 {len(invalid)}건')

# STEP 6 - 오염 데이터의 실패 사유를 표로 출력
print('\n-- STEP 6: 오염 데이터 상세 --')
print(f"{'행':<6}{'ID':<6}{'필드':<20}{'사유'}")
print('-' * 80)

for item in invalid:
    for error in item['errors']:
        row_number = item['index'] + 1
        user_id = item['data'].get('id', '-')
        field = '.'.join(str(x) for x in error['loc'])
        print(f"{row_number:<6}{user_id:<6}{field:<20}{error['msg']}")
