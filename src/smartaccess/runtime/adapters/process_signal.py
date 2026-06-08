"""UDP adapter that drives the downstream process host.

Ports the request/ACK UDP protocol from the reference FastAPI service behind
the :class:`ProcessExecutorClient` port. Failures are normalized to
:class:`ProcessExecutionError` so the API layer can map them to HTTP 502.
"""

from __future__ import annotations

import json
import socket
from typing import Any

from smartaccess.runtime.application.ports import ProcessExecutionState
from smartaccess.runtime.domain.experiment import ProcessExecutionError

_EXECUTE_SIGNAL = "EXECUTE_PROCESS_FILE"
_STATE_SIGNAL = "GET_PROCESS_EXECUTION_STATE"


class UdpProcessExecutorClient:
    """Talks to the instrument host over a request/ACK UDP protocol."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8889,
        timeout_s: float = 6.0,
    ) -> None:
        self._host = host
        self._port = port
        self._timeout_s = timeout_s

    def execute_process(self) -> Any:
        return self._send(_EXECUTE_SIGNAL)["response"]

    def read_execution_state(self) -> ProcessExecutionState:
        return _parse_execution_state(self._send(_STATE_SIGNAL)["response"])

    def _send(self, signal: str, payload: str | None = None) -> dict[str, Any]:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(self._timeout_s)
        try:
            data = signal if payload is None else f"{signal}|{payload}"
            sock.sendto(data.encode("utf-8"), (self._host, int(self._port)))
            raw, source = sock.recvfrom(4096)
            text = raw.decode("utf-8", errors="replace").strip()
            try:
                response: Any = json.loads(text)
            except json.JSONDecodeError:
                response = text
            return {
                "signal": signal,
                "response": response,
                "source": {"host": source[0], "port": source[1]},
            }
        except socket.timeout as exc:
            raise ProcessExecutionError(f"UDP ACK timeout for signal={signal}") from exc
        except OSError as exc:
            raise ProcessExecutionError(f"UDP send failed for signal={signal}: {exc}") from exc
        finally:
            sock.close()


def _parse_execution_state(response: Any) -> ProcessExecutionState:
    if not isinstance(response, dict):
        raise ProcessExecutionError("GET_PROCESS_EXECUTION_STATE 返回了非 JSON 响应")
    if response.get("status") != "success":
        message = str(response.get("message") or response)
        raise ProcessExecutionError(f"GET_PROCESS_EXECUTION_STATE 失败: {message}")
    if response.get("command") != _STATE_SIGNAL:
        raise ProcessExecutionError(
            f"GET_PROCESS_EXECUTION_STATE 的 command 字段异常: {response.get('command')}"
        )

    executing = response.get("executing")
    if not isinstance(executing, bool):
        raise ProcessExecutionError("GET_PROCESS_EXECUTION_STATE 的 `executing` 字段无效")

    if executing:
        process_name = str(response.get("process_name", ""))
        current_step = int(response.get("current_step", 0))
        total_steps = int(response.get("total_steps", 0))
        current_command = str(response.get("current_command", ""))
        detail = (
            f"process={process_name or '<unknown>'}, step={current_step}/{total_steps}, "
            f"current_command={current_command or '<unknown>'}, executing=True"
        )
        return ProcessExecutionState(
            status="running", detail=detail, current_command=current_command
        )

    return ProcessExecutionState(
        status="success",
        detail="当前没有流程在执行（executing=False）",
        current_command="",
    )
