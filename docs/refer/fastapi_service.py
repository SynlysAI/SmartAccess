import json
import logging
import socket
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from Tools.trigger_parser import handle_generate_instructions
from config import setup_logging

setup_logging(logger_name="fastapi_service")
logger = logging.getLogger("fastapi_service")


class UdpClientError(RuntimeError):
    pass


class TriggerGenerateRequest(BaseModel):
    experiment_plan: str = Field(..., min_length=1, description="实验方案文本")
    request_id: Optional[str] = Field(default=None, description="可选的外部请求ID")


class ExecuteRequest(BaseModel):
    request_id: Optional[str] = Field(default=None, description="可选的外部请求ID")


class ApiResponse(BaseModel):
    ok: bool
    message: str
    request_id: str
    signal: str
    udp_ack: Any
    timestamp: str
    instructions: Optional[list[str]] = None


class StatusResponse(BaseModel):
    ok: bool
    request_id: Optional[str]
    status: str
    detail: str
    current_command: str
    last_plan_updated_at: Optional[str]
    last_triggered_at: Optional[str]
    generated_at: str


@dataclass
class RequestTrackingState:
    last_plan: Optional[str] = None
    last_trigger_request_id: Optional[str] = None
    last_triggered_at: Optional[datetime] = None
    generation_in_progress: bool = False
    generation_completed_at: Optional[datetime] = None
    generation_error: Optional[str] = None
    lock: threading.Lock = field(default_factory=threading.Lock)

    def trigger(self, experiment_plan: str, request_id: str) -> tuple[bool, str]:
        with self.lock:
            if self.generation_in_progress:
                return False, "上一轮指令解析任务仍在执行中"

            self.last_plan = experiment_plan
            self.last_trigger_request_id = request_id
            self.last_triggered_at = _utcnow()
            self.generation_in_progress = True
            self.generation_completed_at = None
            self.generation_error = None
            return True, ""

    def mark_generation_done(self, error: Optional[str] = None) -> None:
        with self.lock:
            self.generation_in_progress = False
            self.generation_completed_at = _utcnow()
            self.generation_error = error

    def is_ready_to_execute(self) -> tuple[bool, str]:
        with self.lock:
            if self.last_plan is None:
                return False, "请先调用 /api/v1/experiment/trigger 接口"
            if self.last_triggered_at is None:
                return False, "请先调用 /api/v1/experiment/trigger 接口"
            if self.generation_in_progress:
                return False, "指令解析仍在执行中"
            if self.generation_completed_at is None:
                return False, "指令解析尚未完成"
            if self.generation_error:
                return False, f"指令解析失败: {self.generation_error}"
            return True, ""

    def snapshot(self) -> dict[str, Optional[str]]:
        with self.lock:
            last_triggered_iso = self.last_triggered_at.isoformat() if self.last_triggered_at else None
            return {
                "request_id": self.last_trigger_request_id,
                "last_plan_updated_at": last_triggered_iso,
                "last_triggered_at": last_triggered_iso,
            }



def _utcnow() -> datetime:
    return datetime.utcnow()


def send_udp_signal_and_wait(
    signal: str,
    payload: Optional[str] = None,
    use_json: bool = False,
    host: str = "127.0.0.1",
    port: int = 8889,
    timeout_s: float = 6.0,
) -> dict[str, Any]:
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_socket.settimeout(timeout_s)

    try:
        if use_json:
            message: dict[str, Any] = {"signal": signal}
            if payload is not None:
                message["payload"] = payload
            send_data = json.dumps(message, ensure_ascii=False)
        else:
            send_data = signal if payload is None else f"{signal}|{payload}"

        udp_socket.sendto(send_data.encode("utf-8"), (host, int(port)))

        response_raw, source = udp_socket.recvfrom(4096)
        response_text = response_raw.decode("utf-8", errors="replace").strip()

        try:
            response_payload: Any = json.loads(response_text)
        except json.JSONDecodeError:
            response_payload = response_text

        return {
            "ok": True,
            "signal": signal,
            "request": send_data,
            "response": response_payload,
            "response_text": response_text,
            "source": {"host": source[0], "port": source[1]},
        }
    except socket.timeout as exc:
        raise UdpClientError(f"UDP ACK timeout for signal={signal}") from exc
    except OSError as exc:
        raise UdpClientError(f"UDP send failed for signal={signal}: {exc}") from exc
    finally:
        udp_socket.close()


udp_host = "127.0.0.1"
udp_port = 8889
udp_timeout_s = 6.0
state = RequestTrackingState()

app = FastAPI(
    title="SmartCmd External API",
    version="0.1.0",
    description="实验触发、执行与状态查询接口",
)


def _parse_execution_state_response(response: Any) -> tuple[str, str, str]:
    if not isinstance(response, dict):
        raise UdpClientError("GET_PROCESS_EXECUTION_STATE 返回了非 JSON 响应")

    if response.get("status") != "success":
        message = str(response.get("message") or response)
        raise UdpClientError(f"GET_PROCESS_EXECUTION_STATE 失败: {message}")

    if response.get("command") != "GET_PROCESS_EXECUTION_STATE":
        raise UdpClientError(
            f"GET_PROCESS_EXECUTION_STATE 的 command 字段异常: {response.get('command')}"
        )

    executing = response.get("executing")
    if not isinstance(executing, bool):
        raise UdpClientError("GET_PROCESS_EXECUTION_STATE 的 `executing` 字段无效")

    if executing:
        process_name = str(response.get("process_name", ""))
        current_step = int(response.get("current_step", 0))
        total_steps = int(response.get("total_steps", 0))
        current_command = str(response.get("current_command", ""))
        detail = (
            f"process={process_name or '<unknown>'}, step={current_step}/{total_steps}, "
            f"current_command={current_command or '<unknown>'}, executing=True"
        )
        return "running", detail, current_command

    return "success", "当前没有流程在执行（executing=False）", ""


def _run_generation_task(experiment_plan: str, request_id: str) -> None:
    try:
        handle_generate_instructions(experiment_plan)
    except Exception as exc:
        logger.exception("本地指令解析任务失败（request_id=%s）", request_id)
        state.mark_generation_done(error=str(exc))
        return

    state.mark_generation_done()
    logger.info("本地指令解析任务完成（request_id=%s）", request_id)


@app.get("/health")
def health_check() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "smartcmd-fastapi",
        "udp_target": {"host": udp_host, "port": udp_port},
        "timestamp": _utcnow().isoformat(),
    }


@app.post("/api/v1/experiment/trigger", response_model=ApiResponse)
def trigger_generate(request: TriggerGenerateRequest) -> ApiResponse:
    request_id = request.request_id or str(uuid.uuid4())

    accepted, reason = state.trigger(request.experiment_plan, request_id)
    if not accepted:
        raise HTTPException(status_code=409, detail=reason)

    try:
        raw_content = handle_generate_instructions(request.experiment_plan)
        instructions = [line.strip() for line in raw_content.splitlines() if line.strip().startswith("S ")]
    except Exception as exc:
        logger.exception("本地指令解析任务失败（request_id=%s）", request_id)
        state.mark_generation_done(error=str(exc))
        raise HTTPException(status_code=500, detail=f"指令解析失败: {exc}") from exc

    state.mark_generation_done()
    logger.info("本地指令解析任务完成（request_id=%s）", request_id)

    return ApiResponse(
        ok=True,
        message="本地指令解析任务已完成。",
        request_id=request_id,
        signal="TRIGGER_GENERATE_LOCAL",
        udp_ack=None,
        timestamp=_utcnow().isoformat(),
        instructions=instructions,
    )


@app.post("/api/v1/experiment/execute", response_model=ApiResponse)
def execute_process(request: Optional[ExecuteRequest] = None) -> ApiResponse:
    request_id = (request.request_id if request else None) or str(uuid.uuid4())

    ready, reason = state.is_ready_to_execute()
    if not ready:
        raise HTTPException(status_code=409, detail=reason)

    try:
        result = send_udp_signal_and_wait(
            signal="EXECUTE_PROCESS_FILE",
            payload=None,
            use_json=False,
            host=udp_host,
            port=udp_port,
            timeout_s=udp_timeout_s,
        )
    except UdpClientError as exc:
        logger.exception("EXECUTE_PROCESS_FILE 调用失败")
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ApiResponse(
        ok=True,
        message="工艺流程执行命令已下发，请通过 /api/v1/experiment/status 查询进度。",
        request_id=request_id,
        signal="EXECUTE_PROCESS_FILE",
        udp_ack=result["response"],
        timestamp=_utcnow().isoformat(),
    )


@app.get("/api/v1/experiment/status", response_model=StatusResponse)
def get_experiment_status() -> StatusResponse:
    try:
        result = send_udp_signal_and_wait(
            signal="GET_PROCESS_EXECUTION_STATE",
            payload=None,
            use_json=False,
            host=udp_host,
            port=udp_port,
            timeout_s=udp_timeout_s,
        )
        status, detail, current_command = _parse_execution_state_response(result["response"])
    except UdpClientError as exc:
        logger.exception("GET_PROCESS_EXECUTION_STATE 调用失败")
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    snapshot = state.snapshot()
    return StatusResponse(
        ok=True,
        request_id=snapshot["request_id"],
        status=status,
        detail=detail,
        current_command=current_command,
        last_plan_updated_at=snapshot["last_plan_updated_at"],
        last_triggered_at=snapshot["last_triggered_at"],
        generated_at=_utcnow().isoformat(),
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "fastapi_service:app",
        host="0.0.0.0",
        port=7000,
        reload=False,
    )
