from __future__ import annotations

import numpy as np
import pytest

from smartaccess.runtime.adapters import local_vision as local_vision_module


class _ModernResult:
    def __init__(self, payload: dict) -> None:
        self.json = payload


def test_local_vision_uses_device_init_for_modern_paddleocr(monkeypatch) -> None:
    calls: dict[str, object] = {}

    class FakeModernPaddleOCR:
        def __init__(
            self,
            lang=None,
            use_doc_orientation_classify=None,
            use_doc_unwarping=None,
            use_textline_orientation=None,
            **kwargs,
        ) -> None:
            calls["lang"] = lang
            calls["kwargs"] = kwargs
            calls["use_doc_orientation_classify"] = use_doc_orientation_classify
            calls["use_doc_unwarping"] = use_doc_unwarping
            calls["use_textline_orientation"] = use_textline_orientation

        def predict(self, img):
            return [
                _ModernResult(
                    {"res": {"rec_texts": ["Alice", "Bob"], "rec_scores": [0.9, 0.7]}}
                )
            ]

    monkeypatch.setattr(local_vision_module, "_CV2_AVAILABLE", True)
    monkeypatch.setattr(local_vision_module, "_PADDLE_AVAILABLE", True)
    monkeypatch.setattr(local_vision_module, "_PaddleOCR", FakeModernPaddleOCR)

    provider = local_vision_module.LocalVisionProvider(ocr_use_gpu=False)
    reading = provider._ocr_image(np.zeros((8, 8, 3), dtype=np.uint8), "roi_modern")

    assert calls["lang"] == "ch"
    assert calls["kwargs"] == {"device": "cpu", "enable_mkldnn": False}
    assert calls["use_doc_orientation_classify"] is False
    assert calls["use_doc_unwarping"] is False
    assert calls["use_textline_orientation"] is False
    assert reading.text == "Alice Bob"
    assert reading.confidence == pytest.approx(0.8)


def test_local_vision_keeps_legacy_use_gpu_path(monkeypatch) -> None:
    calls: dict[str, object] = {}

    class FakeLegacyPaddleOCR:
        def __init__(self, lang=None, use_gpu=False) -> None:
            calls["lang"] = lang
            calls["use_gpu"] = use_gpu

        def ocr(self, img, cls=False):
            calls["cls"] = cls
            return [[(None, ("Carol", 0.9)), (None, ("Delta", 0.5))]]

    monkeypatch.setattr(local_vision_module, "_CV2_AVAILABLE", True)
    monkeypatch.setattr(local_vision_module, "_PADDLE_AVAILABLE", True)
    monkeypatch.setattr(local_vision_module, "_PaddleOCR", FakeLegacyPaddleOCR)

    provider = local_vision_module.LocalVisionProvider(ocr_use_gpu=True)
    reading = provider._ocr_image(np.zeros((8, 8, 3), dtype=np.uint8), "roi_legacy")

    assert calls["lang"] == "ch"
    assert calls["use_gpu"] is True
    assert calls["cls"] is False
    assert reading.text == "Carol Delta"
    assert reading.confidence == pytest.approx(0.7)
