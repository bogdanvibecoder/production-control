"""Утилита генерации PDF-отчётов по производству."""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any

from loguru import logger
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# --- Стили текста ---

_styles = getSampleStyleSheet()

STYLE_TITLE = ParagraphStyle(
    "ReportTitle",
    parent=_styles["Title"],
    fontSize=18,
    spaceAfter=6 * mm,
)

STYLE_SUBTITLE = ParagraphStyle(
    "ReportSubtitle",
    parent=_styles["Heading2"],
    fontSize=13,
    spaceBefore=4 * mm,
    spaceAfter=2 * mm,
)

STYLE_BODY = _styles["BodyText"]

# --- Стили таблицы ---

TABLE_STYLE = TableStyle(
    [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9E1F2")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F2F2")]),
    ]
)


def generate_report(report_data: dict[str, Any]) -> bytes:
    """Генерация PDF-отчёта по производству за период.

    Формирует документ A4 с:
    - Заголовком и периодом
    - Сводкой (план / факт / % выполнения)
    - Таблицей разбивки по статусам

    Args:
        report_data: Словарь из ``AnalyticsService.get_production_report()``.
            Ожидаемые ключи: ``date_from``, ``date_to``, ``work_center_id``,
            ``total_batches``, ``batches_by_status``, ``total_planned``,
            ``total_actual``, ``completion_percent``.

    Returns:
        Содержимое PDF-файла в байтах.
    """
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )

    elements: list[Any] = []

    # --- Заголовок ---
    elements.append(Paragraph("Производственный отчёт", STYLE_TITLE))

    date_from = report_data.get("date_from", "")
    date_to = report_data.get("date_to", "")
    if isinstance(date_from, datetime):
        date_from = date_from.strftime("%d.%m.%Y")
    if isinstance(date_to, datetime):
        date_to = date_to.strftime("%d.%m.%Y")

    elements.append(Paragraph(f"Период: {date_from} — {date_to}", STYLE_BODY))

    wc_id = report_data.get("work_center_id")
    wc_label = f"Рабочий центр: {wc_id}" if wc_id is not None else "Все рабочие центры"
    elements.append(Paragraph(wc_label, STYLE_BODY))

    elements.append(Spacer(1, 6 * mm))

    # --- Сводка ---
    elements.append(Paragraph("Сводка", STYLE_SUBTITLE))

    summary_data = [
        ["Показатель", "Значение"],
        ["Всего партий", str(report_data.get("total_batches", 0))],
        ["План (кол-во)", str(report_data.get("total_planned", 0))],
        ["Факт (кол-во)", str(report_data.get("total_actual", 0))],
        ["Выполнение, %", str(report_data.get("completion_percent", 0))],
    ]

    summary_table = Table(summary_data, colWidths=[80 * mm, 60 * mm])
    summary_table.setStyle(TABLE_STYLE)
    elements.append(summary_table)

    elements.append(Spacer(1, 6 * mm))

    # --- Партии по статусам ---
    elements.append(Paragraph("Партии по статусам", STYLE_SUBTITLE))

    status_rows: list[list[str]] = [["Статус", "Количество"]]
    batches_by_status: dict[str, int] = report_data.get("batches_by_status", {})
    for status, count in batches_by_status.items():
        status_rows.append([status, str(count)])

    status_table = Table(status_rows, colWidths=[80 * mm, 60 * mm])
    status_table.setStyle(TABLE_STYLE)
    elements.append(status_table)

    # --- Сборка документа ---
    doc.build(elements)

    result: bytes = buffer.getvalue()
    logger.info("PDF-отчёт сгенерирован: {} байт", len(result))
    return result
