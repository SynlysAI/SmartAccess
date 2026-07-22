"""工作流运行前的人工输入对话框。"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from smartaccess.runtime.application.workflow_input_resolver import RuntimeInputField


class RuntimeInputDialog(QDialog):
    """集中收集一个工作流运行所需的人工输入。"""

    def __init__(
        self,
        fields: list[RuntimeInputField],
        parent: QWidget | None = None,
    ) -> None:
        """初始化运行前输入对话框。

        Args:
            fields: 需要人工填写的工作流输入字段。
            parent: Qt 父组件。
        """

        super().__init__(parent)
        self.setWindowTitle("填写运行参数")
        self.setMinimumWidth(460)
        self._editors: dict[str, QLineEdit] = {}

        layout = QVBoxLayout(self)
        hint = QLabel("请填写工作流本次运行所需的输入内容。")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = QFormLayout()
        for field in fields:
            editor = QLineEdit()
            editor.setPlaceholderText(field.template.replace("{input}", ""))
            editor.setClearButtonEnabled(True)
            self._editors[field.step_id] = editor
            label = f"{field.step_id} / {_action_label(field.action)}"
            if field.anchor_id:
                label = f"{label} / {field.anchor_id}"
            form.addRow(label, editor)
        layout.addLayout(form)

        self._error = QLabel("")
        self._error.setObjectName("FormError")
        self._error.setVisible(False)
        layout.addWidget(self._error)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("开始运行")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> dict[str, str]:
        """返回用户填写的运行时输入值。"""

        return {
            step_id: editor.text().strip()
            for step_id, editor in self._editors.items()
        }

    def _accept(self) -> None:
        """校验输入非空后关闭对话框。"""

        missing = [
            step_id
            for step_id, value in self.values().items()
            if not value
        ]
        if missing:
            self._error.setText("请填写: " + "、".join(missing))
            self._error.setVisible(True)
            return
        self.accept()


def _action_label(action: str) -> str:
    """返回动作在运行参数表单中的中文名称。"""

    labels = {
        "type": "输入",
        "ocr": "OCR识别",
    }
    return labels.get(action, action)
