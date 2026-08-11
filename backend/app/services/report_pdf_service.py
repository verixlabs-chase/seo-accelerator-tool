from __future__ import annotations

import math
import unicodedata
from html import escape
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase.pdfdoc import PDFString
from reportlab.platypus import (
    CondPageBreak,
    Flowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

PAGE_WIDTH, PAGE_HEIGHT = LETTER
INK = HexColor("#171717")
MUTED = HexColor("#626262")
SOFT = HexColor("#F5F5F2")
LINE = HexColor("#D9D9D4")
ACCENT = HexColor("#E85D19")
ACCENT_SOFT = HexColor("#FFF0E8")
GOOD = HexColor("#08775B")
GOOD_SOFT = HexColor("#EAF7F2")
BAD = HexColor("#B42318")
BAD_SOFT = HexColor("#FDECEA")
BLUE = HexColor("#2B9FC9")


def _ascii(value: Any) -> str:
    text = str(value or "")
    replacements = {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2022": "-",
        "\u2191": "up ",
        "\u2193": "down ",
        "\u2192": "to ",
        "\u00b7": " | ",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def _safe(value: Any) -> str:
    return escape(_ascii(value))


def _display_value(metric: dict[str, Any]) -> str:
    value = metric.get("current")
    if value is None:
        return "Not measured"
    unit = str(metric.get("unit") or "")
    if unit == "rating":
        return f"{float(value):.1f} / 5"
    if unit == "position":
        return f"#{float(value):.1f}"
    if isinstance(value, float) and not value.is_integer():
        return f"{value:,.1f}"
    return f"{float(value):,.0f}"


def _comparison_label(metric: dict[str, Any]) -> str:
    change = metric.get("change_percent")
    if change is None:
        return "Waiting for a full comparison"
    direction = str(metric.get("direction") or "changed")
    return f"{abs(float(change)):.1f}% {direction} from the earlier period"


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "eyebrow": ParagraphStyle(
            "InsightEyebrow",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=11,
            tracking=1.4,
            textColor=ACCENT,
            spaceAfter=6,
        ),
        "title": ParagraphStyle(
            "InsightTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=25,
            leading=29,
            textColor=INK,
            alignment=TA_LEFT,
            spaceAfter=9,
        ),
        "lede": ParagraphStyle(
            "InsightLede",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=11.5,
            leading=17,
            textColor=INK,
            spaceAfter=9,
        ),
        "meta": ParagraphStyle(
            "InsightMeta",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=12,
            textColor=MUTED,
        ),
        "h1": ParagraphStyle(
            "InsightH1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=INK,
            spaceBefore=8,
            spaceAfter=5,
            keepWithNext=True,
        ),
        "h2": ParagraphStyle(
            "InsightH2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            textColor=INK,
            spaceBefore=5,
            spaceAfter=5,
            keepWithNext=True,
        ),
        "h3": ParagraphStyle(
            "InsightH3",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=14,
            textColor=INK,
            spaceAfter=3,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "InsightBody",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=14,
            textColor=INK,
            spaceAfter=5,
        ),
        "small": ParagraphStyle(
            "InsightSmall",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=10.5,
            textColor=MUTED,
        ),
        "metric_label": ParagraphStyle(
            "InsightMetricLabel",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=MUTED,
            spaceAfter=4,
        ),
        "metric_value": ParagraphStyle(
            "InsightMetricValue",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=20,
            textColor=INK,
            spaceAfter=3,
        ),
        "metric_change": ParagraphStyle(
            "InsightMetricChange",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=10,
            textColor=MUTED,
        ),
        "number": ParagraphStyle(
            "InsightNumber",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=14,
            alignment=TA_CENTER,
            textColor=colors.white,
        ),
        "table_head": ParagraphStyle(
            "InsightTableHead",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=9.5,
            textColor=MUTED,
        ),
        "table_body": ParagraphStyle(
            "InsightTableBody",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=10,
            textColor=INK,
        ),
        "footer": ParagraphStyle(
            "InsightFooter",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=7,
            leading=9,
            textColor=MUTED,
            alignment=TA_RIGHT,
        ),
    }


class TrendChart(Flowable):
    def __init__(
        self,
        current_points: list[dict[str, Any]],
        comparison_points: list[dict[str, Any]],
        *,
        field: str,
        lower_is_better: bool,
        width: float,
    ) -> None:
        super().__init__()
        self.width = width
        self.height = 138
        self.current = [point for point in current_points if point.get(field) is not None]
        self.comparison = [point for point in comparison_points if point.get(field) is not None]
        self.field = field
        self.lower_is_better = lower_is_better

    def wrap(self, available_width: float, available_height: float) -> tuple[float, float]:
        return min(self.width, available_width), self.height

    def _coordinates(
        self,
        points: list[dict[str, Any]],
        *,
        minimum: float,
        maximum: float,
        left: float,
        bottom: float,
        plot_width: float,
        plot_height: float,
    ) -> list[tuple[float, float]]:
        denominator = max(len(points) - 1, 1)
        coordinates: list[tuple[float, float]] = []
        for index, point in enumerate(points):
            value = float(point[self.field])
            ratio = (value - minimum) / (maximum - minimum)
            if self.lower_is_better:
                ratio = 1 - ratio
            coordinates.append(
                (
                    left + (index / denominator) * plot_width,
                    bottom + ratio * plot_height,
                )
            )
        return coordinates

    def draw(self) -> None:
        canvas = self.canv
        left, right, bottom, top = 38, 8, 28, 18
        plot_width = self.width - left - right
        plot_height = self.height - bottom - top
        values = [float(point[self.field]) for point in self.current + self.comparison]
        if not values:
            canvas.setFillColor(MUTED)
            canvas.setFont("Helvetica", 8)
            canvas.drawString(left, bottom + plot_height / 2, "No saved trend values are available yet.")
            return

        minimum, maximum = min(values), max(values)
        if math.isclose(minimum, maximum):
            padding = max(abs(maximum) * 0.1, 1.0)
            minimum -= padding
            maximum += padding

        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.7)
        for ratio in (0, 0.5, 1):
            y = bottom + ratio * plot_height
            canvas.line(left, y, left + plot_width, y)

        top_value = minimum if self.lower_is_better else maximum
        bottom_value = maximum if self.lower_is_better else minimum
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 6.5)
        canvas.drawRightString(left - 5, bottom + plot_height - 2, f"{top_value:,.1f}")
        canvas.drawRightString(left - 5, bottom - 2, f"{bottom_value:,.1f}")

        for points, color, dashed, width in (
            (self.comparison, BLUE, True, 1.5),
            (self.current, ACCENT, False, 2.2),
        ):
            coordinates = self._coordinates(
                points,
                minimum=minimum,
                maximum=maximum,
                left=left,
                bottom=bottom,
                plot_width=plot_width,
                plot_height=plot_height,
            )
            if not coordinates:
                continue
            canvas.setStrokeColor(color)
            canvas.setLineWidth(width)
            canvas.setDash(4, 3) if dashed else canvas.setDash()
            path = canvas.beginPath()
            path.moveTo(*coordinates[0])
            for coordinate in coordinates[1:]:
                path.lineTo(*coordinate)
            canvas.drawPath(path, stroke=1, fill=0)
            if not dashed:
                canvas.setFillColor(color)
                for x, y in coordinates:
                    canvas.circle(x, y, 1.7, stroke=0, fill=1)
        canvas.setDash()

        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 6.5)
        if self.current:
            start = _ascii(self.current[0].get("date") or "")
            end = _ascii(self.current[-1].get("date") or "")
            canvas.drawString(left, 10, start)
            canvas.drawRightString(left + plot_width, 10, end)


class SectionBookmark(Flowable):
    def __init__(self, title: str, key: str) -> None:
        super().__init__()
        self.title = _ascii(title)
        self.key = key
        self.width = 0
        self.height = 0

    def wrap(self, available_width: float, available_height: float) -> tuple[float, float]:
        return 0, 0

    def draw(self) -> None:
        self.canv.bookmarkPage(self.key)
        self.canv.addOutlineEntry(self.title, self.key, level=0, closed=False)


def _metric_grid(metrics: list[dict[str, Any]], styles: dict[str, ParagraphStyle], width: float) -> Table:
    columns = 3
    gap = 8
    cell_width = (width - gap * (columns - 1)) / columns
    cells: list[list[Any]] = []
    row: list[Any] = []
    backgrounds: dict[tuple[int, int], colors.Color] = {}
    accents: dict[tuple[int, int], colors.Color] = {}
    for metric in metrics:
        result = str(metric.get("result") or "")
        background = GOOD_SOFT if result == "improved" else BAD_SOFT if result == "declined" else colors.white
        accent = GOOD if result == "improved" else BAD if result == "declined" else LINE
        source = metric.get("source") or {}
        coverage = ((metric.get("coverage") or {}).get("current") or {}).get("state") or "unknown"
        cell = [
            Paragraph(_safe(metric.get("label") or "Measurement"), styles["metric_label"]),
            Paragraph(_safe(_display_value(metric)), styles["metric_value"]),
            Paragraph(_safe(_comparison_label(metric)), styles["metric_change"]),
            Spacer(1, 5),
            Paragraph(
                _safe(f"{source.get('label') or 'Saved data'} | {str(coverage).replace('_', ' ')} coverage"),
                styles["small"],
            ),
        ]
        column_index = len(row)
        row_index = len(cells)
        backgrounds[(row_index, column_index)] = background
        accents[(row_index, column_index)] = accent
        row.append(cell)
        if len(row) == columns:
            cells.append(row)
            row = []
    if row:
        while len(row) < columns:
            row.append("")
        cells.append(row)

    table = Table(cells, colWidths=[cell_width] * columns, hAlign="LEFT")
    commands: list[tuple[Any, ...]] = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.6, LINE),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white]),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
    ]
    for (row_index, column_index), background in backgrounds.items():
        commands.append(("BACKGROUND", (column_index, row_index), (column_index, row_index), background))
        commands.append(("LINEBEFORE", (column_index, row_index), (column_index, row_index), 3, accents[(row_index, column_index)]))
    table.setStyle(TableStyle(commands))
    return table


def _story_list(
    title: str,
    items: list[dict[str, Any]],
    empty: str,
    styles: dict[str, ParagraphStyle],
    *,
    detail_key: str = "detail",
) -> list[Any]:
    flowables: list[Any] = [Paragraph(_safe(title), styles["h2"])]
    if not items:
        flowables.append(Paragraph(_safe(empty), styles["body"]))
        return flowables
    for index, item in enumerate(items, start=1):
        detail = item.get(detail_key) or item.get("detail") or item.get("result") or item.get("status") or ""
        flowables.append(
            KeepTogether(
                [
                    Paragraph(f"<b>{index}. {_safe(item.get('title') or 'Saved item')}</b>", styles["body"]),
                    Paragraph(_safe(detail), styles["small"]),
                    Spacer(1, 4),
                ]
            )
        )
    return flowables


def _chart_blocks(snapshot: dict[str, Any], styles: dict[str, ParagraphStyle], width: float) -> list[Any]:
    series_by_key = {str(item.get("key")): item for item in snapshot.get("trend_series") or []}
    definitions = (
        ("google_discovery", "visits", "Visits from Google", False),
        ("google_discovery", "appearances", "Times shown on Google", False),
        ("tracked_rankings", "average_position", "Average tracked keyword position", True),
        ("website_scans", "issues", "Issues found in website scans", True),
        ("review_growth", "reviews", "Reviews received in the last 30 days", False),
    )
    heading: list[Any] = [
        Paragraph("Performance over time", styles["h1"]),
        Paragraph(
            "Orange shows this report period. Dashed blue shows the earlier period. Every chart includes a written description so the result does not depend on color alone.",
            styles["body"],
        ),
    ]
    cards: list[Any] = []
    for series_key, field, label, lower_is_better in definitions:
        series = series_by_key.get(series_key) or {}
        current = list(series.get("points") or [])
        comparison = list(series.get("comparison_points") or [])
        if not any(point.get(field) is not None for point in current + comparison):
            continue
        direction_note = "A lower number is better." if lower_is_better else "A higher number is generally better."
        chart = TrendChart(
            current,
            comparison,
            field=field,
            lower_is_better=lower_is_better,
            width=width - 24,
        )
        card = Table(
            [[[
                Paragraph(_safe(label), styles["h2"]),
                Paragraph("<font color='#E85D19'><b>Orange: current</b></font> &nbsp; <font color='#2B9FC9'><b>Dashed blue: earlier</b></font>", styles["small"]),
                Spacer(1, 4),
                chart,
                Paragraph(_safe(f"{series.get('description') or ''} {direction_note}"), styles["small"]),
            ]]],
            colWidths=[width],
        )
        card.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.7, LINE),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                    ("LEFTPADDING", (0, 0), (-1, -1), 12),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                    ("TOPPADDING", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ]
            )
        )
        cards.append(card)
    if not cards:
        return heading + [Paragraph("No saved trend measurements are available yet.", styles["body"])]

    flowables: list[Any] = [KeepTogether(heading + [cards[0]])]
    for card in cards[1:]:
        flowables.extend([Spacer(1, 10), KeepTogether([card])])
    return flowables


def _action_blocks(items: list[dict[str, Any]], styles: dict[str, ParagraphStyle], width: float) -> list[Any]:
    heading: list[Any] = [
        Paragraph("What to do next", styles["h1"]),
        Paragraph(
            "Start with the first item. Each action appears once and names the measurement used to check whether the work helped.",
            styles["body"],
        ),
    ]
    if not items:
        return heading + [Paragraph("No verified next action is ready yet.", styles["body"])]
    cards: list[Any] = []
    for index, item in enumerate(items, start=1):
        steps = list(item.get("steps") or [])
        measurement = item.get("measurement") or {}
        check_after = measurement.get("check_after_days")
        check_label = (
            f"Check {measurement.get('label') or 'the saved measurement'} again after {int(check_after)} days."
            if check_after
            else f"Measure {measurement.get('label') or 'the saved result'} before and after the work."
        )
        body: list[Any] = [
            Paragraph(_safe(item.get("title") or "Saved action"), styles["h2"]),
            Paragraph(f"<b>Why this matters:</b> {_safe(item.get('why_it_matters') or item.get('detail') or '')}", styles["body"]),
        ]
        for step_index, step in enumerate(steps, start=1):
            body.append(Paragraph(f"<b>{step_index}.</b> {_safe(step)}", styles["body"]))
        body.append(
            Paragraph(
                f"<b>How results will be checked:</b> {_safe(check_label)} {_safe(measurement.get('explanation') or '')}",
                styles["small"],
            )
        )
        number_cell = Table([[Paragraph(str(index), styles["number"])]], colWidths=[28], rowHeights=[28])
        number_cell.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), ACCENT),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        card = Table([[number_cell, body]], colWidths=[38, width - 62])
        card.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.7, LINE),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ]
            )
        )
        cards.append(card)
    flowables: list[Any] = [KeepTogether(heading + [cards[0]])]
    for card in cards[1:]:
        flowables.extend([Spacer(1, 9), KeepTogether([card])])
    return flowables


def _sources_table(metrics: list[dict[str, Any]], styles: dict[str, ParagraphStyle], width: float) -> Table:
    data: list[list[Any]] = [
        [
            Paragraph("Measurement", styles["table_head"]),
            Paragraph("Source", styles["table_head"]),
            Paragraph("Updated", styles["table_head"]),
            Paragraph("Coverage", styles["table_head"]),
        ]
    ]
    for metric in metrics:
        source = metric.get("source") or {}
        coverage = (metric.get("coverage") or {}).get("current") or {}
        state = str(coverage.get("state") or "unknown").replace("_", " ").capitalize()
        data.append(
            [
                Paragraph(f"<b>{_safe(metric.get('label') or 'Measurement')}</b>", styles["table_body"]),
                Paragraph(_safe(source.get("label") or "Saved InsightOS data"), styles["table_body"]),
                Paragraph(_safe(source.get("last_updated") or "Not available"), styles["table_body"]),
                Paragraph(
                    _safe(f"{state} ({int(coverage.get('observed') or 0)} of {int(coverage.get('expected') or 0)})"),
                    styles["table_body"],
                ),
            ]
        )
    table = Table(data, colWidths=[width * 0.31, width * 0.27, width * 0.18, width * 0.24], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), SOFT),
                ("BOX", (0, 0), (-1, -1), 0.7, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def _page(canvas: Any, document: SimpleDocTemplate, *, title: str) -> None:
    canvas.saveState()
    canvas.setTitle(_ascii(title))
    canvas.setAuthor("VerixLabs")
    canvas.setSubject("InsightOS business progress report")
    canvas.setKeywords("InsightOS, VerixLabs, SEO progress report")
    canvas._doc.Catalog.Lang = PDFString("en-US")
    canvas.setFillColor(ACCENT)
    canvas.rect(0, PAGE_HEIGHT - 7, PAGE_WIDTH, 7, stroke=0, fill=1)
    canvas.setStrokeColor(LINE)
    canvas.line(document.leftMargin, 34, PAGE_WIDTH - document.rightMargin, 34)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7)
    canvas.drawString(document.leftMargin, 22, "InsightOS by VerixLabs | Private progress report")
    canvas.drawRightString(PAGE_WIDTH - document.rightMargin, 22, f"Page {document.page}")
    canvas.restoreState()


def build_report_pdf(snapshot: dict[str, Any]) -> bytes:
    styles = _styles()
    campaign = snapshot.get("campaign") or {}
    period = snapshot.get("period") or {}
    executive = snapshot.get("executive_summary") or {}
    metrics = list(snapshot.get("metrics") or [])
    location_name = campaign.get("location_name") or campaign.get("name") or "Business"
    title = f"{location_name} progress report"

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        leftMargin=0.58 * inch,
        rightMargin=0.58 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.62 * inch,
        title=_ascii(title),
        author="VerixLabs",
        subject="InsightOS business progress report",
        pageCompression=1,
    )
    usable_width = PAGE_WIDTH - document.leftMargin - document.rightMargin
    story: list[Any] = [
        SectionBookmark("Report summary", "report-summary"),
        Paragraph("INSIGHTOS PROGRESS REPORT", styles["eyebrow"]),
        Paragraph(_safe(executive.get("headline") or title), styles["title"]),
        Paragraph(_safe(executive.get("summary") or ""), styles["lede"]),
        Paragraph(
            _safe(f"{location_name} | {period.get('start') or 'Unknown'} to {period.get('end') or 'Unknown'}"),
            styles["meta"],
        ),
        Spacer(1, 14),
        Paragraph("Your results at a glance", styles["h1"]),
        Paragraph(
            "Every number below comes from a saved source. Missing information is shown as not measured instead of being treated as zero.",
            styles["body"],
        ),
        _metric_grid(metrics, styles, usable_width),
        Spacer(1, 12),
    ]
    story.extend([SectionBookmark("Performance over time", "performance-over-time")])
    story.extend(_chart_blocks(snapshot, styles, usable_width))
    story.extend(
        [
            CondPageBreak(220),
            SectionBookmark("What changed", "what-changed"),
            Spacer(1, 18),
            Paragraph("The story behind the numbers", styles["eyebrow"]),
            Paragraph("What changed and what needs attention", styles["title"]),
        ]
    )
    story.extend(
        _story_list(
            "What improved",
            list(snapshot.get("wins") or []),
            "No clear improvement was measured in this report window.",
            styles,
        )
    )
    story.extend(
        _story_list(
            "What needs attention",
            list(snapshot.get("risks") or []),
            "No measured risk was found in the available information.",
            styles,
        )
    )
    story.extend(
        _story_list(
            "Work completed",
            list(snapshot.get("completed_actions") or []),
            "No completed action was recorded in this period.",
            styles,
            detail_key="completed_at",
        )
    )
    story.extend(
        _story_list(
            "Measured results",
            list(snapshot.get("measured_outcomes") or []),
            "Completed work is still waiting for enough follow-up information.",
            styles,
            detail_key="result",
        )
    )
    story.extend([Spacer(1, 8)])
    story.append(SectionBookmark("What to do next", "what-to-do-next"))
    story.extend(_action_blocks(list(snapshot.get("next_priorities") or []), styles, usable_width))
    story.extend(
        [
            PageBreak(),
            SectionBookmark("Data sources", "data-sources"),
            Paragraph("REPORT DETAILS", styles["eyebrow"]),
            Paragraph("Where the numbers came from", styles["title"]),
            Paragraph(
                "This appendix shows source, recency, and coverage so partial or missing information stays visible.",
                styles["body"],
            ),
            _sources_table(metrics, styles, usable_width),
            Spacer(1, 16),
            Paragraph("Saved report record", styles["h1"]),
            Paragraph(
                _safe(
                    f"Snapshot version: {snapshot.get('schema_version') or 'legacy'} | "
                    f"Data freshness: {(snapshot.get('source') or {}).get('freshness_state') or 'unknown'}"
                ),
                styles["body"],
            ),
            Paragraph(
                _safe(f"Snapshot ID: {snapshot.get('snapshot_hash') or 'legacy'}"),
                styles["small"],
            ),
            Spacer(1, 12),
            Table(
                [[Paragraph(
                    "This report separates completed work from measured results. It does not claim that an action caused a change unless the saved follow-up evidence supports that conclusion.",
                    styles["body"],
                )]],
                colWidths=[usable_width],
                style=TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), ACCENT_SOFT),
                        ("BOX", (0, 0), (-1, -1), 0.7, ACCENT),
                        ("LEFTPADDING", (0, 0), (-1, -1), 12),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                        ("TOPPADDING", (0, 0), (-1, -1), 10),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                    ]
                ),
            ),
        ]
    )

    document.build(
        story,
        onFirstPage=lambda canvas, doc: _page(canvas, doc, title=title),
        onLaterPages=lambda canvas, doc: _page(canvas, doc, title=title),
    )
    return buffer.getvalue()
