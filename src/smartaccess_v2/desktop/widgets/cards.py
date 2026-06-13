"""桌面端卡片容器工具。"""

from __future__ import annotations

from PyQt6.QtWidgets import QFrame, QVBoxLayout


def create_card(
    *,
    object_name: str = "Card",
    margins: tuple[int, int, int, int] = (16, 16, 16, 16),
    spacing: int = 10,
) -> tuple[QFrame, QVBoxLayout]:
    """创建统一卡片容器。

    Args:
        object_name: QSS 使用的对象名。
        margins: 卡片内部边距，顺序为左、上、右、下。
        spacing: 卡片内部布局间距。

    Returns:
        卡片框架和其垂直布局。
    """

    card = QFrame()
    card.setObjectName(object_name)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    return card, layout
