import joblib
import numpy as np
from django.conf import settings

# ── Load models once at import time ───────────────────────────────────────────
# These globals are populated the first time this module is imported.
# If the pkl files are missing, an error is raised immediately at startup
# (which is what we want — fail fast rather than on the first student login).

_scaler = None
_model  = None

def _load_models():
    """
    Lazy-load scaler and model on first call.
    Raises FileNotFoundError if the .pkl paths in .env are wrong.
    """
    global _scaler, _model
    if _scaler is None or _model is None:
        _scaler = joblib.load(settings.SCALER_PATH)
        _model  = joblib.load(settings.SVM_PATH)

# Label mapping from SVM integer output to human-readable status
_LABEL_MAP = {0: 'Stable', 1: 'Challenged', 2: 'Critical'}

def predict(answers: list) -> str:
    """
    Classify a student's mental health status from their 26 answers.

    Args:
        answers: A list of exactly 26 integers in the feature order
                 PSS1-PSS10, GAD1-GAD7, PHQ1-PHQ9.
                 PSS values must be 0-4; GAD/PHQ values must be 0-3.

    Returns:
        One of: "Stable" | "Challenged" | "Critical"

    Raises:
        ValueError  : if answers does not contain exactly 26 values.
        RuntimeError: if the model files cannot be loaded.
    """
    if len(answers) != 26:
        raise ValueError(
            f'predict() expects exactly 26 answers, got {len(answers)}.'
        )

    _load_models()

    features = np.array(answers, dtype=float).reshape(1, -1)
    scaled   = _scaler.transform(features)
    raw      = _model.predict(scaled)[0]

    return _LABEL_MAP.get(int(raw), 'Stable')