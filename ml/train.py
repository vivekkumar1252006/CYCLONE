"""Train and persist the vulnerability model.

Usage (from repo root):
    python -m ml.train                      # RandomForest (default)
    python -m ml.train --backend xgboost    # requires `pip install xgboost`
"""
from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.metrics import accuracy_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import train_test_split

from .features import FEATURES
from .synthetic_training import generate_training_data
from .vulnerability_model import VulnerabilityModel, make_model

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_PATH = REPO_ROOT / "models" / "vulnerability_model.joblib"


def train(backend: str = "random_forest", n_samples: int = 12000, seed: int = 7,
          out_path: Path = DEFAULT_MODEL_PATH) -> VulnerabilityModel:
    t0 = time.time()
    df = generate_training_data(n=n_samples, seed=seed)
    X, y = df[FEATURES], df["damaged"].to_numpy()
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=seed, stratify=y)
    model = make_model(backend)
    model.fit(X_tr, y_tr)
    p = model.predict_proba(X_te)
    model.metrics = {
        "roc_auc": round(float(roc_auc_score(y_te, p)), 4),
        "brier": round(float(brier_score_loss(y_te, p)), 4),
        "accuracy@0.5": round(float(accuracy_score(y_te, (p >= 0.5).astype(int))), 4),
        "positive_rate": round(float(np.mean(y)), 4),
        "n_train": int(len(X_tr)),
        "n_test": int(len(X_te)),
        "training_data": "SYNTHETIC fragility-curve process (see ml/synthetic_training.py)",
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "train_seconds": round(time.time() - t0, 2),
    }
    model.save(out_path)
    return model


def load_or_train(path: Path = DEFAULT_MODEL_PATH, backend: str = "random_forest") -> VulnerabilityModel:
    if path.exists():
        try:
            return VulnerabilityModel.load(path)
        except Exception:  # corrupted / incompatible artifact -> retrain
            pass
    return train(backend=backend, out_path=path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--backend", default="random_forest", choices=["random_forest", "xgboost"])
    ap.add_argument("--samples", type=int, default=12000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", type=Path, default=DEFAULT_MODEL_PATH)
    a = ap.parse_args()
    m = train(a.backend, a.samples, a.seed, a.out)
    print(f"Trained {m.name} -> {a.out}")
    for k, v in m.metrics.items():
        print(f"  {k}: {v}")
