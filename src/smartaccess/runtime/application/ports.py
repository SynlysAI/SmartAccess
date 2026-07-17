"""应用层与外部适配器之间的端口协议。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from smartaccess.shared.contracts.anchors import AnchorDefinition, PixelRegion
from smartaccess.shared.contracts.workflow import WorkflowContract


@dataclass(slots=True)
class GenerationResult:
    """实验计划生成结果。"""

    instructions: list[str]


@dataclass(slots=True)
class ProcessExecutionState:
    """下游过程主机的执行状态。"""

    status: str
    detail: str
    current_command: str


@dataclass(slots=True)
class WindowInfo:
    """发现到的目标软件窗口。"""

    title: str
    width: int = 0
    height: int = 0
    matched: bool = True
    hwnd: int | None = None


@dataclass(slots=True)
class OcrReading:
    """一次 OCR 或视觉读取结果。"""

    roi: str
    text: str
    confidence: float
    source_path: str | None = None
    detail: str = ""


@dataclass(slots=True)
class ActionOutcome:
    """自动化动作执行结果。"""

    ok: bool
    detail: str = ""
    screenshot_path: str | None = None


@dataclass(slots=True)
class Screenshot:
    """PNG 截图字节及尺寸。"""

    data: bytes
    width: int = 0
    height: int = 0


class InstructionGenerator(Protocol):
    """把实验计划转换成本地执行指令。"""

    def generate(self, experiment_plan: str) -> GenerationResult:
        """生成执行指令。

        Args:
            experiment_plan: 实验计划文本。

        Returns:
            指令生成结果。
        """


class ProcessExecutorClient(Protocol):
    """驱动下游过程主机的客户端协议。"""

    def execute_process(self) -> Any:
        """执行下游过程。"""

    def read_execution_state(self) -> ProcessExecutionState:
        """读取下游过程状态。"""


class AutomationProvider(Protocol):
    """目标软件 UI 自动化提供者协议。"""

    def window_present(self, title_contains: str | None) -> bool:
        """判断目标窗口是否存在。"""

    def discover_windows(self) -> list[WindowInfo]:
        """扫描可接入窗口。"""

    def locate_anchor(self, anchor_id: str) -> bool:
        """判断锚点是否可定位。"""

    def configure_profile(self, profile: Any | None) -> None:
        """配置当前锚点配置。"""

    def run_action(
        self,
        action: str,
        target: str | None,
        value: Any | None,
    ) -> ActionOutcome:
        """执行一个 UI 动作。"""

    def screenshot(self, label: str) -> bytes:
        """截取当前窗口或桌面图像。"""

    def capture_window(self, hwnd: int) -> bytes | None:
        """按窗口句柄截图。"""

    def capture_windows(self, hwnds: list[int]) -> bytes | None:
        """按多个窗口的屏幕联合区域截图。"""


class VisionProvider(Protocol):
    """截图视觉识别提供者协议。"""

    def read_text(self, roi: str) -> OcrReading:
        """读取指定 ROI 文本。"""

    def read_roi_text(
        self,
        *,
        screenshot: bytes | None,
        anchor: AnchorDefinition,
        roi: PixelRegion | None = None,
    ) -> OcrReading:
        """读取指定锚点 ROI 文本。"""

    def detect_presence(self, roi: str) -> bool:
        """检测指定 ROI 是否存在目标。"""

    def match_template(self, roi: str) -> OcrReading:
        """执行模板匹配。"""

    def sample_color(self, roi: str) -> OcrReading:
        """采样指定 ROI 颜色。"""


class PlatformClient(Protocol):
    """SpecLabOS 平台客户端协议。"""

    def health(self) -> bool:
        """检查平台是否可用。"""

    def fetch_task(self) -> dict[str, Any] | None:
        """拉取待执行任务。"""

    def fetch_template(
        self,
        template_id: str,
        template_version: str,
    ) -> dict[str, Any]:
        """拉取指定模板版本。"""

    def list_templates(
        self,
        *,
        device_id: str | None = None,
        source_device_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """列出云端模板。"""

    def publish_template(self, payload: dict[str, Any]) -> dict[str, Any]:
        """发布模板。"""

    def delete_template(self, template_id: str, template_version: str) -> bool:
        """删除模板版本。"""

    def upload_status(self, payload: dict[str, Any]) -> bool:
        """上传运行状态。"""

    def upload_logs(self, payload: dict[str, Any]) -> bool:
        """上传运行日志。"""

    def upload_run_event(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """上传 SmartAccess 运行事件。

        Args:
            run_id: SpecLabOS 运行 ID。
            payload: 事件载荷。

        Returns:
            平台响应。
        """

    def upload_results(self, payload: dict[str, Any]) -> bool:
        """上传运行结果。"""

    def report_heartbeat(self, payload: dict[str, Any]) -> bool:
        """上报执行端心跳,通知平台本节点在线。"""

    def register_node(self, payload: dict[str, Any]) -> dict[str, Any]:
        """注册并校验执行端节点身份。"""


class ArtifactStore(Protocol):
    """运行产物存储协议。"""

    def save_screenshot(self, session_id: str, name: str, data: bytes) -> str:
        """保存截图。"""

    def save_text(self, session_id: str, name: str, text: str) -> str:
        """保存文本。"""

    def append_jsonl(self, session_id: str, name: str, line: str) -> str:
        """追加 JSONL 行。"""


class WorkflowDraftGenerator(Protocol):
    """自然语言工作流草稿生成器协议。"""

    def draft_from_prompt(self, prompt: str, context: dict[str, Any]) -> Any:
        """生成工作流草稿。"""


class InstrumentProfileDraftGenerator(Protocol):
    """仪器锚点配置草稿生成器协议。"""

    def draft_from_prompt(self, prompt: str, context: dict[str, Any]) -> Any:
        """生成仪器锚点配置草稿。"""


class TemplateVersionMissing(Exception):
    """请求的模板版本不存在。"""

    def __init__(self, template_id: str, template_version: str) -> None:
        """初始化异常。

        Args:
            template_id: 模板 ID。
            template_version: 模板版本。
        """

        self.template_id = template_id
        self.template_version = template_version
        super().__init__(f"模板版本不存在: {template_id}@{template_version}")


class PlatformOffline(Exception):
    """平台不可达异常。"""

    def __init__(self, detail: str = "platform offline") -> None:
        """初始化异常。

        Args:
            detail: 异常详情。
        """

        self.detail = detail
        super().__init__(detail)


@dataclass(slots=True)
class WorkflowListEntry:
    """工作流列表 UI 投影。"""

    workflow: WorkflowContract
    source_kind: str
    storage_ref: str
    display_label: str


@dataclass(slots=True)
class InstrumentReferenceInfo:
    """删除仪器前的引用检查结果。"""

    device_id: str
    draft_count: int = 0
    local_template_count: int = 0
    active_session_count: int = 0
    referencing_workflow_ids: list[str] | None = None
    referencing_template_ids: list[str] | None = None
