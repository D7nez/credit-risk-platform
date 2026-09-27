"""Operational summaries, score drift, and outcome-based quality."""

from collections import Counter
import math

import numpy as np
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score


def psi(reference, current, bins=10):
    ref, now = np.asarray(reference, float), np.asarray(current, float)
    edges = np.unique(np.quantile(ref, np.linspace(0, 1, bins + 1)))
    if len(edges) < 2:
        return None
    edges[0], edges[-1] = -np.inf, np.inf
    a = np.maximum(np.histogram(ref, bins=edges)[0] / len(ref), 1e-6)
    b = np.maximum(np.histogram(now, bins=edges)[0] / len(now), 1e-6)
    return float(np.sum((b-a)*np.log(b/a)))


def summarize(rows, reference_scores, days: int):
    scores = [float(r["score"]) for r in rows]
    labeled = [r for r in rows if r["outcome"] is not None]
    daily = Counter(r["created_at"][:10] for r in rows)
    histogram = np.histogram(scores, bins=np.linspace(0,1,11))[0].tolist() if scores else [0]*10
    drift = {"status": "insufficient_data", "psi": None, "minimum_scores": 100}
    if len(scores) >= 100:
        drift = {"status": "available", "psi": psi(reference_scores, scores),
                 "minimum_scores": 100}
    performance = {"status": "awaiting_outcomes", "minimum_labeled": 30,
                   "labeled": len(labeled)}
    if len(labeled) >= 30 and len({r["outcome"] for r in labeled}) == 2:
        y = np.array([r["outcome"] for r in labeled], dtype=int)
        p = np.array([r["score"] for r in labeled], dtype=float)
        top = np.argsort(-p)[:max(1, math.ceil(len(p)*0.2))]
        performance = {"status": "available", "labeled": len(labeled),
                       "minimum_labeled": 30, "default_rate": float(y.mean()),
                       "pr_auc": float(average_precision_score(y,p)),
                       "roc_auc": float(roc_auc_score(y,p)),
                       "brier": float(brier_score_loss(y,p)),
                       "top20_capture": float(y[top].sum()/y.sum())}
    return {
        "window_days": days, "predictions": len(rows), "labeled": len(labeled),
        "mean_score": float(np.mean(scores)) if scores else None,
        "daily_counts": [{"date":k,"count":v} for k,v in sorted(daily.items())],
        "score_histogram": histogram, "drift": drift, "performance": performance,
        "interpretation": "PSI measures score distribution shift, not business impact. Outcome metrics require representative labels."
    }
