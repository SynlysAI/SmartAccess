"""单独执行设备接入页的 AI 辅助接入流程。

脚本复用项目 `.env` 中的多模态 AI 配置，构造与桌面端
“AI辅助接入”按钮相同的上下文，生成锚点草稿并保存到文件。
"""

from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
os.chdir(REPO_ROOT)


DEVICE_ID = "ccswich-1-1-1"
TITLE_CONTAINS = "CC Switch"
WINDOW_TITLE = "CC Switch"
SCREENSHOT_PATH = REPO_ROOT / "workspace" / "anchors" / "ccswich-1-1-1" / "capture.png"
PROMPT = (
    "请只识别截图中蓝色圆角按钮“导入当前配置”的锚点。"
    "返回一个可点击按钮锚点，锚点 id 使用 import_current_config_button。"
    "action_region 必须覆盖蓝色按钮本体的完整可点击区域，"
    "不要框到按钮下方的白色输入框、空白区域或其它控件；observe_region 为空。"
    "不要生成其它按钮、输入框或状态区域。"
)
ANNOTATED_IMAGE_PATH = REPO_ROOT / "workspace" / "ai_assist_drafts" / "last_ai_assist_annotated.png"


def load_screenshot_context(image_path: Path) -> dict[str, str] | None:
    """读取截图并构建 AI 多模态上下文。

    Args:
        image_path: 截图文件路径。

    Returns:
        包含 MIME 类型和 base64 数据的上下文字典；路径为空或不存在时返回 None。
    """

    if not image_path or not image_path.exists():
        return None
    suffix = image_path.suffix.lower()
    mime_type = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(suffix, "image/png")
    return {
        "mime_type": mime_type,
        "data": base64.b64encode(image_path.read_bytes()).decode("ascii"),
    }


def image_size(image_path: Path) -> tuple[int, int]:
    """读取截图宽高。

    Args:
        image_path: 截图文件路径。

    Returns:
        图片宽度和高度。
    """

    with Image.open(image_path) as image:
        return image.size


def build_context() -> dict[str, Any]:
    """构建设备接入 AI 生成上下文。

    Returns:
        与桌面端 AI 辅助接入按钮一致的上下文字典。
    """

    capture_width, capture_height = image_size(Path(SCREENSHOT_PATH))
    context: dict[str, Any] = {
        "device_id": DEVICE_ID,
        "title_contains": TITLE_CONTAINS,
        "window_title": WINDOW_TITLE,
        "capture_width": capture_width,
        "capture_height": capture_height,
    }
    screenshot = load_screenshot_context(Path(SCREENSHOT_PATH))
    if screenshot is not None:
        context["screenshot"] = screenshot
    return context


def anchor_pixel_region(anchor: Any) -> tuple[int, int, int, int] | None:
    """读取锚点动作区域像素框。

    Args:
        anchor: 锚点契约对象。

    Returns:
        左上角 x/y 和宽高；缺失时返回 None。
    """

    region = getattr(anchor, "action_region", None)
    pixel = getattr(region, "pixel", None)
    if pixel is None:
        return None
    return int(pixel.x), int(pixel.y), int(pixel.width), int(pixel.height)


def iter_profile_anchors(profile: Any) -> list[Any]:
    """返回 AI 识别出的锚点列表。

    Args:
        profile: AI 返回的锚点契约对象。

    Returns:
        锚点对象列表。
    """

    anchors = list(getattr(profile, "anchors", []) or [])
    if anchors:
        return anchors
    result: list[Any] = []
    for view in getattr(profile, "views", []) or []:
        result.extend(list(getattr(view, "anchors", []) or []))
    return result


def draw_annotated_image(image_path: Path, anchors: list[Any]) -> Path:
    """绘制锚点识别框。

    Args:
        image_path: 原始截图路径。
        anchors: 锚点列表。

    Returns:
        标注图路径。
    """

    ANNOTATED_IMAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(image_path).convert("RGB") as image:
        draw = ImageDraw.Draw(image)
        for anchor in anchors:
            box = anchor_pixel_region(anchor)
            if box is None:
                continue
            x, y, width, height = box
            anchor_id = str(getattr(anchor, "id", "anchor"))
            draw.rectangle((x, y, x + width, y + height), outline="red", width=4)
            label = f"{anchor_id} ({x},{y},{width},{height})"
            text_box = draw.textbbox((x, y), label)
            text_height = text_box[3] - text_box[1]
            label_y = max(0, y - text_height - 6)
            label_box = draw.textbbox((x, label_y), label)
            draw.rectangle(label_box, fill="red")
            draw.text((x, label_y), label, fill="white")
        image.save(ANNOTATED_IMAGE_PATH)
    return ANNOTATED_IMAGE_PATH


def main() -> int:
    """执行 AI 辅助接入并输出结果。"""

    from smartaccess.bootstrap.runtime import build_runtime_facade
    from smartaccess.shared.config.settings import AppSettings

    settings = AppSettings.from_env()
    facade = build_runtime_facade(settings)
    context = build_context()

    print("截图 =", SCREENSHOT_PATH)
    print("尺寸 =", f"{context['capture_width']}x{context['capture_height']}")
    print("提示词 =", PROMPT)

    profile = facade.draft_instrument_from_prompt(PROMPT, context)
    anchors = iter_profile_anchors(profile)
    annotated_path = draw_annotated_image(Path(SCREENSHOT_PATH), anchors)

    print("识别结果 =")
    for anchor in anchors:
        box = anchor_pixel_region(anchor)
        print(
            json.dumps(
                {
                    "id": getattr(anchor, "id", ""),
                    "action_region": box,
                    "supported_actions": getattr(anchor, "supported_actions", []),
                    "observe_region": getattr(anchor, "observe_region", None) is not None,
                },
                ensure_ascii=False,
            )
        )
    print("标注图 =", annotated_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
