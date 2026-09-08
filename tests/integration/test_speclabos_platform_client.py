"""SpecLabOS 平台客户端测试。"""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from threading import Thread

from smartaccess.runtime.adapters.speclabos_client import SpecLabOSPlatformClient


class CaptureHandler(BaseHTTPRequestHandler):
    """捕获 HTTP 请求的测试 handler。"""

    payloads: list[dict] = []

    def do_POST(self):  # noqa: N802
        """处理 POST 请求。"""
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        payload = json.loads(body.decode("utf-8"))
        self.__class__.payloads.append({"path": self.path, "payload": payload})
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True, **payload}).encode("utf-8"))

    def log_message(self, format, *args):  # noqa: A002
        """关闭测试 HTTP 日志。"""
        return None


class ListTemplatesHandler(BaseHTTPRequestHandler):
    """返回嵌套模板列表的测试 handler。"""

    paths: list[str] = []

    def do_GET(self):  # noqa: N802
        """处理 GET 请求。"""

        self.__class__.paths.append(self.path)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(
            json.dumps(
                {
                    "data": {
                        "items": [
                            {
                                "template_id": "tpl_weixin",
                                "template_version": "1.0.0",
                            }
                        ]
                    }
                }
            ).encode("utf-8")
        )

    def log_message(self, format, *args):  # noqa: A002
        """关闭测试 HTTP 日志。"""

        return None


def test_publish_template_posts_smartaccess_endpoint() -> None:
    """验证模板发布调用 SpecLabOS SmartAccess 模板接口。"""
    CaptureHandler.payloads = []
    server = HTTPServer(("127.0.0.1", 0), CaptureHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client = SpecLabOSPlatformClient(base_url=f"http://127.0.0.1:{server.server_port}")

    result = client.publish_template(
        {
            "template_id": "tpl_weixin",
            "template_version": "1.0.0",
            "anchor_profile": "weixin",
            "workflow": {
                "metadata": {"workflow_id": "wf_weixin"},
                "steps": [{"id": "open"}],
            },
        }
    )

    server.shutdown()
    sent_payload = CaptureHandler.payloads[-1]["payload"]
    assert result["ok"] is True
    assert CaptureHandler.payloads[-1]["path"] == "/api/smartaccess/templates/publish"
    assert sent_payload["workflow_id"] == "wf_weixin"
    assert sent_payload["name"] == "wf_weixin"
    assert sent_payload["anchor_profile"] == "weixin"
    assert sent_payload["source_device_id"] == "weixin"
    assert sent_payload["published_by"] == "smartaccess"


def test_list_templates_extracts_nested_items() -> None:
    """验证模板列表兼容 data.items 包装响应。"""

    ListTemplatesHandler.paths = []
    server = HTTPServer(("127.0.0.1", 0), ListTemplatesHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client = SpecLabOSPlatformClient(base_url=f"http://127.0.0.1:{server.server_port}")

    templates = client.list_templates(source_device_id="pc-xiaoxu")

    server.shutdown()
    assert ListTemplatesHandler.paths[-1].endswith(
        "/api/smartaccess/templates?source_device_id=pc-xiaoxu"
    )
    assert templates == [{"template_id": "tpl_weixin", "template_version": "1.0.0"}]
