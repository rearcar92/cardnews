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
    thumbnail_url: str
    source_urls: list[str]
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


def naver_news_search_url(query: str) -> str:
    encoded_query = urllib.parse.urlencode(
        {
            "query": query,
            "display": "20",
            "start": "1",
            "sort": "date",
        }
    )
    return f"https://openapi.naver.com/v1/search/news.json?{encoded_query}"


def naver_image_search_url(query: str) -> str:
    encoded_query = urllib.parse.urlencode(
        {
            "query": query,
            "display": "5",
            "start": "1",
            "sort": "sim",
            "filter": "medium",
        }
    )
    return f"https://openapi.naver.com/v1/search/image?{encoded_query}"


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


def fetch_json_url(url: str, headers: dict[str, str], timeout_seconds: int = 15) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "MorningInsightCards/1.0 (+local personal briefing)",
            "Accept": "application/json",
            **headers,
        },
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return json.loads(response.read().decode(charset, errors="ignore"))


def fetch_html_url(url: str, timeout_seconds: int = 8) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "MorningInsightCards/1.0 (+local personal briefing)",
            "Accept": "text/html,application/xhtml+xml,image/avif,image/webp,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="ignore")


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def naver_headers() -> dict[str, str] | None:
    client_id = os_environ_get("NAVER_CLIENT_ID")
    client_secret = os_environ_get("NAVER_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None
    return {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }


def extract_thumbnail_url(value: str, item: ElementTree.Element | None = None) -> str:
    if item is not None:
        for child in item.iter():
            tag = child.tag.lower()
            image_url = child.attrib.get("url", "").strip()
            image_type = child.attrib.get("type", "").lower()
            if image_url and (
                tag.endswith("thumbnail")
                or tag.endswith("content")
                or tag.endswith("image")
                or image_type.startswith("image/")
            ):
                return html.unescape(image_url)

    patterns = [
        r'<img[^>]+src=["\']([^"\']+)["\']',
        r'<media:thumbnail[^>]+url=["\']([^"\']+)["\']',
        r'<media:content[^>]+url=["\']([^"\']+)["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, value, flags=re.IGNORECASE)
        if match:
            return html.unescape(match.group(1)).strip()
    return ""


def extract_article_urls(value: str) -> list[str]:
    urls: list[str] = []
    for match in re.finditer(r'href=["\']([^"\']+)["\']', value, flags=re.IGNORECASE):
        url = html.unescape(match.group(1)).strip()
        domain = source_domain(url)
        if not url.startswith(("http://", "https://")):
            continue
        if domain.endswith("google.com") or domain.endswith("google.co.kr"):
            continue
        if url not in urls:
            urls.append(url)
    return urls


def is_generic_thumbnail_url(url: str) -> bool:
    if not url:
        return True
    parsed = urllib.parse.urlparse(url)
    hostname = (parsed.hostname or "").lower()
    return hostname == "lh3.googleusercontent.com" and "J6_coFbogxhRI9iM864NL_liGXvsQp2AupsKei7z0cNNfDvGUmWUy20nuUhkREQyrpY4bEeIBuc" in url


def extract_html_thumbnail_url(value: str, base_url: str = "") -> str:
    patterns = [
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',
        r'<link[^>]+rel=["\']image_src["\'][^>]+href=["\']([^"\']+)["\']',
        r'<link[^>]+href=["\']([^"\']+)["\'][^>]+rel=["\']image_src["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, value, flags=re.IGNORECASE)
        if match:
            image_url = html.unescape(match.group(1)).strip()
            if base_url:
                image_url = urllib.parse.urljoin(base_url, image_url)
            if not is_generic_thumbnail_url(image_url):
                return image_url
    return ""


def thumbnail_query(title: str) -> str:
    return re.sub(r"\s+-\s+[^-]+$", "", title).strip()


def fetch_naver_image_thumbnail(title: str, headers: dict[str, str]) -> str:
    data = fetch_json_url(naver_image_search_url(thumbnail_query(title)), headers, timeout_seconds=8)
    for raw_item in data.get("items", []):
        thumbnail_url = clean_text(str(raw_item.get("thumbnail", "")))
        image_url = clean_text(str(raw_item.get("link", "")))
        for candidate in [thumbnail_url, image_url]:
            if candidate and not is_generic_thumbnail_url(candidate):
                return candidate
    return ""


def enrich_thumbnails(items: list[NewsItem]) -> None:
    headers = naver_headers()
    for item in items:
        if item.thumbnail_url and not is_generic_thumbnail_url(item.thumbnail_url):
            continue

        for url in [*item.source_urls, item.url]:
            try:
                thumbnail_url = extract_html_thumbnail_url(fetch_html_url(url), url)
                if thumbnail_url:
                    item.thumbnail_url = thumbnail_url
                    logging.info("Fetched thumbnail source=%s title=%s", item.source, item.title)
                    break
            except Exception as exc:
                logging.info("Thumbnail unavailable source=%s url=%s error=%s", item.source, url, exc)

        if not item.thumbnail_url and headers:
            try:
                item.thumbnail_url = fetch_naver_image_thumbnail(item.title, headers)
                if item.thumbnail_url:
                    logging.info("Fetched Naver image thumbnail source=%s title=%s", item.source, item.title)
            except Exception as exc:
                logging.info("Naver image thumbnail unavailable source=%s error=%s", item.source, exc)

        if is_generic_thumbnail_url(item.thumbnail_url):
            item.thumbnail_url = ""


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
        raw_summary = item.findtext("description", "")
        summary = clean_text(raw_summary)
        thumbnail_url = extract_thumbnail_url(raw_summary, item)
        source_urls = extract_article_urls(raw_summary)
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
                thumbnail_url=thumbnail_url,
                source_urls=source_urls,
                topic=topic,
                score=score,
                reasons=reasons,
            )
        )

    return items


def parse_naver_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


def parse_naver_items(
    data: dict[str, Any],
    topic: Topic,
    trusted_domains: list[str],
    blocked_terms: list[str],
    generated_at: datetime,
) -> list[NewsItem]:
    items: list[NewsItem] = []

    for raw_item in data.get("items", []):
        title = clean_text(str(raw_item.get("title", "")))
        summary = clean_text(str(raw_item.get("description", "")))
        original_url = clean_text(str(raw_item.get("originallink", "")))
        naver_url = clean_text(str(raw_item.get("link", "")))
        url = original_url or naver_url
        if not title or not url:
            continue
        if any(term in f"{title} {summary}" for term in blocked_terms):
            continue

        published = parse_naver_datetime(str(raw_item.get("pubDate", "")))
        if not is_fresh_article(published, generated_at):
            continue

        source = source_domain(original_url or naver_url) or "Naver News"
        score, reasons = calculate_score(title, summary, topic, source, url, trusted_domains)
        reasons.append("네이버 뉴스")
        source_urls = [candidate for candidate in [original_url, naver_url] if candidate]
        items.append(
            NewsItem(
                title=title,
                url=url,
                source=source,
                published=published,
                summary=summary,
                thumbnail_url="",
                source_urls=list(dict.fromkeys(source_urls)),
                topic=topic,
                score=score + 0.8,
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
    headers = naver_headers()

    for topic in topics:
        for query in topic.queries:
            if headers:
                try:
                    data = fetch_json_url(naver_news_search_url(query), headers)
                    collected.extend(
                        parse_naver_items(
                            data,
                            topic,
                            trusted_domains,
                            blocked_terms,
                            generated_at,
                        )
                    )
                    logging.info("Fetched Naver query=%s topic=%s", query, topic.id)
                except Exception as exc:
                    logging.warning("Failed Naver query=%s topic=%s error=%s", query, topic.id, exc)

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


def normalize_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=False)
    filtered_query = [
        (key, value)
        for key, value in query
        if not key.lower().startswith("utm_") and key.lower() not in {"oc", "fbclid", "gclid"}
    ]
    return urllib.parse.urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/"),
            "",
            urllib.parse.urlencode(filtered_query),
            "",
        )
    )


def previous_output_paths(generated_at: datetime) -> list[Path]:
    if not OUTPUT_DIR.exists():
        return []

    today_key = generated_at.strftime("%Y-%m-%d")
    paths: list[Path] = []
    for path in OUTPUT_DIR.glob("morning-insight-cards-*.html"):
        match = re.search(r"morning-insight-cards-(\d{4}-\d{2}-\d{2})\.html$", path.name)
        if match and match.group(1) < today_key:
            paths.append(path)
    return paths


def load_previous_article_keys(generated_at: datetime) -> tuple[set[str], set[str]]:
    titles: set[str] = set()
    urls: set[str] = set()

    for path in previous_output_paths(generated_at):
        content = path.read_text(encoding="utf-8")
        for match in re.finditer(r"<h2[^>]*>\s*<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", content, re.DOTALL):
            url = html.unescape(match.group(1)).strip()
            title = clean_text(match.group(2))
            if title:
                titles.add(normalize_title(title))
            if url:
                urls.add(normalize_url(url))

    return titles, urls


def select_news(
    items: list[NewsItem],
    daily_count: int,
    previous_titles: set[str] | None = None,
    previous_urls: set[str] | None = None,
) -> list[NewsItem]:
    previous_titles = previous_titles or set()
    previous_urls = previous_urls or set()
    deduped: dict[str, NewsItem] = {}
    for item in items:
        key = normalize_title(item.title)
        url_key = normalize_url(item.url)
        source_url_keys = {normalize_url(url) for url in item.source_urls}
        if key in previous_titles or url_key in previous_urls or source_url_keys.intersection(previous_urls):
            logging.info("Skipped previously published article title=%s source=%s", item.title, item.source)
            continue
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
    escaped_url = html.escape(item.url, quote=True)
    escaped_thumbnail_url = html.escape(item.thumbnail_url, quote=True)
    summary_items = "\n".join(
        f'<li style="margin:0 0 8px 0;color:#303642;">{html.escape(sentence)}</li>'
        for sentence in split_summary(item.summary)
    )
    reasons = " · ".join(dict.fromkeys(item.reasons))

    return f"""
        <article data-thumbnail="{escaped_thumbnail_url}" style="background:#ffffff;border:1px solid #d8dde6;border-radius:8px;padding:22px;margin:0 0 16px 0;">
          <div style="display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:12px;font-size:13px;font-weight:700;">
            <span style="color:#176b87;">{tier} {index}</span>
            <span style="color:#8a5a00;text-align:right;">{html.escape(item.topic.label)}</span>
          </div>
          <h2 style="font-size:21px;line-height:1.35;margin:0 0 14px 0;letter-spacing:0;">
            <a href="{escaped_url}" target="_blank" rel="noreferrer" style="color:#16181d;text-decoration:none;">{html.escape(item.title)}</a>
          </h2>
          <ul style="margin:0 0 18px 0;padding-left:20px;">
            {summary_items}
          </ul>
          <section style="border-top:1px solid #e4e7ec;padding-top:14px;margin-top:4px;">
            <h3 style="font-size:14px;margin:0 0 6px 0;color:#344054;letter-spacing:0;">왜 중요한가</h3>
            <p style="margin:0;color:#3f4652;">{html.escape(item.topic.why_it_matters)}</p>
          </section>
          <section style="border-top:1px solid #e4e7ec;padding-top:14px;margin-top:14px;">
            <h3 style="font-size:14px;margin:0 0 6px 0;color:#344054;letter-spacing:0;">내게 적용할 점</h3>
            <p style="margin:0;color:#3f4652;">{html.escape(item.topic.action_hint)}</p>
          </section>
          <footer style="border-top:1px solid #e4e7ec;margin-top:16px;padding-top:14px;color:#667085;font-size:13px;">
            <div style="margin-bottom:6px;">{html.escape(item.source)} · {format_date(item.published)}</div>
            <div style="margin-bottom:12px;">선정 이유: {html.escape(reasons)}</div>
            <a href="{escaped_url}" target="_blank" rel="noreferrer" style="display:inline-block;background:#176b87;color:#ffffff;text-decoration:none;font-weight:700;border-radius:6px;padding:9px 13px;">원문 보기</a>
            <div style="margin-top:8px;word-break:break-all;">
              <a href="{escaped_url}" target="_blank" rel="noreferrer" style="color:#176b87;text-decoration:underline;">{escaped_url}</a>
            </div>
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
      <p class="brief">업무 적용성 60%, 시장 흐름 40% 기준으로 선별한 개인용 아침 브리핑입니다. 모든 기사는 발송일 당일 또는 전날 발행 기사만 포함합니다.</p>
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
    message = MIMEMultipart("alternative")
    message["Subject"] = f"Morning Insight Cards - {date_label}"
    message["From"] = email_from
    message["To"] = email_to

    message.attach(
        MIMEText(
            "Morning Insight Cards briefing is available in the HTML body of this email.",
            "plain",
            "utf-8",
        )
    )
    message.attach(MIMEText(html_content, "html", "utf-8"))

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
        previous_titles, previous_urls = load_previous_article_keys(now)
        selected = select_news(items, daily_count, previous_titles, previous_urls)
        enrich_thumbnails(selected)
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
