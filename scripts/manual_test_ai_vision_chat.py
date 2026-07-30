"""手动测试 Agnes Chat Completions 图片识别接口。

默认请求 `https://apihub.agnes-ai.com/v1/chat/completions`，使用
OpenAI 兼容的 `messages[].content` 图片格式发送一张图片。
"""

from __future__ import annotations

import base64
import json
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API_BASE_URL = "http://10.26.15.52:30081/ccb44b4cfe18439f8affd07babd0810e/v1"
API_MODEL = "Qwen3.6-35B-A3B"
API_KEY = "sk-6mOM3wbHEoMQRnVzaW9uc22tAt6iUlMG"
IMAGE_PATH = r"C:\Users\www59\Pictures\多模态材料表征数据库概览.png"
PROMPT = (
    "一句话总结这个图片"
)
TIMEOUT_SECONDS = 120.0
ENABLE_THINKING = False
MAX_TOKENS = 1000
TEMPERATURE = 0.7
TOP_P = 0.80
TOP_K = 20
MIN_P = 0.0
PRESENCE_PENALTY = 1.5
REPETITION_PENALTY = 1.0


def build_demo_image_base64() -> tuple[str, str]:
    """生成一张用于 OCR 联通测试的小图片。

    Returns:
        MIME 类型和 base64 图片内容。
    """

    from PIL import Image, ImageDraw

    image = Image.new("RGB", (360, 120), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((12, 12, 348, 108), outline="black", width=2)
    draw.text((32, 42), "SmartAccess 42", fill="black")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return "image/png", base64.b64encode(buffer.getvalue()).decode("ascii")


def encode_image_file(image_path: Path) -> tuple[str, str]:
    """读取本地图片并编码为 base64。

    Args:
        image_path: 本地图片路径。

    Returns:
        MIME 类型和 base64 图片内容。
    """

    suffix = image_path.suffix.lower()
    mime_type = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(suffix, "image/png")
    return mime_type, base64.b64encode(image_path.read_bytes()).decode("ascii")


def build_chat_payload(model: str, prompt: str, mime_type: str, image_b64: str) -> dict:
    """构建 OpenAI 兼容 Chat 图片请求体。

    Args:
        model: 模型名称。
        prompt: 图片识别提示词。
        mime_type: 图片 MIME 类型。
        image_b64: base64 图片内容。

    Returns:
        可直接 JSON 序列化的请求体。
    """

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{image_b64}",
                        },
                    },
                ],
            }
        ],
        "temperature": TEMPERATURE,
        "top_p": TOP_P,
        "top_k": TOP_K,
        "min_p": MIN_P,
        "presence_penalty": PRESENCE_PENALTY,
        "repetition_penalty": REPETITION_PENALTY,
        "max_tokens": MAX_TOKENS,
    }
    if not ENABLE_THINKING:
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    return payload


def post_chat_completion(
    *,
    endpoint: str,
    api_key: str,
    payload: dict,
    timeout_seconds: float,
) -> tuple[int, str]:
    """发送 Chat Completions 请求。

    Args:
        endpoint: Chat Completions 完整地址。
        api_key: API Key。
        payload: 请求体。
        timeout_seconds: 超时时间。

    Returns:
        HTTP 状态码和响应文本。
    """

    request = Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
        return response.status, response.read().decode("utf-8", errors="replace")


def main() -> int:
    """执行手动图片识别接口测试。

    Returns:
        进程退出码。
    """

    base_url = API_BASE_URL
    model = API_MODEL
    api_key = API_KEY
    if not api_key or api_key == "请在这里填写你的 API Key":
        print("缺少 API Key：请先修改脚本顶部的 API_KEY")
        return 2

    if IMAGE_PATH:
        mime_type, image_b64 = encode_image_file(Path(IMAGE_PATH))
    else:
        mime_type, image_b64 = build_demo_image_base64()

    endpoint = f"{base_url.rstrip('/')}/chat/completions"
    payload = build_chat_payload(model, PROMPT, mime_type, image_b64)

    print("endpoint =", endpoint)
    print("model =", model)
    print("image_mime =", mime_type)
    print("image_path =", IMAGE_PATH or "<demo image>")
    print("prompt =", PROMPT)
    try:
        status, text = post_chat_completion(
            endpoint=endpoint,
            api_key=api_key,
            payload=payload,
            timeout_seconds=TIMEOUT_SECONDS,
        )
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print("result = failed")
        print("status =", exc.code)
        print("error =", detail[:2000])
        return 1
    except URLError as exc:
        print("result = failed")
        print("error_type =", type(exc.reason).__name__)
        print("error =", str(exc.reason)[:2000])
        return 1
    except TimeoutError as exc:
        print("result = failed")
        print("error_type =", type(exc).__name__)
        print("error =", str(exc))
        return 1

    print("result = success")
    print("status =", status)
    print("raw =", text[:2000])
    try:
        data = json.loads(text)
        choice = data["choices"][0]
        print("finish_reason =", choice.get("finish_reason"))
        content = choice["message"].get("content", "")
        print("content =", content)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        print("parse_error =", type(exc).__name__, str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
