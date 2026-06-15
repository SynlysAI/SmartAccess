"""Small HTML rendering helpers for desktop text panels."""

from __future__ import annotations

from html import escape

from smartaccess.desktop.shell import theme


def text(value: object | None) -> str:
    """Return HTML-escaped display text."""

    return escape("-" if value is None or value == "" else str(value), quote=True)


def document(body: str) -> str:
    """Wrap a rich text body in shared desktop styling."""

    return f"""
<html>
<body style="font-family:'Microsoft YaHei','Segoe UI',sans-serif;
             font-size:13px;color:{theme.TEXT};margin:0;">
{body}
</body>
</html>
"""


def panel(title: str, body: str, *, status: str | None = None) -> str:
    """Render a titled text panel."""

    color = _status_color(status)
    return document(
        f"""
<div style="font-size:14px;font-weight:700;color:{theme.TEXT};margin-bottom:6px;">
  {text(title)}
</div>
<div style="border-left:3px solid {color};padding-left:10px;">
  {body}
</div>
"""
    )


def field(label: str, value: object | None, *, strong: bool = True) -> str:
    """Render a label/value row."""

    value_html = text(value)
    if strong:
        value_html = f"<b>{value_html}</b>"
    return (
        f"<span style=\"color:{theme.TEXT_MUTED};\">{text(label)}</span>"
        f"<span style=\"color:{theme.TEXT};\">{value_html}</span>"
    )


def field_block(label: str, value: object | None, *, strong: bool = True) -> str:
    """Render a wrap-friendly label/value block."""

    value_html = text(value)
    if strong:
        value_html = f"<b>{value_html}</b>"
    return (
        f"<div style=\"line-height:1.45;margin:2px 0;\">"
        f"<span style=\"color:{theme.TEXT_MUTED};font-weight:600;\">{text(label)}</span>"
        f"<span style=\"color:{theme.TEXT};overflow-wrap:anywhere;word-break:break-all;\">"
        f"{value_html}</span></div>"
    )


def field_list(items: list[tuple[str, object | None]]) -> str:
    """Render multiple fields as stacked wrap-friendly blocks."""

    return "".join(field_block(label, value) for label, value in items)


def info_card(title: str, items: list[tuple[str, object | None]]) -> str:
    """Render a compact information-assessment card for summary grids."""

    return (
        f"<div style=\"border:1px solid {theme.BORDER};border-radius:6px;"
        f"background:{theme.SURFACE_ALT};padding:7px 8px;\">"
        f"<div style=\"font-size:12px;font-weight:700;color:{theme.TEXT};"
        f"margin-bottom:4px;\">{text(title)}</div>"
        f"{field_list(items)}</div>"
    )


def info_grid(cards: list[str]) -> str:
    """Render cards in a width-efficient multi-column table."""

    if not cards:
        return ""
    width = max(1, 100 // len(cards))
    cells = "".join(
        f"<td width=\"{width}%\" valign=\"top\" style=\"padding:0 4px;\">{card}</td>"
        for card in cards
    )
    return (
        "<table width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" "
        f"style=\"table-layout:fixed;\"><tr>{cells}</tr></table>"
    )


def paragraph(value: object | None) -> str:
    """Render a paragraph preserving line breaks."""

    return (
        f"<div style=\"line-height:1.55;margin:4px 0;color:{theme.TEXT};\">"
        f"{text(value).replace(chr(10), '<br>')}"
        "</div>"
    )


def status_badge(value: object | None, *, status: str | None = None) -> str:
    """Render a compact status badge."""

    color = _status_color(status)
    return (
        f"<span style=\"display:inline-block;border:1px solid {color};"
        f"color:{color};border-radius:5px;padding:1px 6px;font-weight:700;\">"
        f"{text(value)}</span>"
    )


def markdownish(title: str, content: str, *, status: str | None = None) -> str:
    """Render simple markdown-like text with heading hierarchy."""

    parts: list[str] = []
    for raw in content.strip().splitlines():
        line = raw.strip()
        if not line:
            parts.append("<div style=\"height:6px;\"></div>")
        elif line.startswith("## "):
            parts.append(
                f"<div style=\"font-size:13px;font-weight:700;color:{theme.TEXT};"
                f"margin:8px 0 3px;\">{text(line[3:])}</div>"
            )
        elif line.startswith("- "):
            parts.append(
                f"<div style=\"line-height:1.5;margin:2px 0 2px 10px;\">"
                f"&bull; {text(line[2:])}</div>"
            )
        else:
            parts.append(
                f"<div style=\"line-height:1.5;margin:2px 0;color:{theme.TEXT};\">"
                f"{text(line)}</div>"
            )
    body = "".join(parts) if parts else paragraph("")
    return panel(title, body, status=status)


def ocr_rule(match_mode: object | None, expected_text: object | None) -> str:
    """Format the OCR pass rule."""

    mode = str(match_mode or "none")
    if mode == "not_empty":
        return mode
    return f"{mode} {expected_text or '-'}"


def _status_color(status: str | None) -> str:
    """Map a status name to a theme color."""

    if status == "error":
        return theme.DANGER
    if status == "warning":
        return theme.WARNING
    if status == "success":
        return theme.SUCCESS
    return theme.PRIMARY
