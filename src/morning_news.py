from __future__ import annotations

import argparse
import html
import json
import logging
import re
import smtplib
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT_DIR / "config" / "sources.json"
OUTPUT_DIR = ROOT_DIR / "output"
LOG_DIR = ROOT_DIR / "logs"
LOG_PATH = LOG_DIR / "morning-news.log"
DEFAULT_TIMEZONE = "Asia/Seoul"


@dataclass(frozen=True)
class Topic:
    id: str
    label: str
    weight: float
    queries: list[str]
    why_it_matters: str
    action_hint: str


@dataclass
class NewsItem:
    title: str
    url: str
    source: str
    published: datetime | None
    summary: str
    topic: Topic
    score: float
    reasons: list[str]


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=LOG_PATH,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_timezone(timezone_name: str) -> tzinfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        if timezone_name == DEFAULT_TIMEZONE:
            return timezone(timedelta(hours=9), name="KST")
        raise


def build_topics(config: dict[str, Any]) -> list[Topic]:
    return [
        Topic(
            id=topic["id"],
            label=topic["label"],
            weight=float(topic.get("weight", 1.0)),
            queries=list(topic["queries"]),
            why_it_matters=topic["why_it_matters"],
            action_hint=topic["action_hint"],
        )
        for topic in config["topics"]
    ]


def google_news_rss_url(query: str, locale: dict[str, str]) -> str:
    fresh_query = f"{query} when:2d"
    encoded_query = urllib.parse.quote(fresh_query)
    return (
        "https://news.google.com/rss/search?"
        f"q={encoded_query}&hl={locale['hl']}&gl={locale['gl']}&ceid={locale['ceid']}"
    )


def fetch_url(url: str, timeout_seconds: int = 15) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "MorningInsightCards/1.0 (+local personal briefing)",
            "Accept": "application/rss+xml, application/xml, text/xml",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return response.read()


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def parse_source(item: ElementTree.Element, title: str) -> str:
    source = item.find("source")
    if source is not None and source.text:
        return clean_text(source.text)
    if " - " in title:
        return clean_text(title.rsplit(" - ", 1)[-1])
    return "Google News"


def parse_published(item: ElementTree.Element) -> datetime | None:
    published = item.findtext("pubDate")
    if not published:
        return None
    try:
        return parsedate_to_datetime(published)
    except (TypeError, ValueError):
        return None


def is_fresh_article(published: datetime | None, generated_at: datetime) -> bool:
    if published is None:
        return False

    local_published = published.astimezone()
    generated_date = generated_at.astimezone().date()
    allowed_dates = {generated_date, generated_date - timedelta(days=1)}
    return local_published.date() in allowed_dates


def source_domain(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    hostname = parsed.hostname or ""
    return hostname.removeprefix("www.").lower()


def is_trusted_source(source: str, url: str, trusted_domains: list[str]) -> bool:
    combined = f"{source} {source_domain(url)}".lower()
    return any(domain.lower() in combined for domain in trusted_domains)


def calculate_score(
    title: str,
    summary: str,
    topic: Topic,
    source: str,
    url: str,
    trusted_domains: list[str],
) -> tuple[float, list[str]]:
    score = 10.0 * topic.weight
    reasons = [f"{topic.label} 주제 적합"]
    text = f"{title} {summary}".lower()

    work_terms = ["결제", "정산", "수수료", "정책", "플랫폼", "커머스", "서비스", "자동화"]
    market_terms = ["투자", "규제", "금리", "시장", "전략", "성장", "실적", "인수"]

    work_hits = sum(1 for term in work_terms if term.lower() in text)
    market_hits = sum(1 for term in market_terms if term.lower() in text)
    if work_hits:
        score += min(work_hits, 3) * 1.8
        reasons.append("업무 적용성 높음")
    if market_hits:
        score += min(market_hits, 3) * 1.2
        reasons.append("시장 흐름 참고")
    if is_trusted_source(source, url, trusted_domains):
        score += 2.5
        reasons.append("선호 출처")

    return score, reasons


def parse_rss_items(
    rss_bytes: bytes,
    topic: Topic,
    trusted_domains: list[str],
    blocked_terms: list[str],
    generated_at: datetime,
) -> list[NewsItem]:
    root = ElementTree.fromstring(rss_bytes)
    items: list[NewsItem] = []

    for item in root.findall("./channel/item"):
        title = clean_text(item.findtext("title", ""))
        url = clean_text(item.findtext("link", ""))
        summary = clean_text(item.findtext("description", ""))
        if not title or not url:
            continue
        if any(term in f"{title} {summary}" for term in blocked_terms):
            continue

        source = parse_source(item, title)
        published = parse_published(item)
        if not is_fresh_article(published, generated_at):
            continue

        score, reasons = calculate_score(title, summary, topic, source, url, trusted_domains)
        items.append(
            NewsItem(
                title=title,
                url=url,
                source=source,
                published=published,
                summary=summary,
                topic=topic,
                score=score,
                reasons=reasons,
            )
        )

    return items


def collect_news(config: dict[str, Any], generated_at: datetime) -> list[NewsItem]:
    topics = build_topics(config)
    locale = config["locale"]
    trusted_domains = list(config.get("trusted_domains", []))
    blocked_terms = list(config.get("blocked_terms", []))
    collected: list[NewsItem] = []

    for topic in topics:
        for query in topic.queries:
            url = google_news_rss_url(query, locale)
            try:
                rss_bytes = fetch_url(url)
                collected.extend(
                    parse_rss_items(
                        rss_bytes,
                        topic,
                        trusted_domains,
                        blocked_terms,
                        generated_at,
                    )
                )
                logging.info("Fetched query=%s topic=%s", query, topic.id)
            except Exception as exc:
                logging.warning("Failed query=%s topic=%s error=%s", query, topic.id, exc)

    return collected


def normalize_title(title: str) -> str:
    title = re.sub(r"\s+-\s+[^-]+$", "", title)
    title = re.sub(r"\s+", " ", title).strip().lower()
    return title


def select_news(items: list[NewsItem], daily_count: int) -> list[NewsItem]:
    deduped: dict[str, NewsItem] = {}
    for item in items:
        key = normalize_title(item.title)
        if key not in deduped or item.score > deduped[key].score:
            deduped[key] = item

    selected: list[NewsItem] = []
    used_topics: set[str] = set()
    ranked = sorted(
        deduped.values(),
        key=lambda item: (
            item.score,
            item.published.timestamp() if item.published else 0,
        ),
        reverse=True,
    )

    for item in ranked:
        if len(selected) >= daily_count:
            break
        if item.topic.id in used_topics and len(used_topics) < min(daily_count, 5):
            continue
        selected.append(item)
        used_topics.add(item.topic.id)

    for item in ranked:
        if len(selected) >= daily_count:
            break
        if item not in selected:
            selected.append(item)

    return selected


def split_summary(summary: str) -> list[str]:
    if not summary:
        return ["원문 링크에서 핵심 내용을 확인하세요."]
    sentences = re.split(r"(?<=[.!?。])\s+|(?<=다\.)\s+", summary)
    cleaned = [sentence.strip(" -") for sentence in sentences if sentence.strip(" -")]
    if not cleaned:
        cleaned = [summary]
    return cleaned[:3]


def format_date(value: datetime | None) -> str:
    if not value:
        return "발행일 확인 필요"
    return value.strftime("%Y.%m.%d %H:%M")


def render_card(item: NewsItem, index: int, core_count: int) -> str:
    tier = "핵심" if index <= core_count else "참고"
    summary_items = "\n".join(
        f"<li>{html.escape(sentence)}</li>" for sentence in split_summary(item.summary)
    )
    reasons = " · ".join(dict.fromkeys(item.reasons))

    return f"""
        <article class="news-card">
          <div class="card-topline">
            <span class="tier">{tier} {index}</span>
            <span class="topic">{html.escape(item.topic.label)}</span>
          </div>
          <h2>{html.escape(item.title)}</h2>
          <ul class="summary-list">
            {summary_items}
          </ul>
          <section>
            <h3>왜 중요한가</h3>
            <p>{html.escape(item.topic.why_it_matters)}</p>
          </section>
          <section>
            <h3>내게 적용할 점</h3>
            <p>{html.escape(item.topic.action_hint)}</p>
          </section>
          <footer>
            <span>{html.escape(item.source)} · {format_date(item.published)}</span>
            <span>{html.escape(reasons)}</span>
            <a href="{html.escape(item.url)}" target="_blank" rel="noreferrer">원문 보기</a>
          </footer>
        </article>
    """


def render_html(items: list[NewsItem], config: dict[str, Any], generated_at: datetime) -> str:
    core_count = int(config.get("core_card_count", 3))
    cards = "\n".join(render_card(item, index + 1, core_count) for index, item in enumerate(items))
    topic_labels = " · ".join(topic["label"] for topic in config["topics"])
    date_label = generated_at.strftime("%Y.%m.%d %A %H:%M")

    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Morning Insight Cards - {generated_at.strftime("%Y-%m-%d")}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --ink: #16181d;
      --muted: #667085;
      --line: #d8dde6;
      --panel: #ffffff;
      --accent: #176b87;
      --accent-2: #8a5a00;
      --soft: #eef7f8;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: "Segoe UI", "Malgun Gothic", Arial, sans-serif;
      line-height: 1.55;
    }}
    .page {{
      width: min(1120px, calc(100% - 32px));
      margin: 0 auto;
      padding: 36px 0 48px;
    }}
    header {{
      border-bottom: 1px solid var(--line);
      padding-bottom: 24px;
      margin-bottom: 24px;
    }}
    .eyebrow {{
      color: var(--accent);
      font-size: 14px;
      font-weight: 700;
      margin: 0 0 8px;
    }}
    h1 {{
      font-size: 34px;
      line-height: 1.2;
      margin: 0 0 12px;
      letter-spacing: 0;
    }}
    .brief {{
      color: var(--muted);
      margin: 0;
      max-width: 860px;
    }}
    .meta-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 18px;
    }}
    .meta-pill {{
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 999px;
      color: #344054;
      font-size: 13px;
      padding: 7px 11px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
    }}
    .news-card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 22px;
      min-height: 420px;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }}
    .news-card:first-child {{
      grid-column: 1 / -1;
      min-height: 360px;
      background: var(--soft);
      border-color: #b8dadd;
    }}
    .card-topline {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      color: var(--muted);
      font-size: 13px;
      font-weight: 700;
    }}
    .tier {{
      color: var(--accent);
    }}
    .topic {{
      color: var(--accent-2);
      text-align: right;
    }}
    h2 {{
      font-size: 22px;
      line-height: 1.35;
      margin: 0;
      letter-spacing: 0;
    }}
    .summary-list {{
      margin: 0;
      padding-left: 20px;
      color: #303642;
    }}
    section {{
      border-top: 1px solid var(--line);
      padding-top: 14px;
    }}
    h3 {{
      font-size: 14px;
      margin: 0 0 6px;
      color: #344054;
      letter-spacing: 0;
    }}
    p {{
      margin: 0;
      color: #3f4652;
    }}
    footer {{
      border-top: 1px solid var(--line);
      margin-top: auto;
      padding-top: 14px;
      display: grid;
      gap: 8px;
      color: var(--muted);
      font-size: 13px;
    }}
    a {{
      color: var(--accent);
      font-weight: 700;
      text-decoration: none;
    }}
    a:hover {{
      text-decoration: underline;
    }}
    .empty {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 28px;
      color: var(--muted);
    }}
    @media (max-width: 760px) {{
      .page {{
        width: min(100% - 20px, 640px);
        padding-top: 24px;
      }}
      h1 {{
        font-size: 27px;
      }}
      .grid {{
        grid-template-columns: 1fr;
      }}
      .news-card:first-child {{
        grid-column: auto;
      }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <header>
      <p class="eyebrow">Morning Insight Cards</p>
      <h1>오늘의 핵심 뉴스 5개</h1>
      <p class="brief">업무 적용성 60%, 시장 흐름 40% 기준으로 선별한 개인용 아침 브리핑입니다.</p>
      <div class="meta-row">
        <span class="meta-pill">생성: {html.escape(date_label)}</span>
        <span class="meta-pill">주제: {html.escape(topic_labels)}</span>
        <span class="meta-pill">구성: 핵심 3개 + 참고 2개</span>
      </div>
    </header>
    <section class="grid">
      {cards if cards else '<div class="empty">수집된 뉴스가 없습니다. 네트워크 연결과 logs/morning-news.log를 확인하세요.</div>'}
    </section>
  </main>
</body>
</html>
"""


def write_html(content: str, generated_at: datetime) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"morning-insight-cards-{generated_at.strftime('%Y-%m-%d')}.html"
    output_path.write_text(content, encoding="utf-8")
    return output_path


def required_env(name: str) -> str:
    value = os_environ_get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def os_environ_get(name: str) -> str:
    import os

    return os.environ.get(name, "").strip()


def send_email(html_content: str, output_path: Path, generated_at: datetime) -> None:
    smtp_host = required_env("SMTP_HOST")
    smtp_user = required_env("SMTP_USER")
    smtp_password = required_env("SMTP_PASSWORD")
    email_from = required_env("EMAIL_FROM")
    email_to = required_env("EMAIL_TO")
    smtp_port = int(os_environ_get("SMTP_PORT") or "587")
    use_tls = (os_environ_get("SMTP_USE_TLS") or "true").lower() not in {"0", "false", "no"}

    date_label = generated_at.strftime("%Y-%m-%d")
    message = MIMEMultipart("mixed")
    message["Subject"] = f"Morning Insight Cards - {date_label}"
    message["From"] = email_from
    message["To"] = email_to

    alternative = MIMEMultipart("alternative")
    alternative.attach(
        MIMEText(
            "Morning Insight Cards HTML briefing is attached. Open this email in an HTML-capable client for the full view.",
            "plain",
            "utf-8",
        )
    )
    alternative.attach(MIMEText(html_content, "html", "utf-8"))
    message.attach(alternative)

    attachment = MIMEApplication(output_path.read_bytes(), _subtype="html")
    attachment.add_header("Content-Disposition", "attachment", filename=output_path.name)
    message.attach(attachment)

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        if use_tls:
            server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(message)

    logging.info("Email sent to %s via %s", email_to, smtp_host)


def is_weekday(value: datetime) -> bool:
    return value.weekday() < 5


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Morning Insight Cards HTML.")
    parser.add_argument("--force", action="store_true", help="Run even on weekends.")
    parser.add_argument("--email", action="store_true", help="Send generated HTML by SMTP email.")
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE, help="Generation timezone. Default: Asia/Seoul.")
    args = parser.parse_args()

    setup_logging()
    now = datetime.now(load_timezone(args.timezone))
    if not args.force and not is_weekday(now):
        logging.info("Skipped weekend run")
        print("Weekend run skipped. Use --force to generate anyway.")
        return 0

    try:
        config = load_config()
        items = collect_news(config, now)
        daily_count = int(config.get("daily_card_count", 5))
        selected = select_news(items, daily_count)
        html_content = render_html(selected, config, now)
        output_path = write_html(html_content, now)
        logging.info("Generated %s with %s cards from %s collected items", output_path, len(selected), len(items))
        if len(selected) < daily_count:
            logging.error("Only %s/%s cards generated", len(selected), daily_count)
            print(f"Only {len(selected)}/{daily_count} cards generated. Check log: {LOG_PATH}", file=sys.stderr)
            return 2
        if args.email:
            send_email(html_content, output_path, now)
        print(output_path)
        return 0
    except Exception as exc:
        logging.exception("Generation failed: %s", exc)
        print(f"Generation failed. Check log: {LOG_PATH}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
