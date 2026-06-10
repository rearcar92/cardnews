from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT_DIR / "output"
INDEX_PATH = ROOT_DIR / "index.html"
CARD_FILE_PATTERN = re.compile(r"morning-insight-cards-(\d{4}-\d{2}-\d{2})\.html$")
WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]


@dataclass(frozen=True)
class ArchiveEntry:
    date: datetime
    filename: str

    @property
    def href(self) -> str:
        return f"output/{self.filename}"

    @property
    def date_label(self) -> str:
        return self.date.strftime("%Y.%m.%d")

    @property
    def title(self) -> str:
        return f"{self.date.strftime('%m월 %d일')} 브리핑"

    @property
    def series(self) -> str:
        return f"{WEEKDAYS[self.date.weekday()]}요일 카드뉴스"


def discover_entries() -> list[ArchiveEntry]:
    if not OUTPUT_DIR.exists():
        return []

    entries: list[ArchiveEntry] = []
    for path in OUTPUT_DIR.glob("morning-insight-cards-*.html"):
        match = CARD_FILE_PATTERN.match(path.name)
        if not match:
            continue
        entries.append(
            ArchiveEntry(
                date=datetime.strptime(match.group(1), "%Y-%m-%d"),
                filename=path.name,
            )
        )

    return sorted(entries, key=lambda entry: entry.date, reverse=True)


def render_weekday_nav(active_weekday: int) -> str:
    items = []
    for index, label in enumerate(WEEKDAYS):
        active_class = " active" if index == active_weekday else ""
        items.append(f'<span class="weekday{active_class}">{html.escape(label)}</span>')
    return "\n".join(items)


def render_entry(entry: ArchiveEntry, is_latest: bool) -> str:
    badge = '<span class="new-badge">N</span>' if is_latest else ""
    return f"""
      <article class="archive-card">
        <a class="card-link" href="{html.escape(entry.href)}" aria-label="{html.escape(entry.title)} 보기">
          <div class="card-copy">
            <p class="series">{html.escape(entry.series)}</p>
            <h2>{html.escape(entry.title)} {badge}</h2>
            <p class="byline"><em>by</em> Morning Insight Cards</p>
          </div>
          <p class="date-label">{html.escape(entry.date_label)}</p>
        </a>
      </article>
    """


def render_index(entries: list[ArchiveEntry]) -> str:
    active_weekday = entries[0].date.weekday() if entries else datetime.now().weekday()
    archive_body = (
        "\n".join(render_entry(entry, index == 0) for index, entry in enumerate(entries))
        if entries
        else '<p class="empty">아직 보관된 카드뉴스가 없습니다.</p>'
    )

    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>요일별 연재</title>
  <meta name="description" content="매일 발송한 카드뉴스 공개 아카이브">
  <style>
    :root {{
      color-scheme: light;
      --bg: #ffffff;
      --ink: #222222;
      --muted: #9a9a9a;
      --line: #e8e8e8;
      --accent: #13b9b7;
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
    a {{
      color: inherit;
      text-decoration: none;
    }}
    .page {{
      width: min(960px, calc(100% - 32px));
      margin: 0 auto;
      padding: 116px 0 72px;
    }}
    .masthead {{
      text-align: center;
      margin-bottom: 34px;
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
      margin-bottom: 29px;
    }}
    .weekday {{
      display: flex;
      justify-content: center;
      align-items: center;
      height: 38px;
      color: #969696;
      font-size: 14px;
      position: relative;
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
    .sort-row {{
      display: flex;
      justify-content: flex-end;
      gap: 24px;
      margin: 0 0 28px;
      color: #9b9b9b;
      font-size: 13px;
    }}
    .sort-row span:first-child {{
      color: #606060;
      position: relative;
    }}
    .sort-row span:first-child::before {{
      content: "";
      width: 4px;
      height: 4px;
      border-radius: 50%;
      background: var(--accent);
      position: absolute;
      left: -8px;
      top: 7px;
    }}
    .archive-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 20px 20px;
    }}
    .archive-card {{
      min-height: 152px;
      border: 1px solid var(--line);
      background: #ffffff;
    }}
    .card-link {{
      min-height: 152px;
      padding: 21px 20px 19px;
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 18px;
      align-items: start;
    }}
    .series {{
      margin: 0 0 8px;
      color: #969696;
      font-size: 14px;
      line-height: 1.35;
    }}
    .archive-card h2 {{
      margin: 0;
      color: #202020;
      font-size: 16px;
      line-height: 1.65;
      font-weight: 400;
    }}
    .new-badge {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 16px;
      height: 16px;
      margin-left: 3px;
      border-radius: 50%;
      background: var(--accent);
      color: #ffffff;
      font-size: 10px;
      font-weight: 700;
      line-height: 1;
      vertical-align: 1px;
    }}
    .byline {{
      margin: 18px 0 0;
      color: #aaa;
      font-size: 13px;
      line-height: 1.45;
    }}
    .byline em {{
      color: #b8b8b8;
      font-family: Georgia, serif;
      font-style: italic;
    }}
    .date-label {{
      min-width: 86px;
      margin: 0;
      color: #9c9c9c;
      font-size: 13px;
      line-height: 1.4;
      text-align: right;
    }}
    .empty {{
      grid-column: 1 / -1;
      margin: 0;
      padding: 40px 20px;
      border: 1px solid var(--line);
      color: var(--muted);
      text-align: center;
      font-size: 14px;
    }}
    @media (max-width: 760px) {{
      .page {{
        width: min(100% - 24px, 520px);
        padding-top: 72px;
      }}
      .archive-grid {{
        grid-template-columns: 1fr;
      }}
      .sort-row {{
        gap: 18px;
      }}
      .card-link {{
        grid-template-columns: 1fr;
        gap: 14px;
      }}
      .date-label {{
        text-align: left;
      }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <header class="masthead">
      <h1>요일별 연재</h1>
      <p>브런치북 오리지널 연재를 만나 보세요.</p>
    </header>
    <nav class="weekdays" aria-label="요일 목록">
      {render_weekday_nav(active_weekday)}
    </nav>
    <div class="sort-row" aria-label="정렬 옵션">
      <span>최신순</span>
      <span>응원순</span>
      <span>라이킷순</span>
    </div>
    <section class="archive-grid" aria-label="카드뉴스 목록">
      {archive_body}
    </section>
  </main>
</body>
</html>
"""


def main() -> int:
    entries = discover_entries()
    INDEX_PATH.write_text(render_index(entries), encoding="utf-8")
    print(INDEX_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
