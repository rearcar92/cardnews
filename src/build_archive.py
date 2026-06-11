from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT_DIR / "output"
TEMPLATE_PATH = ROOT_DIR / "templates" / "archive.html"
INDEX_PATH = ROOT_DIR / "index.html"
CARD_FILE_PATTERN = re.compile(r"morning-insight-cards-(\d{4}-\d{2}-\d{2})\.html$")
WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
THUMB_COLORS = ["#e8f4f5", "#f4f0e8", "#eef2f7", "#f2eef7", "#edf4ee"]


@dataclass
class CardItem:
    tier: str = ""
    topic: str = ""
    title: str = ""
    url: str = ""
    thumbnail_url: str = ""
    summary: list[str] = field(default_factory=list)
    why: str = ""
    action: str = ""
    source_meta: str = ""


@dataclass(frozen=True)
class ArchiveIssue:
    date: datetime
    filename: str
    cards: list[CardItem]

    @property
    def href(self) -> str:
        return f"output/{self.filename}"

    @property
    def key(self) -> str:
        return self.date.strftime("%Y-%m-%d")

    @property
    def date_label(self) -> str:
        return self.date.strftime("%Y.%m.%d")

    @property
    def short_date_label(self) -> str:
        return self.date.strftime("%m.%d")

    @property
    def weekday(self) -> str:
        return WEEKDAYS[self.date.weekday()]

    @property
    def title(self) -> str:
        return f"{self.date.strftime('%m월 %d일')} 카드뉴스"


class CardNewsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cards: list[CardItem] = []
        self.current: CardItem | None = None
        self.in_article = False
        self.in_topline = False
        self.in_h2 = False
        self.in_summary = False
        self.in_footer = False
        self.section_target = ""
        self.capture_text_for = ""
        self.topline_spans: list[str] = []
        self.footer_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        style = attrs_dict.get("style", "")

        if tag == "article":
            self.current = CardItem(thumbnail_url=attrs_dict.get("data-thumbnail", "") or "")
            self.in_article = True
            self.topline_spans = []
            self.footer_parts = []
            return

        if not self.in_article or self.current is None:
            return

        if tag == "div" and "justify-content:space-between" in style:
            self.in_topline = True
        elif tag == "h2":
            self.in_h2 = True
        elif tag == "a" and self.in_h2 and not self.current.url:
            self.current.url = attrs_dict.get("href", "") or ""
            self.capture_text_for = "title"
        elif tag == "li":
            self.in_summary = True
            self.capture_text_for = "summary"
        elif tag == "h3":
            self.capture_text_for = "section_heading"
        elif tag == "p" and self.section_target:
            self.capture_text_for = self.section_target
        elif tag == "footer":
            self.in_footer = True
        elif tag in {"div", "span"} and self.in_topline:
            self.capture_text_for = "topline"
        elif tag == "div" and self.in_footer:
            self.capture_text_for = "footer"

    def handle_endtag(self, tag: str) -> None:
        if tag == "article" and self.current is not None:
            if self.current.title:
                self.current.tier = self.topline_spans[0] if self.topline_spans else ""
                self.current.topic = self.topline_spans[-1] if len(self.topline_spans) > 1 else ""
                self.current.source_meta = self.footer_parts[0] if self.footer_parts else ""
                self.cards.append(self.current)
            self._reset_article()
            return

        if not self.in_article:
            return

        if tag == "div" and self.in_topline:
            self.in_topline = False
        elif tag == "h2":
            self.in_h2 = False
        elif tag == "li":
            self.in_summary = False
        elif tag == "section":
            self.section_target = ""
        elif tag == "footer":
            self.in_footer = False

        if tag in {"a", "li", "h3", "p", "div", "span"}:
            self.capture_text_for = ""

    def handle_data(self, data: str) -> None:
        if not self.in_article or self.current is None:
            return

        value = " ".join(data.split())
        if not value:
            return

        if self.capture_text_for == "topline":
            self.topline_spans.append(value)
        elif self.capture_text_for == "title":
            self.current.title = value
        elif self.capture_text_for == "summary":
            self.current.summary.append(value)
        elif self.capture_text_for == "section_heading":
            if "왜" in value:
                self.section_target = "why"
            elif "적용" in value:
                self.section_target = "action"
        elif self.capture_text_for == "why":
            self.current.why = value
        elif self.capture_text_for == "action":
            self.current.action = value
        elif self.capture_text_for == "footer":
            self.footer_parts.append(value)

    def _reset_article(self) -> None:
        self.current = None
        self.in_article = False
        self.in_topline = False
        self.in_h2 = False
        self.in_summary = False
        self.in_footer = False
        self.section_target = ""
        self.capture_text_for = ""


def parse_cards(path: Path) -> list[CardItem]:
    parser = CardNewsParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser.cards[:5]


def discover_issues() -> list[ArchiveIssue]:
    if not OUTPUT_DIR.exists():
        return []

    issues: list[ArchiveIssue] = []
    for path in OUTPUT_DIR.glob("morning-insight-cards-*.html"):
        match = CARD_FILE_PATTERN.match(path.name)
        if not match:
            continue
        issues.append(
            ArchiveIssue(
                date=datetime.strptime(match.group(1), "%Y-%m-%d"),
                filename=path.name,
                cards=parse_cards(path),
            )
        )

    return sorted(issues, key=lambda issue: issue.date, reverse=True)


def issue_to_dict(issue: ArchiveIssue) -> dict[str, Any]:
    return {
        "key": issue.key,
        "href": issue.href,
        "dateLabel": issue.date_label,
        "shortDateLabel": issue.short_date_label,
        "weekday": issue.weekday,
        "weekdayIndex": issue.date.weekday(),
        "title": issue.title,
        "cards": [
            {
                "tier": card.tier,
                "topic": card.topic,
                "title": card.title,
                "url": card.url,
                "summary": card.summary[:2],
                "why": card.why,
                "action": card.action,
                "sourceMeta": card.source_meta,
                "thumbnailUrl": card.thumbnail_url,
                "thumbColor": THUMB_COLORS[index % len(THUMB_COLORS)],
            }
            for index, card in enumerate(issue.cards)
        ],
    }


def render_weekday_buttons(active_weekday: int) -> str:
    buttons = []
    for index, label in enumerate(WEEKDAYS):
        active = " active" if index == active_weekday else ""
        escaped_label = html.escape(label)
        buttons.append(
            f'<button class="weekday{active}" type="button" data-weekday="{index}">{escaped_label}</button>'
        )
    return "\n".join(buttons)


def render_index(issues: list[ArchiveIssue]) -> str:
    active_issue = issues[0] if issues else None
    active_weekday = active_issue.date.weekday() if active_issue else datetime.now().weekday()
    archive_data = (
        json.dumps([issue_to_dict(issue) for issue in issues], ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace("</", "<\\/")
    )

    return (
        TEMPLATE_PATH.read_text(encoding="utf-8")
        .replace("__WEEKDAY_BUTTONS__", render_weekday_buttons(active_weekday))
        .replace("__ARCHIVE_DATA__", archive_data)
        .replace("__ACTIVE_WEEKDAY__", str(active_weekday))
    )


def main() -> int:
    issues = discover_issues()
    INDEX_PATH.write_text(render_index(issues), encoding="utf-8")
    print(INDEX_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
