"""Real vision provider using PaddleOCR and OpenCV.

Implements the :class:`VisionProvider` protocol with local libraries:
- **OCR**: PaddleOCR for text recognition from ROI regions.
- **Template matching**: OpenCV ``matchTemplate`` for visual pattern matching.
- **Color detection**: HSV distance between ROI mean and a reference hex color.
- **Presence detection**: Non-background pixel ratio threshold.

All dependencies are optional imports — a clear RuntimeError is raised at
construction time when a required library is missing, so the bootstrap layer
can fail fast instead of silently falling back to stubs.
"""

from __future__ import annotations

import io
import inspect
from pathlib import Path
from typing import Any

import numpy as np

from smartaccess.runtime.application.ports import OcrReading
from smartaccess.runtime.application.roi_resolver import resolve_anchor_roi
from smartaccess.shared.contracts.instrument_profile import AnchorDefinition, RoiRect, VisionConfig

# --------------------------------------------------------------------------- #
# Optional dependency helpers
# --------------------------------------------------------------------------- #
_CV2_AVAILABLE = False
_PADDLE_AVAILABLE = False
_cv2: Any = None
_PaddleOCR: Any = None

try:
    import cv2 as _cv2_mod

    _cv2 = _cv2_mod
    _CV2_AVAILABLE = True
except ImportError:
    pass

try:
    from paddleocr import PaddleOCR as _PaddleOCRCls

    _PaddleOCR = _PaddleOCRCls
    _PADDLE_AVAILABLE = True
except ImportError:
    pass


def _require_cv2() -> None:
    if not _CV2_AVAILABLE:
        raise RuntimeError(
            "LocalVisionProvider 需要 opencv-python。请运行: pip install opencv-python"
        )


def _require_paddle() -> None:
    if not _PADDLE_AVAILABLE:
        raise RuntimeError(
            "LocalVisionProvider 需要 PaddleOCR。请运行: pip install paddlepaddle paddleocr"
        )


# --------------------------------------------------------------------------- #
# Provider
# --------------------------------------------------------------------------- #
class LocalVisionProvider:
    """Real vision provider backed by PaddleOCR + OpenCV."""

    def __init__(
        self,
        *,
        ocr_lang: str = "ch",
        ocr_use_gpu: bool = False,
        workspace_dir: Path | None = None,
    ) -> None:
        _require_cv2()
        self._workspace_dir = workspace_dir
        self._screenshot: np.ndarray | None = None
        self._profile_anchors: dict[str, AnchorDefinition] = {}
        self._window_signature = None

        # Lazy-init PaddleOCR — it's heavy to load
        self._ocr_lang = ocr_lang
        self._ocr_use_gpu = ocr_use_gpu
        self._ocr: Any = None
        self._ocr_api = "legacy"

    # -- configuration ----------------------------------------------------- #
    def configure_screenshot(self, data: bytes | np.ndarray | None) -> None:
        """Cache the latest screenshot so ROI cropping doesn't need a re-read."""
        if data is None:
            self._screenshot = None
            return
        if isinstance(data, bytes):
            arr = np.frombuffer(data, np.uint8)
            self._screenshot = _cv2.imdecode(arr, _cv2.IMREAD_COLOR)
        elif isinstance(data, np.ndarray):
            self._screenshot = data

    def configure_profile(self, profile: Any | None) -> None:
        """Index anchors from an instrument profile for vision_config lookup."""
        self._profile_anchors.clear()
        self._window_signature = getattr(profile, "window_signature", None)
        if profile is None:
            return
        for anchor in getattr(profile, "anchors", []) or []:
            self._profile_anchors[anchor.id] = anchor

    # -- VisionProvider protocol ------------------------------------------- #
    def read_text(self, roi: str) -> OcrReading:
        """OCR the entire current screenshot or a named ROI."""
        _require_paddle()
        img = self._screenshot
        if img is None:
            return OcrReading(roi=roi, text="", confidence=0.0, detail="no screenshot cached")
        if roi in self._profile_anchors:
            anchor = self._profile_anchors[roi]
            cropped = self._crop_roi(img, self._resolved_roi(anchor, img))
            if cropped is not None:
                img = cropped
        return self._ocr_image(img, roi)

    def read_roi_text(
        self,
        *,
        screenshot: bytes | None,
        anchor: AnchorDefinition,
        roi: RoiRect | None = None,
    ) -> OcrReading:
        """OCR a specific anchor's ROI region."""
        _require_paddle()
        if screenshot is not None:
            arr = np.frombuffer(screenshot, np.uint8)
            img = _cv2.imdecode(arr, _cv2.IMREAD_COLOR)
        elif self._screenshot is not None:
            img = self._screenshot
        else:
            return OcrReading(roi=anchor.id, text="", confidence=0.0, detail="no image available")
        target_roi = roi or self._resolved_roi(anchor, img)
        cropped = self._crop_roi(img, target_roi)
        if cropped is not None:
            img = cropped
        return self._ocr_image(img, anchor.id)

    def detect_presence(self, roi: str) -> bool:
        """Check whether a UI element is present via non-background pixel ratio."""
        _require_cv2()
        img = self._screenshot
        if img is None:
            return False
        cropped = self._crop_roi_for_name(img, roi)
        if cropped is None:
            return False
        gray = _cv2.cvtColor(cropped, _cv2.COLOR_BGR2GRAY)
        # Heuristic: pixels significantly different from the mean are "foreground"
        mean_val = float(np.mean(gray))
        foreground = np.sum(np.abs(gray.astype(np.float32) - mean_val) > 30)
        total = gray.size
        cfg = self._vision_config(roi)
        threshold = cfg.presence_threshold if cfg else 0.05
        return (foreground / max(total, 1)) > threshold

    def match_template(self, roi: str) -> OcrReading:
        """Match a cached screenshot region against a stored template image."""
        _require_cv2()
        img = self._screenshot
        if img is None:
            return OcrReading(roi=roi, text="no_match", confidence=0.0, detail="no screenshot cached")

        cfg = self._vision_config(roi)
        if cfg is None or not cfg.template_asset_path:
            return OcrReading(
                roi=roi, text="no_template", confidence=0.0,
                detail="vision_config.template_asset_path not set"
            )

        template_path = Path(cfg.template_asset_path)
        if self._workspace_dir and not template_path.is_absolute():
            template_path = self._workspace_dir / template_path
        if not template_path.exists():
            return OcrReading(
                roi=roi, text="missing_template", confidence=0.0,
                detail=f"template file not found: {template_path}"
            )

        template = _cv2.imread(str(template_path), _cv2.IMREAD_COLOR)
        if template is None:
            return OcrReading(
                roi=roi, text="bad_template", confidence=0.0,
                detail="failed to load template image"
            )

        cropped = self._crop_roi_for_name(img, roi)
        search_area = cropped if cropped is not None else img

        # Template must be smaller than or equal to search area
        th, tw = template.shape[:2]
        sh, sw = search_area.shape[:2]
        if th > sh or tw > sw:
            template = _cv2.resize(template, (min(tw, sw), min(th, sh)))
            th, tw = template.shape[:2]

        result = _cv2.matchTemplate(search_area, template, _cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = _cv2.minMaxLoc(result)
        threshold = cfg.template_threshold
        matched = max_val >= threshold
        return OcrReading(
            roi=roi,
            text="matched" if matched else "no_match",
            confidence=float(max_val),
            detail=f"template={template_path.name} score={max_val:.3f} threshold={threshold}",
        )

    def sample_color(self, roi: str) -> OcrReading:
        """Compute the dominant color of a ROI and compare to a reference."""
        _require_cv2()
        img = self._screenshot
        if img is None:
            return OcrReading(roi=roi, text="unknown", confidence=0.0, detail="no screenshot cached")

        cfg = self._vision_config(roi)
        cropped = self._crop_roi_for_name(img, roi)
        if cropped is None:
            return OcrReading(roi=roi, text="unknown", confidence=0.0, detail="ROI not found")

        # Mean color in BGR
        mean_bgr = np.mean(cropped, axis=(0, 1))
        if cfg and cfg.color_reference_hex:
            ref_bgr = _hex_to_bgr(cfg.color_reference_hex)
            # HSV distance
            mean_hsv = _bgr_to_hsv(mean_bgr)
            ref_hsv = _bgr_to_hsv(ref_bgr)
            h_dist = min(abs(mean_hsv[0] - ref_hsv[0]), 180 - abs(mean_hsv[0] - ref_hsv[0])) / 180.0
            sv_dist = np.linalg.norm(mean_hsv[1:] - ref_hsv[1:]) / 255.0
            distance = float(h_dist * 0.5 + sv_dist * 0.5)
            tolerance = cfg.color_tolerance
            matched = distance <= tolerance
            detail = (
                f"mean_bgr=({mean_bgr[2]:.0f},{mean_bgr[1]:.0f},{mean_bgr[0]:.0f}) "
                f"ref={cfg.color_reference_hex} distance={distance:.3f} tolerance={tolerance}"
            )
            return OcrReading(
                roi=roi,
                text="matched" if matched else "no_match",
                confidence=float(1.0 - min(distance, 1.0)),
                detail=detail,
            )

        # No reference → just report the color
        hex_color = f"#{mean_bgr[2]:02x}{mean_bgr[1]:02x}{mean_bgr[0]:02x}"
        return OcrReading(
            roi=roi,
            text=hex_color,
            confidence=1.0,
            detail=f"sampled BGR=({mean_bgr[2]:.0f},{mean_bgr[1]:.0f},{mean_bgr[0]:.0f})",
        )

    # -- helpers ----------------------------------------------------------- #
    def _ocr_image(self, img: np.ndarray, label: str) -> OcrReading:
        if self._ocr is None:
            self._ocr = self._build_ocr()
        try:
            results = self._run_ocr(img)
        except Exception as exc:
            return OcrReading(roi=label, text="", confidence=0.0, detail=f"OCR error: {exc}")
        texts, confs = self._extract_ocr_lines(results)
        if not texts:
            return OcrReading(roi=label, text="", confidence=0.0, detail="no text detected")
        combined = " ".join(texts)
        avg_conf = float(np.mean(confs)) if confs else 0.0
        return OcrReading(roi=label, text=combined, confidence=avg_conf, detail="paddleocr")

    def _build_ocr(self) -> Any:
        init_params = inspect.signature(_PaddleOCR.__init__).parameters
        kwargs: dict[str, Any] = {"lang": self._ocr_lang}
        for option in (
            "use_doc_orientation_classify",
            "use_doc_unwarping",
            "use_textline_orientation",
        ):
            if option in init_params:
                kwargs[option] = False
        if "enable_mkldnn" in init_params or any(param.kind == inspect.Parameter.VAR_KEYWORD for param in init_params.values()):
            kwargs["enable_mkldnn"] = False
        if "use_gpu" in init_params:
            kwargs["use_gpu"] = self._ocr_use_gpu
            self._ocr_api = "legacy"
        else:
            kwargs["device"] = "gpu" if self._ocr_use_gpu else "cpu"
            self._ocr_api = "predict"
        return _PaddleOCR(**kwargs)

    def _run_ocr(self, img: np.ndarray) -> Any:
        attempts: list[tuple[str, Any]] = []
        if self._ocr_api == "predict":
            if hasattr(self._ocr, "predict"):
                attempts.append(("predict(img)", lambda: self._ocr.predict(img)))
            if hasattr(self._ocr, "ocr"):
                attempts.append(("ocr(img)", lambda: self._ocr.ocr(img)))
                attempts.append(("ocr(img, cls=False)", lambda: self._ocr.ocr(img, cls=False)))
        else:
            if hasattr(self._ocr, "ocr"):
                attempts.append(("ocr(img, cls=False)", lambda: self._ocr.ocr(img, cls=False)))
                attempts.append(("ocr(img)", lambda: self._ocr.ocr(img)))
            if hasattr(self._ocr, "predict"):
                attempts.append(("predict(img)", lambda: self._ocr.predict(img)))

        errors: list[str] = []
        for label, attempt in attempts:
            try:
                return attempt()
            except TypeError as exc:
                errors.append(f"{label}: {exc}")
                continue
        if errors:
            raise TypeError("; ".join(errors))
        raise RuntimeError("No OCR inference entrypoint available on PaddleOCR instance")

    @staticmethod
    def _extract_ocr_lines(results: Any) -> tuple[list[str], list[float]]:
        texts: list[str] = []
        confs: list[float] = []
        if not results:
            return texts, confs

        # PaddleOCR 2.x: [[box, [text, score]], ...]
        if isinstance(results, list) and results and isinstance(results[0], list):
            legacy_lines = results[0]
            if legacy_lines and isinstance(legacy_lines[0], (list, tuple)):
                for line in legacy_lines:
                    if len(line) <= 1:
                        continue
                    pair = line[1]
                    if not isinstance(pair, (list, tuple)) or not pair:
                        continue
                    text = str(pair[0]) if pair[0] is not None else ""
                    conf = float(pair[1]) if len(pair) > 1 else 0.0
                    if text:
                        texts.append(text)
                        confs.append(conf)
                if texts:
                    return texts, confs

        iterable = results if isinstance(results, list) else [results]
        for item in iterable:
            payload = LocalVisionProvider._result_payload(item)
            if not payload:
                continue
            res = payload.get("res", payload) if isinstance(payload, dict) else {}
            if not isinstance(res, dict):
                continue
            line_texts = LocalVisionProvider._as_list(res.get("rec_texts"))
            line_scores = LocalVisionProvider._as_list(res.get("rec_scores"))
            if line_texts:
                for index, text in enumerate(line_texts):
                    text_str = str(text or "").strip()
                    if not text_str:
                        continue
                    texts.append(text_str)
                    score = line_scores[index] if index < len(line_scores) else 0.0
                    confs.append(float(score))
                continue
            single_text = res.get("rec_text") or res.get("text")
            if single_text:
                texts.append(str(single_text))
                confs.append(float(res.get("rec_score", res.get("score", 0.0))))
        return texts, confs

    @staticmethod
    def _result_payload(item: Any) -> dict[str, Any]:
        if isinstance(item, dict):
            return item
        payload = getattr(item, "json", None)
        if callable(payload):
            payload = payload()
        if isinstance(payload, dict):
            return payload
        to_dict = getattr(item, "to_dict", None)
        if callable(to_dict):
            payload = to_dict()
            if isinstance(payload, dict):
                return payload
        model_dump = getattr(item, "model_dump", None)
        if callable(model_dump):
            payload = model_dump()
            if isinstance(payload, dict):
                return payload
        raw = getattr(item, "__dict__", None)
        return raw if isinstance(raw, dict) else {}

    @staticmethod
    def _as_list(value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        tolist = getattr(value, "tolist", None)
        if callable(tolist):
            converted = tolist()
            if isinstance(converted, list):
                return converted
            if isinstance(converted, tuple):
                return list(converted)
            return [converted]
        return [value]

    def _crop_roi_for_name(self, img: np.ndarray, roi_name: str) -> np.ndarray | None:
        """Look up an anchor by name and crop its ROI from the image."""
        anchor = self._profile_anchors.get(roi_name)
        if anchor is None:
            return None
        return self._crop_roi(img, self._resolved_roi(anchor, img))

    @staticmethod
    def _crop_roi(img: np.ndarray, roi: RoiRect | None) -> np.ndarray | None:
        if roi is None:
            return None
        h, w = img.shape[:2]
        x1 = max(0, int(roi.x))
        y1 = max(0, int(roi.y))
        x2 = min(w, int(roi.x + roi.width))
        y2 = min(h, int(roi.y + roi.height))
        if x2 <= x1 or y2 <= y1:
            return None
        return img[y1:y2, x1:x2]

    def _vision_config(self, roi: str) -> VisionConfig | None:
        anchor = self._profile_anchors.get(roi)
        if anchor is None:
            return None
        return anchor.vision_config

    def _resolved_roi(self, anchor: AnchorDefinition, img: np.ndarray) -> RoiRect | None:
        height, width = img.shape[:2]
        return resolve_anchor_roi(
            anchor,
            self._window_signature,
            current_width=width,
            current_height=height,
        )


# --------------------------------------------------------------------------- #
# Color utility helpers
# --------------------------------------------------------------------------- #
def _hex_to_bgr(hex_color: str) -> np.ndarray:
    """Convert '#RRGGBB' to a BGR numpy array (OpenCV format)."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return np.array([b, g, r], dtype=np.float32)


def _bgr_to_hsv(bgr: np.ndarray) -> np.ndarray:
    """Convert a single BGR pixel to HSV using OpenCV."""
    pixel = bgr.reshape(1, 1, 3).astype(np.uint8)
    hsv = _cv2.cvtColor(pixel, _cv2.COLOR_BGR2HSV)
    return hsv[0, 0].astype(np.float32)
