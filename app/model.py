"""Model loading, stable feature engineering and strict request validation."""

from functools import lru_cache
from pathlib import Path
import math

import joblib
import pandas as pd

RAW_FEATURES = (["LIMIT_BAL"] + [f"PAY_{i}" for i in (0, 2, 3, 4, 5, 6)]
                + [f"BILL_AMT{i}" for i in range(1, 7)]
                + [f"PAY_AMT{i}" for i in range(1, 7)])
DERIVED = ["BILL_TO_LIMIT_1", "MAX_DELAY_6", "PAYMENT_SUM_TO_LIMIT_6"]
FEATURES = RAW_FEATURES + DERIVED


def validate_record(record: object) -> dict[str, float]:
    if not isinstance(record, dict):
        raise ValueError("Expected a JSON object containing 19 financial features")
    missing = sorted(set(RAW_FEATURES) - set(record))
    extra = sorted(set(record) - set(RAW_FEATURES))
    if missing or extra:
        raise ValueError(f"Missing fields: {missing}; unexpected fields: {extra}")
    cleaned = {}
    for field in RAW_FEATURES:
        value = record[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{field} must be a finite number")
        cleaned[field] = float(value)
    if cleaned["LIMIT_BAL"] <= 0:
        raise ValueError("LIMIT_BAL must be greater than zero")
    for field in RAW_FEATURES:
        if field.startswith("PAY_AMT") and cleaned[field] < 0:
            raise ValueError(f"{field} cannot be negative")
    return cleaned


def feature_frame(records: list[dict[str, float]]) -> pd.DataFrame:
    frame = pd.DataFrame(records, columns=RAW_FEATURES)
    limit = frame["LIMIT_BAL"].clip(lower=1)
    frame["BILL_TO_LIMIT_1"] = frame["BILL_AMT1"] / limit
    frame["MAX_DELAY_6"] = frame[["PAY_0", "PAY_2", "PAY_3", "PAY_4", "PAY_5", "PAY_6"]].clip(lower=0).max(axis=1)
    frame["PAYMENT_SUM_TO_LIMIT_6"] = frame[[f"PAY_AMT{i}" for i in range(1, 7)]].sum(axis=1) / limit
    return frame[FEATURES]


@lru_cache(maxsize=2)
def load_bundle(path: str):
    bundle = joblib.load(Path(path).resolve())
    if bundle.get("raw_features") != RAW_FEATURES or bundle.get("feature_names") != FEATURES:
        raise RuntimeError("Model feature schema does not match this application")
    return bundle


def predict_many(records: list[object], model_path: str) -> tuple[list[float], str]:
    cleaned = [validate_record(r) for r in records]
    if not cleaned:
        raise ValueError("At least one record is required")
    bundle = load_bundle(model_path)
    scores = bundle["model"].predict_proba(feature_frame(cleaned))[:, 1]
    return [float(p) for p in scores], str(bundle["version"])
