"""Wake word detection using openWakeWord."""

import logging

import numpy as np
from openwakeword.model import Model as OWWModel

import voice.config as cfg

log = logging.getLogger(__name__)


class WakeWordDetector:
    """Thin wrapper around openWakeWord that processes int16 audio frames."""

    def __init__(
        self,
        model_name: str = cfg.WAKE_WORD,
        threshold: float = cfg.WAKE_THRESHOLD,
    ):
        self.model_name = model_name
        self.threshold = threshold
        self._model: OWWModel | None = None

    def load(self) -> None:
        log.info(
            "Loading wake-word model %r  threshold=%.2f",
            self.model_name,
            self.threshold,
        )
        import openwakeword

        openwakeword.utils.download_models()
        self._model = OWWModel(wakeword_models=[self.model_name])
        log.info("Wake-word model ready")

    def process(self, frame: np.ndarray) -> bool:
        """Feed an int16 audio frame and return True if the wake word fired.

        ``frame`` should contain ``cfg.FRAME_SAMPLES`` samples at 16 kHz.
        """
        if self._model is None:
            raise RuntimeError("Call load() before process()")

        self._model.predict(frame)

        for mdl_name in self._model.prediction_buffer:
            scores = self._model.prediction_buffer[mdl_name]
            if scores and scores[-1] >= self.threshold:
                log.info(
                    "Wake word detected  model=%s  score=%.3f",
                    mdl_name,
                    scores[-1],
                )
                self._model.reset()
                return True
        return False

    def reset(self) -> None:
        if self._model is not None:
            self._model.reset()
