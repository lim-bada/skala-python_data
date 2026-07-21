"""
프로그램명: 종합실습 2 - EDA·통계·ML 파이프라인
작성자: 임해안
작성일: 2026-07-21

목적:
    - 통신 고객 데이터를 EDA하고 이탈과 관련된 특성을 탐색한다.
    - 시각화와 통계 검정으로 관찰된 차이가 유의한지 확인한다.
    - 전처리와 RandomForest 모델을 Pipeline으로 묶어 데이터 누수를 방지한다.
    - ROC-AUC로 모델을 평가하고 시각화 리포트와 모델을 저장한다.

변경 이력:
    - 2026-07-21: STEP 0 Polars 기반 기초 EDA 및 이탈 비율 확인 추가.
    - 2026-07-21: STEP 1 이탈 여부별 평균 요금·가입기간 비교 추가.
    - 2026-07-21: STEP 2 이탈 여부별 월요금 Plotly HTML 시각화 추가.
    - 2026-07-21: STEP 3 Welch t-검정과 카이제곱 독립성 검정 추가.
    - 2026-07-21: STEP 4 모델 입력·타깃 분리 및 전처리 전략 정의 추가.
    - 2026-07-21: STEP 5 ColumnTransformer 전처리 파이프라인 구성 추가.
    - 2026-07-21: STEP 6 계층 분할 및 RandomForest Pipeline 학습 추가.
    - 2026-07-21: STEP 7 ROC-AUC 평가 및 전체 Pipeline 저장·재로딩 검증 추가.
    - 2026-07-21: train 5-fold 교차검증 기반 RandomForest 성능 개선 추가.
    - 2026-07-21: train out-of-fold 기반 분류 임계값 선택 및 재현율 개선 추가.
"""

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import polars as pl
import plotly.express as px
from scipy import stats
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import classification_report, precision_recall_curve, roc_auc_score
from sklearn.model_selection import (
    GridSearchCV,
    StratifiedKFold,
    cross_val_predict,
    train_test_split,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


# 현재 실행 위치와 무관하게 프로젝트의 원본 데이터와 출력 폴더를 찾는다.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = PROJECT_ROOT / "data" / "telco_churn.csv"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"
CHART_PATH = OUTPUT_DIR / "churn_charges.html"
MODEL_PATH = OUTPUT_DIR / "churn_model.joblib"
SIGNIFICANCE_LEVEL = 0.05
TARGET_RECALL = 0.60

NUMERIC_FEATURES = [
    "senior",
    "tenure_months",
    "monthly_charges",
    "total_charges",
    "num_services",
]
CATEGORICAL_FEATURES = ["gender", "contract", "payment_method"]

REQUIRED_COLUMNS = {
    "customer_id",
    "gender",
    "senior",
    "tenure_months",
    "monthly_charges",
    "total_charges",
    "contract",
    "payment_method",
    "num_services",
    "churn",
}


def load_churn_data(path: Path) -> pl.DataFrame:
    """통신 고객 CSV를 읽고 종합실습에 필요한 컬럼이 있는지 검증한다."""
    df = pl.read_csv(path)
    missing_columns = REQUIRED_COLUMNS - set(df.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"필수 컬럼이 없습니다: {missing}")
    if df.is_empty():
        raise ValueError("입력 데이터가 비어 있습니다.")
    return df


# STEP 0 - Polars 기초 EDA와 타깃 비율 확인
def summarize_churn_ratio(df: pl.DataFrame) -> pl.DataFrame:
    """이탈 여부별 고객 수와 전체 대비 비율을 계산한다."""
    return (
        df.group_by("churn")
        .len(name="count")
        .with_columns((pl.col("count") / df.height * 100).round(2).alias("ratio_pct"))
        .sort("churn")
    )


def print_step0_result(df: pl.DataFrame, churn_ratio: pl.DataFrame) -> None:
    """데이터 구조, 샘플, 기술통계와 타깃 분포를 출력한다."""
    print("\n-- STEP 0: Polars 기초 EDA --")
    print(f"데이터 파일: {DATA_PATH}")
    print(f"행·열 개수: {df.shape}")
    print(f"컬럼: {df.columns}")

    print("\n[앞 5건]")
    print(df.head())

    print("\n[기술통계]")
    print(df.describe())

    print("\n[이탈 여부별 고객 수와 비율]")
    print(churn_ratio)

    minority_ratio = churn_ratio["ratio_pct"].min()
    print(f"소수 클래스 비율: {minority_ratio:.2f}%")
    print("평가 지표: 클래스 불균형을 고려해 ROC-AUC를 사용합니다.")


# STEP 1 - 이탈 여부별 고객 특성 비교
def compare_churn_groups(df: pl.DataFrame) -> pl.DataFrame:
    """이탈 여부별 평균 월요금, 평균 가입기간과 고객 수를 집계한다."""
    return (
        df.group_by("churn")
        .agg(
            pl.col("monthly_charges").mean().round(2).alias("avg_monthly_charges"),
            pl.col("tenure_months").mean().round(2).alias("avg_tenure_months"),
            pl.len().alias("count"),
        )
        .sort("churn")
    )


def print_step1_result(group_comparison: pl.DataFrame) -> None:
    """이탈·잔류 고객의 특성 차이와 다음 단계에서 확인할 가설을 출력한다."""
    print("\n-- STEP 1: 이탈 여부별 고객 특성 비교 --")
    print(group_comparison)

    churned = group_comparison.filter(pl.col("churn") == 1).row(0, named=True)
    retained = group_comparison.filter(pl.col("churn") == 0).row(0, named=True)
    charge_difference = churned["avg_monthly_charges"] - retained["avg_monthly_charges"]
    tenure_difference = churned["avg_tenure_months"] - retained["avg_tenure_months"]

    print(f"이탈 고객의 평균 월요금 차이: {charge_difference:+.2f}")
    print(f"이탈 고객의 평균 가입기간 차이: {tenure_difference:+.2f}개월")
    print("가설: 월요금과 이탈 여부가 연관되어 있는지 통계 검정이 필요합니다.")


# STEP 2 - Plotly 이탈 여부별 월요금 분포 시각화
def create_churn_boxplot(df: pl.DataFrame, output_path: Path) -> Path:
    """이탈 여부별 월요금 분포를 박스플롯으로 만들고 HTML로 저장한다."""
    chart_data = df.select("churn", "monthly_charges").to_pandas()
    chart_data["churn_label"] = chart_data["churn"].map({0: "잔류", 1: "이탈"})

    figure = px.box(
        chart_data,
        x="churn_label",
        y="monthly_charges",
        color="churn_label",
        points="outliers",
        category_orders={"churn_label": ["잔류", "이탈"]},
        labels={"churn_label": "이탈 여부", "monthly_charges": "월요금"},
        title="이탈 여부별 월요금 분포",
    )
    figure.update_layout(showlegend=False)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.write_html(output_path, include_plotlyjs=True)
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise OSError(f"HTML 리포트가 생성되지 않았습니다: {output_path}")
    return output_path


def print_step2_result(output_path: Path) -> None:
    """Plotly HTML 리포트의 저장 위치와 파일 크기를 출력한다."""
    size_kb = output_path.stat().st_size / 1024
    print("\n-- STEP 2: Plotly HTML 시각화 --")
    print(f"HTML 리포트: {output_path}")
    print(f"파일 크기: {size_kb:,.1f} KB")


# STEP 3 - t-검정과 카이제곱 독립성 검정
def run_statistical_tests(df: pl.DataFrame) -> dict[str, float]:
    """월요금 평균 차이와 계약 유형·이탈 여부의 연관성을 통계적으로 검정한다."""
    pdf = df.select("monthly_charges", "contract", "churn").to_pandas()
    churned_charges = pdf.loc[pdf["churn"] == 1, "monthly_charges"].dropna()
    retained_charges = pdf.loc[pdf["churn"] == 0, "monthly_charges"].dropna()
    if churned_charges.empty or retained_charges.empty:
        raise ValueError("t-검정에 필요한 이탈·잔류 그룹 데이터가 없습니다.")

    t_result = stats.ttest_ind(
        churned_charges,
        retained_charges,
        equal_var=False,
        nan_policy="omit",
    )

    contingency = pd.crosstab(pdf["contract"], pdf["churn"])
    if contingency.shape[0] < 2 or contingency.shape[1] < 2:
        raise ValueError("카이제곱 검정에 필요한 범주 조합이 부족합니다.")
    chi2, chi_pvalue, dof, _ = stats.chi2_contingency(contingency)

    return {
        "t_statistic": float(t_result.statistic),
        "t_pvalue": float(t_result.pvalue),
        "chi2_statistic": float(chi2),
        "chi2_pvalue": float(chi_pvalue),
        "chi2_dof": float(dof),
    }


def significance_message(pvalue: float) -> str:
    """p-value를 유의수준과 비교해 통계적 유의성 해석을 반환한다."""
    if pvalue < SIGNIFICANCE_LEVEL:
        return "통계적으로 유의합니다."
    return "통계적으로 유의하지 않습니다."


def print_step3_result(results: dict[str, float]) -> None:
    """두 통계 검정의 통계량, p-value와 올바른 해석을 출력한다."""
    print("\n-- STEP 3: 통계 검정 --")
    print(f"Welch t-검정: t={results['t_statistic']:.4f}, p={results['t_pvalue']:.2e}")
    print(f"월요금 평균 차이는 {significance_message(results['t_pvalue'])}")

    print(
        f"카이제곱 검정: chi2={results['chi2_statistic']:.4f}, "
        f"dof={int(results['chi2_dof'])}, p={results['chi2_pvalue']:.2e}"
    )
    print(
        f"계약 유형과 이탈 여부의 연관성은 {significance_message(results['chi2_pvalue'])}"
    )
    print("해석 주의: 통계적 연관성이 인과관계를 의미하지는 않습니다.")


# STEP 4 - 모델 입력·타깃 분리 및 전처리 전략 정의
def prepare_model_data(df: pl.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """식별자와 타깃을 제외하고 모델 특성 X와 이진 타깃 y를 반환한다."""
    selected_columns = NUMERIC_FEATURES + CATEGORICAL_FEATURES + ["churn"]
    pdf = df.select(selected_columns).to_pandas()
    features = pdf[NUMERIC_FEATURES + CATEGORICAL_FEATURES].copy()
    target = pdf["churn"].astype("int64")

    if not set(target.unique()).issubset({0, 1}):
        raise ValueError("churn 타깃은 0과 1로 구성되어야 합니다.")
    return features, target


def print_step4_result(features: pd.DataFrame, target: pd.Series) -> None:
    """모델 입력 컬럼, 결측치와 이후 적용할 전처리 전략을 출력한다."""
    print("\n-- STEP 4: 모델 데이터 준비와 전처리 전략 --")
    print(f"특성 행·열 개수: {features.shape}")
    print(f"수치형 특성: {NUMERIC_FEATURES}")
    print(f"범주형 특성: {CATEGORICAL_FEATURES}")

    missing = features.isna().sum()
    print("\n[특성별 결측치 수]")
    print(missing[missing > 0].to_string())
    print(f"타깃 결측치 수: {target.isna().sum()}")

    print("전처리 전략: 수치형은 중앙값 대치·표준화, 범주형은 One-Hot 인코딩")
    print("누수 방지: 전처리는 train/test 분리 후 Pipeline 내부에서 학습합니다.")


# STEP 5 - 컬럼 유형별 전처리기 구성
def build_preprocessor() -> ColumnTransformer:
    """수치형·범주형 컬럼에 서로 다른 전처리를 적용하는 변환기를 구성한다."""
    numeric_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    categorical_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore")),
        ]
    )

    return ColumnTransformer(
        transformers=[
            ("numeric", numeric_pipeline, NUMERIC_FEATURES),
            ("categorical", categorical_pipeline, CATEGORICAL_FEATURES),
        ],
        remainder="drop",
    )


def print_step5_result(preprocessor: ColumnTransformer) -> None:
    """ColumnTransformer에 등록된 전처리 단계와 미학습 상태를 출력한다."""
    print("\n-- STEP 5: ColumnTransformer 구성 --")
    print(preprocessor)
    print("현재 상태: 구성 완료, 아직 fit하지 않음")
    print("학습 시점: 다음 단계에서 train 데이터에 Pipeline 전체를 fit")


# STEP 6 - 계층적 train/test 분리 및 모델 Pipeline 학습
def train_churn_model(
    features: pd.DataFrame,
    target: pd.Series,
    preprocessor: ColumnTransformer,
) -> tuple[
    Pipeline,
    pd.DataFrame,
    pd.DataFrame,
    pd.Series,
    pd.Series,
    dict[str, int],
    float,
]:
    """데이터를 분리하고 train 교차검증으로 선택한 Pipeline을 학습한다."""
    x_train, x_test, y_train, y_test = train_test_split(
        features,
        target,
        test_size=0.2,
        random_state=42,
        stratify=target,
    )

    model_pipeline = Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            (
                "model",
                RandomForestClassifier(
                    n_estimators=200,
                    random_state=42,
                    n_jobs=-1,
                ),
            ),
        ]
    )
    cross_validation = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    parameter_grid = {
        "model__max_depth": [6, 8, 10],
        "model__min_samples_leaf": [5, 10, 20],
    }
    search = GridSearchCV(
        estimator=model_pipeline,
        param_grid=parameter_grid,
        scoring="roc_auc",
        cv=cross_validation,
        n_jobs=1,
        refit=True,
    )
    search.fit(x_train, y_train)

    return (
        search.best_estimator_,
        x_train,
        x_test,
        y_train,
        y_test,
        search.best_params_,
        float(search.best_score_),
    )


def print_step6_result(
    model_pipeline: Pipeline,
    x_train: pd.DataFrame,
    x_test: pd.DataFrame,
    y_train: pd.Series,
    y_test: pd.Series,
    best_params: dict[str, int],
    best_cv_auc: float,
) -> None:
    """분할 크기, 타깃 비율과 Pipeline 학습 완료 상태를 출력한다."""
    print("\n-- STEP 6: RandomForest Pipeline 학습 --")
    print(f"train 크기: {x_train.shape}, 이탈 비율: {y_train.mean():.2%}")
    print(f"test 크기: {x_test.shape}, 이탈 비율: {y_test.mean():.2%}")
    print(f"Pipeline 단계: {list(model_pipeline.named_steps)}")
    print(f"교차검증 최적 파라미터: {best_params}")
    print(f"train 5-fold 평균 ROC-AUC: {best_cv_auc:.3f}")
    print("학습 완료: 모델 선택과 전처리는 train 데이터 안에서만 수행했습니다.")


# STEP 7 - train OOF 확률을 이용한 분류 임계값 선택
def select_classification_threshold(
    model_pipeline: Pipeline,
    x_train: pd.DataFrame,
    y_train: pd.Series,
    target_recall: float = TARGET_RECALL,
) -> tuple[float, float, float]:
    """목표 재현율을 만족하는 가장 높은 train OOF 임계값을 선택한다."""
    cross_validation = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    oof_probabilities = cross_val_predict(
        clone(model_pipeline),
        x_train,
        y_train,
        cv=cross_validation,
        method="predict_proba",
        n_jobs=1,
    )[:, 1]
    precision, recall, thresholds = precision_recall_curve(
        y_train,
        oof_probabilities,
    )
    precision = precision[:-1]
    recall = recall[:-1]
    candidates = np.flatnonzero(recall >= target_recall)
    if candidates.size == 0:
        raise ValueError(
            f"목표 재현율 {target_recall:.2f}을 만족하는 임계값이 없습니다."
        )

    selected_index = candidates[np.argmax(thresholds[candidates])]
    return (
        float(thresholds[selected_index]),
        float(precision[selected_index]),
        float(recall[selected_index]),
    )


# STEP 7 - ROC-AUC 및 선택 임계값 기준 분류 평가
def evaluate_churn_model(
    model_pipeline: Pipeline,
    x_test: pd.DataFrame,
    y_test: pd.Series,
    threshold: float,
) -> tuple[float, str, np.ndarray]:
    """이탈 확률로 ROC-AUC를 계산하고 분류 리포트와 확률을 반환한다."""
    probabilities = model_pipeline.predict_proba(x_test)[:, 1]
    predictions = (probabilities >= threshold).astype(int)
    auc = roc_auc_score(y_test, probabilities)
    report = classification_report(
        y_test,
        predictions,
        target_names=["잔류", "이탈"],
        digits=3,
        zero_division=0,
    )
    return auc, report, probabilities


def save_and_verify_model(
    model_pipeline: Pipeline,
    x_test: pd.DataFrame,
    expected_probabilities: np.ndarray,
    threshold: float,
    output_path: Path,
) -> bool:
    """Pipeline과 임계값을 저장하고 재로딩 결과가 같은지 확인한다."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    model_bundle = {"pipeline": model_pipeline, "threshold": threshold}
    joblib.dump(model_bundle, output_path)
    loaded_bundle = joblib.load(output_path)
    loaded_probabilities = loaded_bundle["pipeline"].predict_proba(x_test)[:, 1]
    probabilities_match = np.allclose(expected_probabilities, loaded_probabilities)
    threshold_matches = loaded_bundle["threshold"] == threshold
    return bool(probabilities_match and threshold_matches)


def print_step7_result(
    auc: float,
    report: str,
    model_path: Path,
    roundtrip_verified: bool,
    threshold: float,
    oof_precision: float,
    oof_recall: float,
) -> None:
    """ROC-AUC, 분류 리포트와 모델 저장·재로딩 검증 결과를 출력한다."""
    print("\n-- STEP 7: 모델 평가 및 저장 --")
    print(f"ROC-AUC: {auc:.3f}")
    print(
        f"train OOF 선택 임계값: {threshold:.3f} "
        f"(정밀도={oof_precision:.3f}, 재현율={oof_recall:.3f})"
    )
    print("\n[분류 리포트]")
    print(report)
    print(f"모델 파일: {model_path}")
    print(f"파일 크기: {model_path.stat().st_size / 1024:,.1f} KB")
    print(f"재로딩 예측 일치: {'확인' if roundtrip_verified else '실패'}")


def main() -> None:
    """이탈 데이터를 불러와 단계별 EDA·통계·모델링을 실행한다."""
    try:
        df = load_churn_data(DATA_PATH)
    except FileNotFoundError:
        print(f"오류: 데이터 파일을 찾을 수 없습니다: {DATA_PATH}")
        print("프로젝트 최상위 폴더에서 python data/generate_data.py를 실행하세요.")
        return
    except (ValueError, pl.exceptions.PolarsError) as error:
        print(f"오류: 입력 데이터를 불러올 수 없습니다: {error}")
        return

    # STEP 0 실행
    churn_ratio = summarize_churn_ratio(df)
    print_step0_result(df, churn_ratio)

    # STEP 1 실행
    group_comparison = compare_churn_groups(df)
    print_step1_result(group_comparison)

    # STEP 2 실행
    try:
        chart_path = create_churn_boxplot(df, CHART_PATH)
    except (OSError, ValueError) as error:
        print(f"오류: Plotly HTML 리포트를 생성할 수 없습니다: {error}")
        return

    print_step2_result(chart_path)

    # STEP 3 실행
    try:
        statistical_results = run_statistical_tests(df)
    except ValueError as error:
        print(f"오류: 통계 검정을 실행할 수 없습니다: {error}")
        return

    print_step3_result(statistical_results)

    # STEP 4 실행
    try:
        features, target = prepare_model_data(df)
    except ValueError as error:
        print(f"오류: 모델 데이터를 준비할 수 없습니다: {error}")
        return

    print_step4_result(features, target)

    # STEP 5 실행
    preprocessor = build_preprocessor()
    print_step5_result(preprocessor)

    # STEP 6 실행
    try:
        (
            model_pipeline,
            x_train,
            x_test,
            y_train,
            y_test,
            best_params,
            best_cv_auc,
        ) = train_churn_model(
            features,
            target,
            preprocessor,
        )
    except ValueError as error:
        print(f"오류: 모델을 학습할 수 없습니다: {error}")
        return

    print_step6_result(
        model_pipeline,
        x_train,
        x_test,
        y_train,
        y_test,
        best_params,
        best_cv_auc,
    )

    # STEP 7 실행
    try:
        threshold, oof_precision, oof_recall = select_classification_threshold(
            model_pipeline,
            x_train,
            y_train,
        )
        auc, report, probabilities = evaluate_churn_model(
            model_pipeline,
            x_test,
            y_test,
            threshold,
        )
        roundtrip_verified = save_and_verify_model(
            model_pipeline,
            x_test,
            probabilities,
            threshold,
            MODEL_PATH,
        )
    except (OSError, ValueError) as error:
        print(f"오류: 모델을 평가하거나 저장할 수 없습니다: {error}")
        return

    print_step7_result(
        auc,
        report,
        MODEL_PATH,
        roundtrip_verified,
        threshold,
        oof_precision,
        oof_recall,
    )


if __name__ == "__main__":
    main()
