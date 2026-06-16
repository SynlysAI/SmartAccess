"""基于远程 API 的视觉/OCR 提供者。

通过 HTTP API 进行文档布局分析和 OCR 文本识别，无需本地 OCR 模型依赖。

依赖: requests, Pillow (用于 ROI 裁剪)
"""

from __future__ import annotations

import base64
from pathlib import Path
from io import BytesIO
from typing import Any

from smartaccess.runtime.application.ports import OcrReading
from smartaccess.shared.contracts.anchors import AnchorDefinition, PixelRegion


# --------------------------------------------------------------------------- #
# Optional dependency helpers
# --------------------------------------------------------------------------- #
_PIL_AVAILABLE = False
_Image: Any = None

try:
    from PIL import Image as _PILImage
    _Image = _PILImage
    _PIL_AVAILABLE = True
except ImportError:
    pass


def _require_pil() -> None:
    """检查 Pillow 是否可用。"""
    if not _PIL_AVAILABLE:
        raise RuntimeError(
            "ApiVisionProvider 需要 Pillow。请运行: pip install Pillow"
        )


# --------------------------------------------------------------------------- #
# Provider
# --------------------------------------------------------------------------- #
class ApiVisionProvider:
    """基于远程 OCR API 的视觉提供者。

    使用外部文档布局分析 API 进行文本识别。
    由于 API 不支持模板匹配和颜色检测，这些功能将返回 unsupported 结果。
    """

    def __init__(
        self,
        *,
        api_url: str,
        workspace_dir: Path | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        """初始化 API 视觉提供者。

        Args:
            api_url: OCR API 基础地址 (例: http://100.84.59.58:8090)。
            workspace_dir: 工作区目录。
            timeout_seconds: API 请求超时秒数。
        """
        _require_pil()

        self._api_url = api_url.rstrip("/")
        self._workspace_dir = workspace_dir
        self._timeout = timeout_seconds
        self._screenshot: bytes | None = None
        self._profile_anchors: dict[str, AnchorDefinition] = {}
        self._window_signature = None
        self._http = __import__("requests")

    # -- configuration ----------------------------------------------------- #
    def configure_screenshot(self, data: bytes | None) -> None:
        """缓存最新截图供后续 OCR 使用。

        Args:
            data: PNG 截图字节。
        """
        self._screenshot = data

    def configure_profile(self, profile: Any | None) -> None:
        """从设备配置中索引锚点。

        Args:
            profile: 锚点配置对象。
        """
        self._profile_anchors.clear()
        self._window_signature = getattr(profile, "window_signature", None)
        if profile is None:
            return
        for anchor in getattr(profile, "anchors", []) or []:
            self._profile_anchors[anchor.id] = anchor

    # -- VisionProvider protocol ------------------------------------------- #
    def read_text(self, roi: str) -> OcrReading:
        """通过 API 对当前截图进行 OCR 文本识别。

        Args:
            roi: ROI 名称。

        Returns:
            OCR 读取结果。
        """
        if self._screenshot is None:
            return OcrReading(
                roi=roi, text="", confidence=0.0, detail="no screenshot cached"
            )

        img_bytes = self._screenshot
        anchor = self._profile_anchors.get(roi)
        if anchor is not None:
            cropped = self._crop_to_anchor_roi(img_bytes, anchor)
            if cropped is not None:
                img_bytes = cropped

        return self._api_ocr(img_bytes, roi)

    def read_roi_text(
        self,
        *,
        screenshot: bytes | None,
        anchor: AnchorDefinition,
        roi: PixelRegion | None = None,
    ) -> OcrReading:
        """通过 API 对指定锚点 ROI 进行 OCR。

        Args:
            screenshot: 当前窗口截图 PNG 字节。
            anchor: 锚点定义。
            roi: 可选覆盖 ROI。

        Returns:
            OCR 读取结果。
        """
        img_bytes = screenshot or self._screenshot
        if img_bytes is None:
            return OcrReading(
                roi=anchor.id, text="", confidence=0.0, detail="no image available"
            )

        if roi is not None:
            cropped = self._crop_pixel_roi(img_bytes, roi)
            if cropped is not None:
                img_bytes = cropped
        else:
            cropped = self._crop_to_anchor_roi(img_bytes, anchor)
            if cropped is not None:
                img_bytes = cropped

        return self._api_ocr(img_bytes, anchor.id)

    def capture_anchor_image(
        self,
        *,
        screenshot: bytes | None,
        anchor: AnchorDefinition,
        roi: PixelRegion | None = None,
    ) -> bytes | None:
        """裁剪并编码锚点观察区域截图。

        Args:
            screenshot: 当前窗口截图 PNG 字节。
            anchor: 锚点定义。
            roi: 可选覆盖 ROI。

        Returns:
            观察区域 PNG 字节；无法裁剪时返回 None。
        """
        _require_pil()
        img_bytes = screenshot or self._screenshot
        if img_bytes is None:
            return None
        if roi is not None:
            return self._crop_pixel_roi(img_bytes, roi)
        return self._crop_to_anchor_roi(img_bytes, anchor)

    def detect_presence(self, roi: str) -> bool:
        """通过 API 检测 ROI 是否存在文本内容。

        Args:
            roi: ROI 名称。

        Returns:
            是否存在可识别内容。
        """
        reading = self.read_text(roi)
        return bool(reading.text.strip())

    def match_template(self, roi: str) -> OcrReading:
        """模板匹配 - API 不支持。

        Args:
            roi: ROI 名称。

        Returns:
            unsupported 结果。
        """
        return OcrReading(
            roi=roi,
            text="unsupported",
            confidence=0.0,
            detail="match_template not supported by API vision provider",
        )

    def sample_color(self, roi: str) -> OcrReading:
        """颜色采样 - 通过 Pillow 本地分析 ROI 颜色。

        Args:
            roi: ROI 名称。

        Returns:
            颜色采样结果。
        """
        _require_pil()
        if self._screenshot is None:
            return OcrReading(
                roi=roi, text="unknown", confidence=0.0, detail="no screenshot cached"
            )

        anchor = self._profile_anchors.get(roi)
        if anchor is None:
            return OcrReading(
                roi=roi, text="unknown", confidence=0.0, detail="anchor not found"
            )

        cropped_bytes = self._crop_to_anchor_roi(self._screenshot, anchor)
        if cropped_bytes is None:
            return OcrReading(
                roi=roi, text="unknown", confidence=0.0, detail="ROI crop failed"
            )

        img = _Image.open(BytesIO(cropped_bytes))
        # 计算平均颜色
        pixels = list(img.getdata())
        if not pixels:
            return OcrReading(
                roi=roi, text="unknown", confidence=0.0, detail="empty ROI"
            )

        r = sum(p[0] for p in pixels) / len(pixels)
        g = sum(p[1] for p in pixels) / len(pixels)
        b = sum(p[2] for p in pixels) / len(pixels)
        hex_color = f"#{int(r):02x}{int(g):02x}{int(b):02x}"

        return OcrReading(
            roi=roi,
            text=hex_color,
            confidence=1.0,
            detail=f"sampled RGB=({int(r)},{int(g)},{int(b)})",
        )

    # -- helpers ----------------------------------------------------------- #
    def _api_ocr(self, img_bytes: bytes, label: str) -> OcrReading:
        """调用远程 OCR API 并解析结果。

        Args:
            img_bytes: PNG 图像字节。
            label: 结果标签。

        Returns:
            OCR 读取结果。
        """
        image_b64 = base64.b64encode(img_bytes).decode("ascii")
        payload = {
            "file": image_b64,
            "fileType": 1,
            "visualize": False,
            "useDocOrientationClassify": False,
            "useDocUnwarping": False,
            "useLayoutDetection": False,
            "useChartRecognition": False,
            "useSealRecognition": False,
            "useOcrForImageBlock": False,
            "prettifyMarkdown": False,
        }

        try:
            resp = self._http.post(
                f"{self._api_url}/layout-parsing",
                json=payload,
                timeout=self._timeout,
            )
            resp.raise_for_status()
            result = resp.json()["result"]
        except Exception as exc:
            return OcrReading(
                roi=label, text="", confidence=0.0, detail=f"API error: {exc}"
            )

        parsing_results = result.get("layoutParsingResults", [])
        if not parsing_results:
            return OcrReading(
                roi=label, text="", confidence=0.0, detail="no layout results"
            )

        parsed = parsing_results[0]
        pruned = parsed.get("prunedResult", {})
        blocks = pruned.get("parsing_res_list", [])

        if not blocks:
            return OcrReading(
                roi=label, text="", confidence=0.0, detail="no text blocks detected"
            )

        texts: list[str] = []
        for block in blocks:
            content = (block.get("block_content") or "").strip()
            if content:
                texts.append(content)

        combined = " ".join(texts)

        # 从 layout_det_res 提取布局检测置信度
        box_scores = self._extract_box_scores(pruned)
        avg_score = float(sum(box_scores) / len(box_scores)) if box_scores else 0.9

        return OcrReading(
            roi=label,
            text=combined,
            confidence=avg_score,
            detail="api_ocr",
        )

    @staticmethod
    def _extract_box_scores(pruned: dict) -> list[float]:
        """从 layout_det_res 中提取检测框置信度。

        /layout-parsing 返回 dict 格式，/restructure-pages 返回 list 格式，
        这里兼容两种结构。

        Args:
            pruned: prunedResult 字典。

        Returns:
            所有检测框的 score 列表。
        """
        layout = pruned.get("layout_det_res", {})
        if layout is None:
            return []
        if isinstance(layout, list):
            entries = layout
        elif isinstance(layout, dict):
            entries = [layout]
        else:
            return []
        scores: list[float] = []
        for entry in entries:
            boxes = entry.get("boxes") or []
            for box in boxes:
                score = box.get("score")
                if score is not None:
                    scores.append(float(score))
        return scores

    def _crop_to_anchor_roi(
        self, img_bytes: bytes, anchor: AnchorDefinition
    ) -> bytes | None:
        """按锚点观察区域裁剪图像。

        Args:
            img_bytes: PNG 图像字节。
            anchor: 锚点定义。

        Returns:
            裁剪后的 PNG 字节；无法裁剪时返回 None。
        """
        observe = getattr(anchor, "observe_region", None)
        if observe is None:
            return None
        return self._crop_pixel_roi(img_bytes, observe.pixel)

    @staticmethod
    def _crop_pixel_roi(img_bytes: bytes, roi: PixelRegion) -> bytes | None:
        """按像素坐标裁剪图像。

        Args:
            img_bytes: PNG 图像字节。
            roi: 像素区域。

        Returns:
            裁剪后的 PNG 字节；无法裁剪时返回 None。
        """
        _require_pil()
        img = _Image.open(BytesIO(img_bytes))
        x1 = max(0, int(roi.x))
        y1 = max(0, int(roi.y))
        x2 = min(img.width, int(roi.x + roi.width))
        y2 = min(img.height, int(roi.y + roi.height))
        if x2 <= x1 or y2 <= y1:
            return None

        cropped = img.crop((x1, y1, x2, y2))
        buf = BytesIO()
        cropped.save(buf, format="PNG")
        return buf.getvalue()
