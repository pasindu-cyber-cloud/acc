"""Machine-learning classifier (Decision Tree + Random Forest).

ProcAI trains a supervised classifier that labels a process snapshot as normal
(0) or suspicious (1) from its behavioural feature vector. Two interpretable
algorithms are supported:

* **Decision Tree** -- maximally transparent; the path to a decision can be read.
* **Random Forest** -- more robust/accurate ensemble (default).

Design choices for safety & explainability:

* scikit-learn / numpy / joblib are imported lazily. If they are not installed,
  :func:`ml_available` returns ``False`` and the hybrid engine simply runs on
  rules + baseline. The product never hard-crashes for lack of ML.
* Models persist to the per-user models directory together with a metadata
  record (algorithm, sample/feature counts, validation metrics, feature names).
* ``predict`` returns calibrated-ish probabilities plus the most influential
  features so the GUI/assistant can explain *why* the model decided as it did.

Training data comes from local labelled samples the user curates, optionally
seeded with the synthetic dataset from :mod:`procai.core.simulation`. No data
ever leaves the machine.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from .features import FEATURE_NAMES, extract, to_vector
from .models import MLResult, ModelMetadata, ProcessSnapshot
from ..config import PATHS
from ..utils.logging_setup import get_logger

log = get_logger("core.ml")

try:  # pragma: no cover - only where the ML extra is installed
    import numpy as np
    import joblib
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.tree import DecisionTreeClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

    _HAVE_SKLEARN = True
except Exception:  # pragma: no cover
    _HAVE_SKLEARN = False


_ALGORITHMS = {"decision_tree", "random_forest"}


def ml_available() -> bool:
    return _HAVE_SKLEARN


class MLClassifier:
    """Wraps a single trained scikit-learn model plus its metadata."""

    def __init__(self, name: str = "random_forest") -> None:
        if name not in _ALGORITHMS:
            name = "random_forest"
        self.name = name
        self.model = None
        self.metadata: Optional[ModelMetadata] = None
        self.feature_names: tuple[str, ...] = FEATURE_NAMES

    # ------------------------------------------------------------------ #
    @property
    def model_path(self) -> Path:
        return PATHS.models_dir / f"{self.name}.joblib"

    def is_loaded(self) -> bool:
        return self.model is not None

    # ------------------------------------------------------------------ #
    def _new_estimator(self):
        if self.name == "decision_tree":
            return DecisionTreeClassifier(
                max_depth=8, min_samples_leaf=5, class_weight="balanced", random_state=42
            )
        return RandomForestClassifier(
            n_estimators=200, max_depth=12, min_samples_leaf=3,
            class_weight="balanced", n_jobs=-1, random_state=42,
        )

    # ------------------------------------------------------------------ #
    def train(
        self, samples: list[tuple[dict[str, float], int]], *, test_size: float = 0.25
    ) -> ModelMetadata:
        """Train on ``[(feature_dict, label), ...]`` and return metadata."""
        if not _HAVE_SKLEARN:
            raise RuntimeError("scikit-learn is not installed (pip install procai[ml]).")
        if len(samples) < 20:
            raise ValueError("Need at least 20 labelled samples to train a model.")

        X = np.array([to_vector(f) for f, _ in samples], dtype=float)
        y = np.array([int(lbl) for _, lbl in samples], dtype=int)

        if len(set(y.tolist())) < 2:
            raise ValueError("Training data must contain both normal and suspicious labels.")

        # Stratify so both classes appear in train/test even when imbalanced.
        X_tr, X_te, y_tr, y_te = train_test_split(
            X, y, test_size=test_size, random_state=42, stratify=y
        )
        model = self._new_estimator()
        model.fit(X_tr, y_tr)
        y_pred = model.predict(X_te)

        md = ModelMetadata(
            name=self.name,
            algorithm=type(model).__name__,
            trained_at=time.time(),
            n_samples=len(samples),
            n_features=len(FEATURE_NAMES),
            feature_names=list(FEATURE_NAMES),
            accuracy=float(accuracy_score(y_te, y_pred)),
            precision=float(precision_score(y_te, y_pred, zero_division=0)),
            recall=float(recall_score(y_te, y_pred, zero_division=0)),
            f1=float(f1_score(y_te, y_pred, zero_division=0)),
            notes=f"Trained on {len(samples)} samples; test split {test_size:.0%}.",
        )
        self.model = model
        self.metadata = md
        log.info(
            "Trained %s: acc=%.3f prec=%.3f rec=%.3f f1=%.3f",
            self.name, md.accuracy, md.precision, md.recall, md.f1,
        )
        return md

    # ------------------------------------------------------------------ #
    def save(self) -> Path:
        if not self.is_loaded():
            raise RuntimeError("No trained model to save.")
        PATHS.ensure()
        joblib.dump(
            {"model": self.model, "feature_names": list(self.feature_names),
             "metadata": self.metadata},
            self.model_path,
        )
        log.info("Saved model to %s", self.model_path)
        return self.model_path

    def load(self) -> bool:
        """Load the model from disk. Returns False if unavailable."""
        if not _HAVE_SKLEARN or not self.model_path.exists():
            return False
        try:
            blob = joblib.load(self.model_path)
            self.model = blob["model"]
            self.feature_names = tuple(blob.get("feature_names", FEATURE_NAMES))
            self.metadata = blob.get("metadata")
            log.info("Loaded model from %s", self.model_path)
            return True
        except Exception as exc:  # pragma: no cover
            log.warning("Failed to load model %s: %s", self.model_path, exc)
            return False

    # ------------------------------------------------------------------ #
    def predict(self, snap: ProcessSnapshot) -> MLResult:
        """Classify one snapshot. Returns an unavailable result if no model."""
        if not _HAVE_SKLEARN or not self.is_loaded():
            return MLResult(available=False, model_name=self.name)
        vec = np.array([to_vector(extract(snap))], dtype=float)
        try:
            proba = float(self.model.predict_proba(vec)[0][1])
        except Exception:
            pred = int(self.model.predict(vec)[0])
            proba = float(pred)
        confidence = abs(proba - 0.5) * 2.0
        top = self._explain(vec[0]) if proba >= 0.5 else self._explain(vec[0])
        return MLResult(
            available=True,
            model_name=self.name,
            is_suspicious=proba >= 0.5,
            probability=proba,
            confidence=confidence,
            top_features=top,
        )

    # ------------------------------------------------------------------ #
    def _explain(self, vector) -> list[tuple[str, float]]:
        """Return the top contributing features using model feature_importances_."""
        try:
            importances = getattr(self.model, "feature_importances_", None)
            if importances is None:
                return []
            pairs = list(zip(self.feature_names, (float(i) for i in importances)))
            pairs.sort(key=lambda kv: kv[1], reverse=True)
            return [(n, round(w, 4)) for n, w in pairs[:5] if w > 0]
        except Exception:
            return []


def train_and_save(
    name: str, samples: list[tuple[dict[str, float], int]]
) -> ModelMetadata:
    """Convenience: train, persist and return metadata for the named algorithm."""
    clf = MLClassifier(name)
    md = clf.train(samples)
    clf.save()
    return md
