from __future__ import annotations

from typing import Any

from freqtrade.freqai.prediction_models.XGBoostClassifier import (
    XGBoostClassifier as BaseXGBoostClassifier,
)


class RebelXGBoostClassifier(BaseXGBoostClassifier):
    """
    Repo-local wrapper for freqai-rebel.

    Fixes:
    - labels_std fallback for prediction path
    """

    def predict(self, unfiltered_df, dk, **kwargs: Any):
        # Original labels_std fix
        if "labels_std" not in dk.data:
            class_names = getattr(self, "class_names", None)
            if not class_names:
                class_names = getattr(dk, "class_names", None)
            if not class_names:
                class_names = ["down", "up"]
            dk.data["labels_std"] = {str(label): 0.0 for label in class_names}

        return super().predict(unfiltered_df, dk, **kwargs)
