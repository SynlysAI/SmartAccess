"""运行产物存储适配器。"""

from __future__ import annotations

from pathlib import Path


class FileArtifactStore:
    """把运行产物保存到工作区 runs 目录。"""

    def __init__(self, workspace_dir: str | Path) -> None:
        """初始化文件产物存储。

        Args:
            workspace_dir: v2 工作区目录。
        """

        self._workspace_dir = Path(workspace_dir)

    def save_screenshot(self, session_id: str, name: str, data: bytes) -> str:
        """保存运行截图。

        Args:
            session_id: 运行会话 ID。
            name: 截图文件名。
            data: PNG 字节。

        Returns:
            保存后的文件路径字符串。
        """

        path = self._session_dir(session_id) / "screenshots" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return str(path)

    def save_text(self, session_id: str, name: str, text: str) -> str:
        """保存文本产物。

        Args:
            session_id: 运行会话 ID。
            name: 文件名。
            text: 文本内容。

        Returns:
            保存后的文件路径字符串。
        """

        path = self._session_dir(session_id) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return str(path)

    def append_jsonl(self, session_id: str, name: str, line: str) -> str:
        """追加 JSONL 记录。

        Args:
            session_id: 运行会话 ID。
            name: JSONL 文件名。
            line: 已序列化的 JSON 行。

        Returns:
            保存后的文件路径字符串。
        """

        path = self._session_dir(session_id) / name
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line)
            handle.write("\n")
        return str(path)

    def _session_dir(self, session_id: str) -> Path:
        """返回并创建会话目录。"""

        path = self._workspace_dir / "runs" / session_id
        path.mkdir(parents=True, exist_ok=True)
        return path


class InMemoryArtifactStore:
    """内存产物存储，供快速本地流程使用。"""

    def __init__(self) -> None:
        """初始化内存产物字典。"""

        self.screenshots: dict[str, bytes] = {}
        self.texts: dict[str, str] = {}
        self.jsonl: dict[str, list[str]] = {}

    def save_screenshot(self, session_id: str, name: str, data: bytes) -> str:
        """保存截图到内存。"""

        key = f"{session_id}/screenshots/{name}"
        self.screenshots[key] = data
        return key

    def save_text(self, session_id: str, name: str, text: str) -> str:
        """保存文本到内存。"""

        key = f"{session_id}/{name}"
        self.texts[key] = text
        return key

    def append_jsonl(self, session_id: str, name: str, line: str) -> str:
        """追加 JSONL 行到内存。"""

        key = f"{session_id}/{name}"
        self.jsonl.setdefault(key, []).append(line)
        return key
