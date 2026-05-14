from __future__ import annotations

from typing import Any

from freqtrade.freqai.prediction_models.XGBoostClassifier import (
    XGBoostClassifier as BaseXGBoostClassifier,
)


class RebelXGBoostClassifier(BaseXGBoostClassifier):
    """
    Repo-local compatibility wrapper for freqai-rebel.

    Reason:
    The built-in XGBoostClassifier predict path can raise KeyError('labels_std')
    when dk.data does not contain label statistics during live/dry prediction.

    This wrapper does not change the strategy, features, targets, or trading logic.
    It only ensures the expected label-statistics key exists before delegating to
    the parent predict implementation.
    """

    def predict(self, unfiltered_df, dk, **kwargs: Any):
        if "labels_std" not in dk.data:
            class_names = getattr(self, "class_names", None)

            if not class_names:
                class_names = getattr(dk, "class_names", None)

            if not class_names:
                # fallback for freqai-rebel binary classifier target
                class_names = ["down", "up"]

            dk.data["labels_std"] = {str(label): 0.0 for label in class_names}

        return super().predict(unfiltered_df, dk, **kwargs)
