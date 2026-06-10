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


@dataclass(frozen=True)
class ArchiveEntry:
    date: datetime
    filename: str
    title: str

    @property
    def href(self) -> str:
        return f"output/{self.filename}"

    @property
    def date_label(self) -> str:
        return self.date.strftime("%Y.%m.%d")


def discover_entries() -> list[ArchiveEntry]:
    if not OUTPUT_DIR.exists():
        return []

    entries: list[ArchiveEntry] = []
    for path in OUTPUT_DIR.glob("morning-insight-cards-*.html"):
        match = CARD_FILE_PATTERN.match(path.name)
        if not match:
            continue
        generated_date = datetime.strptime(match.group(1), "%Y-%m-%d")
        entries.append(
            ArchiveEntry(
                date=generated_date,
                filename=path.name,
                title=f"{generated_date.strftime('%Y.%m.%d')} Morning Insight Cards",
            )
        )

    return sorted(entries, key=lambda entry: entry.date, reverse=True)


def render_entry(entry: ArchiveEntry, is_latest: bool) -> str:
    badge = '<span class="badge">Latest</span>' if is_latest else ""
    return f"""
      <article class="archive-item">
        <div>
          <p class="date">{html.escape(entry.date_label)}</p>
          <h2><a href="{html.escape(entry.href)}">{html.escape(entry.title)}</a></h2>
        </div>
        <a class="open-link" href="{html.escape(entry.href)}" aria-label="{html.escape(entry.title)} 열기">열기</a>
        {badge}
      </article>
    """


def render_index(entries: list[ArchiveEntry]) -> str:
    latest = entries[0] if entries else None
    entry_cards = "\n".join(render_entry(entry, index == 0) for index, entry in enumerate(entries))
    latest_block = (
        f"""
        <section class="latest">
          <div>
            <p class="section-label">Latest briefing</p>
            <h2>{html.escape(latest.title)}</h2>
            <p>가장 최근에 발송된 카드뉴스입니다. 매일 생성되는 HTML을 날짜별로 보관합니다.</p>
          </div>
          <a class="primary-link" href="{html.escape(latest.href)}">최신 카드뉴스 보기</a>
        </section>
        """
        if latest
        else """
        <section class="latest">
          <div>
            <p class="section-label">Latest briefing</p>
            <h2>아직 보관된 카드뉴스가 없습니다.</h2>
            <p>첫 카드뉴스가 생성되면 이곳에 날짜별 아카이브가 자동으로 쌓입니다.</p>
          </div>
        </section>
        """
    )

    archive_body = entry_cards or '<p class="empty">아직 공개할 카드뉴스 파일이 없습니다.</p>'
    updated_at = datetime.now().strftime("%Y.%m.%d %H:%M")

    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Morning Insight Cards Archive</title>
  <meta name="description" content="매일 발송되는 Morning Insight Cards 공개 아카이브">
  <style>
    :root {{
      color-scheme: light;
      --bg: #f5f6f8;
      --ink: #15171c;
      --muted: #606977;
      --line: #d7dde6;
      --panel: #ffffff;
      --accent: #176b87;
      --accent-soft: #e8f4f5;
      --mark: #a45b10;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: "Segoe UI", "Malgun Gothic", Arial, sans-serif;
      line-height: 1.55;
    }}
    a {{
      color: inherit;
      text-decoration: none;
    }}
    a:hover {{
      text-decoration: underline;
    }}
    .page {{
      width: min(1040px, calc(100% - 32px));
      margin: 0 auto;
      padding: 40px 0 56px;
    }}
    header {{
      display: grid;
      gap: 14px;
      margin-bottom: 28px;
    }}
    .eyebrow,
    .section-label {{
      margin: 0;
      color: var(--accent);
      font-size: 14px;
      font-weight: 800;
    }}
    h1 {{
      max-width: 760px;
      margin: 0;
      font-size: clamp(30px, 5vw, 52px);
      line-height: 1.12;
      letter-spacing: 0;
    }}
    .intro {{
      max-width: 760px;
      margin: 0;
      color: var(--muted);
      font-size: 17px;
    }}
    .stats {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 6px;
    }}
    .stat {{
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 999px;
      padding: 7px 12px;
      color: #374151;
      font-size: 13px;
      font-weight: 700;
    }}
    .latest {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 20px;
      align-items: center;
      background: var(--accent-soft);
      border: 1px solid #bad9dd;
      border-radius: 8px;
      padding: 24px;
      margin-bottom: 26px;
    }}
    .latest h2 {{
      margin: 4px 0 8px;
      font-size: 26px;
      letter-spacing: 0;
    }}
    .latest p {{
      margin: 0;
      color: #3c4653;
    }}
    .primary-link,
    .open-link {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 40px;
      border-radius: 6px;
      font-weight: 800;
      white-space: nowrap;
    }}
    .primary-link {{
      background: var(--accent);
      color: #ffffff;
      padding: 0 15px;
    }}
    .archive {{
      display: grid;
      gap: 10px;
    }}
    .archive-title {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: end;
      border-bottom: 1px solid var(--line);
      padding-bottom: 12px;
      margin-bottom: 2px;
    }}
    .archive-title h2 {{
      margin: 0;
      font-size: 22px;
      letter-spacing: 0;
    }}
    .updated {{
      margin: 0;
      color: var(--muted);
      font-size: 13px;
    }}
    .archive-item {{
      position: relative;
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 18px;
      align-items: center;
      min-height: 86px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 17px 18px;
    }}
    .date {{
      margin: 0 0 4px;
      color: var(--mark);
      font-size: 13px;
      font-weight: 800;
    }}
    .archive-item h2 {{
      margin: 0;
      font-size: 19px;
      line-height: 1.35;
      letter-spacing: 0;
    }}
    .open-link {{
      border: 1px solid var(--line);
      color: var(--accent);
      padding: 0 12px;
    }}
    .badge {{
      position: absolute;
      top: 10px;
      right: 72px;
      color: var(--accent);
      font-size: 12px;
      font-weight: 900;
    }}
    .empty {{
      margin: 0;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 20px;
      color: var(--muted);
    }}
    @media (max-width: 720px) {{
      .page {{
        width: min(100% - 22px, 640px);
        padding-top: 26px;
      }}
      .latest,
      .archive-item {{
        grid-template-columns: 1fr;
      }}
      .primary-link,
      .open-link {{
        width: 100%;
      }}
      .archive-title {{
        display: grid;
      }}
      .badge {{
        right: 18px;
      }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <header>
      <p class="eyebrow">Morning Insight Cards Archive</p>
      <h1>매일 아침 쌓이는 결제, 정산, PM 인사이트</h1>
      <p class="intro">업무에 바로 적용할 뉴스와 시장 흐름을 날짜별로 보관하는 공개 아카이브입니다.</p>
      <div class="stats">
        <span class="stat">총 {len(entries)}개 브리핑</span>
        <span class="stat">평일 오전 8시 기준</span>
        <span class="stat">공개 아카이브</span>
      </div>
    </header>
    {latest_block}
    <section class="archive" aria-labelledby="archive-heading">
      <div class="archive-title">
        <h2 id="archive-heading">전체 카드뉴스</h2>
        <p class="updated">마지막 갱신: {html.escape(updated_at)}</p>
      </div>
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
