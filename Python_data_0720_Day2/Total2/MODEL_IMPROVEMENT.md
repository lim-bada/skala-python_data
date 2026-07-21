# 종합실습 2 모델 성능 개선 정리

- 작성자: 임해안
- 작성일: 2026-07-21
- 대상 프로그램: `analysis.py`
- 데이터: `data/telco_churn.csv` 7,000건

## 1. 개선 목적

기본 RandomForest 모델의 test ROC-AUC는 `0.635`로, 실습 가이드의 성공 기준인 약 `0.66`보다 낮았다. 훈련 데이터와 테스트 데이터의 성능 차이를 확인하고, 데이터 누수 없이 일반화 성능을 개선하는 것을 목표로 했다.

## 2. 기존 모델의 문제

기존 설정은 다음과 같다.

```python
RandomForestClassifier(
    n_estimators=200,
    random_state=42,
    n_jobs=-1,
)
```

기본값에서는 `max_depth=None`, `min_samples_leaf=1`이 적용된다. 따라서 트리가 제한 없이 깊어지고, 표본 하나만으로도 리프를 만들 수 있다.

측정 결과는 다음과 같다.

| 평가 데이터 | ROC-AUC |
|---|---:|
| train | 1.000 |
| test | 0.635 |

train ROC-AUC가 1.0인 반면 test ROC-AUC는 0.635에 머물렀다. 이는 모델이 훈련 데이터의 잡음까지 외운 과적합 상태임을 의미한다.

## 3. 개선 방법

테스트 데이터에 맞춰 파라미터를 선택하지 않도록 train 데이터 내부에서만 5-fold 계층 교차검증을 수행했다.

```python
cross_validation = StratifiedKFold(
    n_splits=5,
    shuffle=True,
    random_state=42,
)

parameter_grid = {
    "model__max_depth": [6, 8, 10],
    "model__min_samples_leaf": [5, 10, 20],
}

search = GridSearchCV(
    estimator=model_pipeline,
    param_grid=parameter_grid,
    scoring="roc_auc",
    cv=cross_validation,
    refit=True,
)
```

교차검증에서 선택된 파라미터는 다음과 같다.

```text
max_depth = 6
min_samples_leaf = 20
```

- `max_depth=6`: 트리 깊이를 제한해 지나치게 세밀한 분기를 방지한다.
- `min_samples_leaf=20`: 하나의 리프에 최소 20개 표본이 있도록 해 작은 잡음 패턴을 외우지 못하게 한다.
- `n_estimators=200`, `random_state=42`: 기존 설정을 유지한다.

## 4. 개선 결과

| 항목 | 기존 모델(0.5) | 규제 모델(0.5) | 최종 모델(0.269) |
|---|---:|---:|---:|
| 모델 선택 방식 | 기본값 | train 5-fold 교차검증 | 동일 |
| `max_depth` | 제한 없음 | 6 | 6 |
| `min_samples_leaf` | 1 | 20 | 20 |
| train 성능 | ROC-AUC 1.000 | CV ROC-AUC 0.679 | 동일 |
| test ROC-AUC | 0.635 | 0.673 | 0.673 |
| test 정확도 | 0.742 | 0.752 | 0.645 |
| 이탈 정밀도 | 0.414 | 0.250 | 0.354 |
| 이탈 재현율 | 0.172 | 0.015 | 0.576 |
| 이탈 F1-score | 0.243 | 0.028 | 0.438 |
| 저장 모델 크기 | 약 40MB | 약 1.3MB | 약 1.3MB |

ROC-AUC는 `0.635 → 0.673`으로 상승해 가이드의 목표인 0.66 이상을 달성했다. train out-of-fold 예측에서 목표 재현율 0.60을 만족하는 가장 높은 임계값 `0.269`를 선택한 결과, 독립 test 재현율은 `0.576`으로 개선됐다.

## 5. 데이터 누수 방지

모델 개선 과정은 다음 순서를 지켰다.

1. 전체 데이터를 train 80%, test 20%로 먼저 분리한다.
2. `stratify=y`로 양쪽의 이탈 비율을 동일하게 유지한다.
3. 결측치 대치, 표준화, One-Hot 인코딩을 Pipeline 내부에 둔다.
4. train 데이터 내부에서만 GridSearchCV를 수행한다.
5. train out-of-fold 예측으로 분류 임계값을 선택한다.
6. 모델과 임계값 선택이 끝난 뒤 test 데이터에 한 번 평가한다.

따라서 test 데이터의 정보를 이용해 전처리 규칙이나 모델 파라미터를 선택하지 않았다.

## 6. 결과 해석 시 주의점

ROC-AUC는 고객의 이탈 위험 순위를 매기는 능력이며 분류 임계값을 바꿔도 변하지 않는다. 임계값을 `0.5 → 0.269`로 낮추면서 이탈 재현율은 `0.015 → 0.576`으로 높아졌지만 정확도는 `0.752 → 0.645`로 낮아졌다.

이는 더 많은 이탈 고객을 찾는 대신 정상 고객을 이탈 고객으로 판단하는 오탐이 늘어난 결과다. 정확도 하나가 아니라 정밀도·재현율·업무 비용을 함께 판단해야 한다.

## 7. 다음 개선 방향

- ROC-AUC와 함께 PR-AUC, 이탈 재현율, 정밀도 확인
- `class_weight` 또는 비용 민감 학습 검토
- 필요하면 확률 보정(calibration) 적용
- 업무에서 허용할 오탐 비용과 미탐 비용을 기준으로 최종 임계값 결정

임계값 역시 test 데이터에 맞춰 선택하지 않고 train/validation 데이터에서 결정해야 한다.

## 8. 실행 방법

프로젝트 최상위 폴더에서 실행한다.

```bash
source .venv/bin/activate
python Python_data_0720_Day2/Total2/analysis.py
```

정상 실행 시 다음 핵심 결과가 출력된다.

```text
train 5-fold 평균 ROC-AUC: 0.679
ROC-AUC: 0.673
train OOF 선택 임계값: 0.269
이탈 재현율: 0.576
재로딩 예측 일치: 확인
```
