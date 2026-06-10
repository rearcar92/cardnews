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
            self.current = CardItem()
            self.current.thumbnail_url = attrs_dict.get("data-thumbnail", "") or ""
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
                if self.topline_spans:
                    self.current.tier = self.topline_spans[0]
                if len(self.topline_spans) > 1:
                    self.current.topic = self.topline_spans[-1]
                if self.footer_parts:
                    self.current.source_meta = self.footer_parts[0]
                self.cards.append(self.current)
            self.current = None
            self.in_article = False
            self.in_topline = False
            self.in_h2 = False
            self.in_summary = False
            self.in_footer = False
            self.section_target = ""
            self.capture_text_for = ""
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
        buttons.append(
            f'<button class="weekday{active}" type="button" data-weekday="{index}">{html.escape(label)}</button>'
        )
    return "\n".join(buttons)


def render_index(issues: list[ArchiveIssue]) -> str:
    active_issue = issues[0] if issues else None
    active_weekday = active_issue.date.weekday() if active_issue else datetime.now().weekday()
    data_json = json.dumps([issue_to_dict(issue) for issue in issues], ensure_ascii=False)

    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>요일별 카드뉴스</title>
  <meta name="description" content="매일 발송한 카드뉴스 공개 아카이브">
  <style>
    :root {{
      color-scheme: light;
      --bg: #ffffff;
      --ink: #202020;
      --muted: #9a9a9a;
      --line: #e9e9e9;
      --accent: #12b9b5;
      --panel: #ffffff;
    }}
    * {{
      box-sizing: border-box;
    }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: "Segoe UI", "Malgun Gothic", Arial, sans-serif;
      letter-spacing: 0;
    }}
    button,
    select {{
      font: inherit;
    }}
    button {{
      border: 0;
      background: transparent;
      cursor: pointer;
    }}
    a {{
      color: inherit;
      text-decoration: none;
    }}
    .page {{
      width: min(960px, calc(100% - 32px));
      margin: 0 auto;
      padding: 64px 0 72px;
    }}
    .masthead {{
      text-align: center;
      margin-bottom: 24px;
    }}
    .masthead h1 {{
      margin: 0;
      font-size: 18px;
      line-height: 1.35;
      font-weight: 500;
    }}
    .masthead p {{
      margin: 14px 0 0;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
    }}
    .weekdays {{
      display: grid;
      grid-template-columns: repeat(7, 1fr);
      border-bottom: 1px solid var(--line);
      margin-bottom: 14px;
    }}
    .weekday {{
      position: relative;
      height: 38px;
      color: #969696;
      font-size: 14px;
    }}
    .weekday.active {{
      color: #202020;
      font-weight: 500;
    }}
    .weekday.active::after {{
      content: "";
      position: absolute;
      left: 35%;
      right: 35%;
      bottom: -1px;
      height: 1px;
      background: var(--accent);
    }}
    .issue-head {{
      display: flex;
      justify-content: flex-end;
      gap: 18px;
      align-items: center;
      margin: 0 0 18px;
      color: #9b9b9b;
      font-size: 13px;
      position: relative;
    }}
    .issue-head strong {{
      position: relative;
      color: #606060;
      font-weight: 400;
    }}
    .issue-head strong::before {{
      content: "";
      width: 4px;
      height: 4px;
      border-radius: 50%;
      background: var(--accent);
      position: absolute;
      left: -8px;
      top: 7px;
    }}
    .calendar-wrap {{
      position: relative;
    }}
    .calendar-button {{
      width: 30px;
      height: 30px;
      border: 1px solid var(--line);
      color: #777777;
      display: grid;
      place-items: center;
      background: #ffffff;
    }}
    .calendar-button svg {{
      width: 15px;
      height: 15px;
      stroke: currentColor;
      stroke-width: 1.8;
      fill: none;
    }}
    .calendar-popover {{
      position: absolute;
      top: 38px;
      right: 0;
      z-index: 10;
      width: 260px;
      border: 1px solid var(--line);
      background: #ffffff;
      padding: 16px;
      box-shadow: 0 14px 40px rgba(0, 0, 0, 0.08);
      display: none;
    }}
    .calendar-popover.open {{
      display: block;
    }}
    .calendar-title {{
      margin: 0 0 12px;
      color: #606060;
      font-size: 13px;
    }}
    .calendar-options {{
      display: grid;
      gap: 8px;
      max-height: 180px;
      overflow: auto;
    }}
    .calendar-option {{
      min-height: 34px;
      border: 1px solid var(--line);
      color: #777777;
      background: #ffffff;
      text-align: left;
      padding: 0 10px;
      font-size: 13px;
    }}
    .calendar-option.active {{
      border-color: var(--accent);
      color: #202020;
    }}
    .calendar-confirm {{
      width: 100%;
      min-height: 34px;
      margin-top: 12px;
      border: 1px solid var(--accent);
      color: #202020;
      background: #ffffff;
      font-size: 13px;
    }}
    .content-layout {{
      display: grid;
      gap: 18px;
      align-items: start;
    }}
    .thumbnail-grid {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 10px;
    }}
    .thumb-card {{
      min-height: 86px;
      border: 1px solid var(--line);
      background: #ffffff;
      text-align: left;
      padding: 12px 18px;
      display: grid;
      grid-template-columns: minmax(0, 1fr) 82px;
      gap: 18px;
      align-items: center;
      transition: border-color 0.15s ease, box-shadow 0.15s ease;
    }}
    .thumb-card.active,
    .thumb-card:hover {{
      border-color: var(--accent);
      box-shadow: 0 8px 20px rgba(18, 185, 181, 0.08);
    }}
    .thumb-meta {{
      margin: 0 0 7px;
      color: #969696;
      font-size: 13px;
      line-height: 1.35;
    }}
    .thumb-card h2 {{
      margin: 0;
      color: #202020;
      font-size: 15px;
      line-height: 1.38;
      font-weight: 400;
    }}
    .thumb-desc {{
      margin: 6px 0 0;
      color: #9a9a9a;
      font-size: 13px;
      line-height: 1.5;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }}
    .thumb-art {{
      width: 82px;
      height: 58px;
      display: grid;
      place-items: center;
      color: rgba(32, 32, 32, 0.54);
      font-size: 22px;
      font-weight: 300;
      overflow: hidden;
    }}
    .thumb-art img {{
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }}
    .new-badge {{
      display: inline-grid;
      place-items: center;
      width: 15px;
      height: 15px;
      margin-left: 3px;
      border-radius: 50%;
      background: var(--accent);
      color: #ffffff;
      font-size: 10px;
      font-weight: 700;
      vertical-align: 1px;
    }}
    .detail-panel {{
      position: fixed;
      inset: 0;
      z-index: 20;
      display: none;
      align-items: center;
      justify-content: center;
      background: rgba(255, 255, 255, 0.82);
      padding: 24px;
    }}
    .detail-panel.open {{
      display: flex;
    }}
    .detail-card {{
      width: min(620px, 100%);
      max-height: min(720px, calc(100vh - 48px));
      overflow: auto;
      border: 1px solid var(--line);
      background: #ffffff;
      padding: 26px;
      box-shadow: 0 18px 54px rgba(0, 0, 0, 0.08);
    }}
    .detail-kicker {{
      margin: 0 0 9px;
      color: #969696;
      font-size: 13px;
    }}
    .detail-panel h2 {{
      margin: 0;
      font-size: 18px;
      line-height: 1.55;
      font-weight: 400;
    }}
    .detail-close {{
      float: right;
      width: 28px;
      height: 28px;
      border: 1px solid var(--line);
      color: #888888;
      font-size: 18px;
      line-height: 1;
    }}
    .detail-section {{
      border-top: 1px solid var(--line);
      margin-top: 18px;
      padding-top: 15px;
    }}
    .detail-section h3 {{
      margin: 0 0 7px;
      color: #666666;
      font-size: 13px;
      font-weight: 500;
    }}
    .detail-section p,
    .detail-section li {{
      color: #555555;
      font-size: 13px;
      line-height: 1.65;
    }}
    .detail-section p {{
      margin: 0;
    }}
    .detail-section ul {{
      margin: 0;
      padding-left: 18px;
    }}
    .detail-actions {{
      display: grid;
      gap: 8px;
      margin-top: 18px;
    }}
    .detail-actions a {{
      min-height: 38px;
      border: 1px solid var(--line);
      display: flex;
      align-items: center;
      justify-content: center;
      color: #555555;
      font-size: 13px;
    }}
    .detail-actions a.primary {{
      border-color: var(--accent);
      color: #202020;
    }}
    .empty {{
      grid-column: 1 / -1;
      padding: 40px 20px;
      border: 1px solid var(--line);
      color: var(--muted);
      text-align: center;
      font-size: 14px;
    }}
    @media (max-width: 900px) {{}}
    @media (max-width: 680px) {{
      .page {{
        width: min(100% - 24px, 520px);
        padding-top: 70px;
      }}
      .issue-head {{
        justify-content: flex-start;
      }}
      .calendar-popover {{
        left: 0;
        right: auto;
      }}
      .thumbnail-grid {{
        grid-template-columns: 1fr;
      }}
      .thumb-card {{
        grid-template-columns: minmax(0, 1fr) 64px;
        gap: 14px;
      }}
      .thumb-art {{
        width: 64px;
        height: 64px;
      }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <header class="masthead">
      <h1>요일별 카드뉴스</h1>
      <p>날짜를 선택하고 오늘의 5개 카드뉴스를 확인해 보세요.</p>
    </header>
    <nav class="weekdays" aria-label="요일 선택">
      {render_weekday_buttons(active_weekday)}
    </nav>
    <div class="issue-head">
      <strong id="selectedDate">최신순</strong>
      <div class="calendar-wrap">
        <button class="calendar-button" id="calendarButton" type="button" aria-label="날짜 선택">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <rect x="3.5" y="5" width="17" height="15.5" rx="2"></rect>
            <path d="M7.5 3.5v3M16.5 3.5v3M3.5 9h17"></path>
          </svg>
        </button>
        <div class="calendar-popover" id="calendarPopover" aria-label="날짜 선택 달력">
          <p class="calendar-title">날짜 선택</p>
          <div class="calendar-options" id="calendarOptions"></div>
          <button class="calendar-confirm" id="calendarConfirm" type="button">확인</button>
        </div>
      </div>
      <span id="selectedCount">5개 카드뉴스</span>
    </div>
    <section class="content-layout" aria-label="카드뉴스">
      <div class="thumbnail-grid" id="cardGrid"></div>
    </section>
    <aside class="detail-panel" id="detailPanel" aria-live="polite"></aside>
  </main>
  <script>
    const issues = {data_json};
    let activeWeekday = {active_weekday};
    let activeIssueKey = issues[0]?.key || "";
    let activeCardIndex = -1;
    let pendingIssueKey = activeIssueKey;

    const weekdayButtons = [...document.querySelectorAll(".weekday")];
    const calendarButton = document.getElementById("calendarButton");
    const calendarPopover = document.getElementById("calendarPopover");
    const calendarOptions = document.getElementById("calendarOptions");
    const calendarConfirm = document.getElementById("calendarConfirm");
    const cardGrid = document.getElementById("cardGrid");
    const detailPanel = document.getElementById("detailPanel");
    const selectedDate = document.getElementById("selectedDate");
    const selectedCount = document.getElementById("selectedCount");

    function escapeHtml(value) {{
      return String(value || "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }}

    function currentIssues() {{
      return issues.filter((issue) => issue.weekdayIndex === activeWeekday);
    }}

    function currentIssue() {{
      return issues.find((issue) => issue.key === activeIssueKey) || currentIssues()[0] || issues[0];
    }}

    function setWeekday(index) {{
      activeWeekday = index;
      const filtered = currentIssues();
      activeIssueKey = filtered[0]?.key || issues[0]?.key || "";
      pendingIssueKey = activeIssueKey;
      activeCardIndex = -1;
      render();
    }}

    function setIssue(key) {{
      activeIssueKey = key;
      pendingIssueKey = key;
      const selectedIssue = issues.find((issue) => issue.key === key);
      if (selectedIssue) {{
        activeWeekday = selectedIssue.weekdayIndex;
      }}
      activeCardIndex = -1;
      render();
    }}

    function setCard(index) {{
      activeCardIndex = index;
      renderCards();
      renderDetail();
      detailPanel.classList.add("open");
    }}

    function closeDetail() {{
      detailPanel.classList.remove("open");
    }}

    function renderWeekdays() {{
      weekdayButtons.forEach((button) => {{
        const isActive = Number(button.dataset.weekday) === activeWeekday;
        button.classList.toggle("active", isActive);
      }});
    }}

    function renderCalendar() {{
      const filtered = currentIssues();
      calendarOptions.innerHTML = filtered.length
        ? filtered.map((issue) => `
          <button class="calendar-option ${{issue.key === pendingIssueKey ? "active" : ""}}" type="button" data-key="${{issue.key}}">
            ${{escapeHtml(issue.dateLabel)}} (${{escapeHtml(issue.weekday)}})
          </button>
        `).join("")
        : '<p class="calendar-title">해당 요일 카드뉴스가 없습니다.</p>';

      [...calendarOptions.querySelectorAll(".calendar-option")].forEach((button) => {{
        button.addEventListener("click", () => {{
          pendingIssueKey = button.dataset.key;
          renderCalendar();
        }});
      }});
    }}

    function renderCards() {{
      const issue = currentIssue();
      if (!issue || !issue.cards.length) {{
        cardGrid.innerHTML = '<p class="empty">선택한 날짜에 표시할 카드뉴스가 없습니다.</p>';
        selectedDate.textContent = "카드뉴스 없음";
        selectedCount.textContent = "0개 카드뉴스";
        return;
      }}

      selectedDate.textContent = `${{issue.dateLabel}} (${{issue.weekday}})`;
      selectedCount.textContent = `${{issue.cards.length}}개 카드뉴스`;
      cardGrid.innerHTML = issue.cards.map((card, index) => `
        <button class="thumb-card ${{index === activeCardIndex ? "active" : ""}}" type="button" data-index="${{index}}">
          <div>
            <p class="thumb-meta">${{escapeHtml(card.tier || card.topic || "카드뉴스")}}</p>
            <h2>${{escapeHtml(card.title)}} ${{index === 0 ? '<span class="new-badge">N</span>' : ''}}</h2>
            <p class="thumb-desc">${{escapeHtml((card.summary && card.summary[0]) || card.why || "")}}</p>
          </div>
          <div class="thumb-art" style="background:${{escapeHtml(card.thumbColor)}}">
            ${{card.thumbnailUrl ? `<img src="${{escapeHtml(card.thumbnailUrl)}}" alt="">` : index + 1}}
          </div>
        </button>
      `).join("");

      [...cardGrid.querySelectorAll(".thumb-card")].forEach((button) => {{
        button.addEventListener("click", () => setCard(Number(button.dataset.index)));
      }});
    }}

    function renderDetail() {{
      const issue = currentIssue();
      const card = issue?.cards[activeCardIndex];
      if (!issue || !card) {{
        detailPanel.innerHTML = "";
        return;
      }}

      const summaryItems = (card.summary || [])
        .map((summary) => `<li>${{escapeHtml(summary)}}</li>`)
        .join("");

      detailPanel.innerHTML = `
        <div class="detail-card" role="dialog" aria-modal="true" aria-label="카드뉴스 본문">
          <button class="detail-close" type="button" aria-label="닫기">×</button>
          <p class="detail-kicker">${{escapeHtml(card.topic || card.tier || issue.title)}}</p>
          <h2>${{escapeHtml(card.title)}}</h2>
          <section class="detail-section">
            <h3>간단 설명</h3>
            <ul>${{summaryItems || `<li>${{escapeHtml(card.why || "요약 정보가 없습니다.")}}</li>`}}</ul>
          </section>
          <section class="detail-section">
            <h3>왜 중요한가</h3>
            <p>${{escapeHtml(card.why)}}</p>
          </section>
          <section class="detail-section">
            <h3>내게 적용할 점</h3>
            <p>${{escapeHtml(card.action)}}</p>
          </section>
          <div class="detail-actions">
            <a class="primary" href="${{escapeHtml(issue.href)}}">전체 카드뉴스 보기</a>
            <a href="${{escapeHtml(card.url)}}" target="_blank" rel="noreferrer">원문 기사 보기</a>
          </div>
        </div>
      `;
      detailPanel.querySelector(".detail-close").addEventListener("click", closeDetail);
    }}

    function render() {{
      renderWeekdays();
      renderCalendar();
      renderCards();
      renderDetail();
    }}

    weekdayButtons.forEach((button) => {{
      button.addEventListener("click", () => setWeekday(Number(button.dataset.weekday)));
    }});
    calendarButton.addEventListener("click", () => {{
      pendingIssueKey = activeIssueKey;
      renderCalendar();
      calendarPopover.classList.toggle("open");
    }});
    calendarConfirm.addEventListener("click", () => {{
      if (pendingIssueKey) {{
        setIssue(pendingIssueKey);
      }}
      calendarPopover.classList.remove("open");
    }});
    document.addEventListener("click", (event) => {{
      if (!calendarPopover.contains(event.target) && !calendarButton.contains(event.target)) {{
        calendarPopover.classList.remove("open");
      }}
    }});
    detailPanel.addEventListener("click", (event) => {{
      if (event.target === detailPanel) {{
        closeDetail();
      }}
    }});
    window.addEventListener("keydown", (event) => {{
      if (event.key === "Escape") {{
        closeDetail();
      }}
    }});

    render();
  </script>
</body>
</html>
"""


def main() -> int:
    issues = discover_issues()
    INDEX_PATH.write_text(render_index(issues), encoding="utf-8")
    print(INDEX_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
