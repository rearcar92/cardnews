const issues = JSON.parse(document.getElementById("archive-data").textContent);
let activeWeekday = window.ARCHIVE_ACTIVE_WEEKDAY ?? new Date().getDay() - 1;
let activeIssueKey = issues[0]?.key || "";
let activeCardIndex = -1;
let pendingIssueKey = activeIssueKey;

const WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"];
const weekdayButtons = [...document.querySelectorAll(".weekday")];
const calendarButton = document.getElementById("calendarButton");
const calendarPopover = document.getElementById("calendarPopover");
const calendarInput = document.getElementById("calendarInput");
const calendarConfirm = document.getElementById("calendarConfirm");
const cardGrid = document.getElementById("cardGrid");
const detailPanel = document.getElementById("detailPanel");
const selectedDate = document.getElementById("selectedDate");
const selectedCount = document.getElementById("selectedCount");

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function currentIssues() {
  return issues.filter((issue) => issue.weekdayIndex === activeWeekday);
}

function currentIssue() {
  return issues.find((issue) => issue.key === activeIssueKey) || null;
}

function todayKey() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function weekdayIndexFromKey(key) {
  if (!key) {
    return activeWeekday;
  }
  const day = new Date(`${key}T00:00:00`).getDay();
  return day === 0 ? 6 : day - 1;
}

function weekdayLabelFromKey(key) {
  return WEEKDAYS[weekdayIndexFromKey(key)] || "";
}

function dateLabelFromKey(key) {
  return key ? key.replaceAll("-", ".") : "날짜 없음";
}

function cardTone(index) {
  return ["mint", "sand", "sky", "lilac", "sage"][index % 5];
}

function topicInitial(card) {
  const value = (card.topic || card.tier || "N").replace(/[0-9\s]/g, "").trim();
  return value ? [...value][0] : "N";
}

function setWeekday(index) {
  activeWeekday = index;
  const filtered = currentIssues();
  activeIssueKey = filtered[0]?.key || "";
  pendingIssueKey = activeIssueKey;
  activeCardIndex = -1;
  render();
}

function setIssue(key) {
  activeIssueKey = key;
  pendingIssueKey = key;
  const selectedIssue = issues.find((issue) => issue.key === key);
  activeWeekday = selectedIssue ? selectedIssue.weekdayIndex : weekdayIndexFromKey(key);
  activeCardIndex = -1;
  render();
}

function setCard(index) {
  activeCardIndex = index;
  renderCards();
  renderDetail();
  detailPanel.classList.add("open");
}

function closeDetail() {
  detailPanel.classList.remove("open");
}

function renderWeekdays() {
  weekdayButtons.forEach((button) => {
    const isActive = Number(button.dataset.weekday) === activeWeekday;
    button.classList.toggle("active", isActive);
  });
}

function renderCalendar() {
  calendarInput.max = todayKey();
  calendarInput.value = pendingIssueKey || activeIssueKey || todayKey();
}

function renderCards() {
  const issue = currentIssue();
  if (!issue || !issue.cards.length) {
    cardGrid.innerHTML = '<p class="empty">해당 요일 카드뉴스가 없습니다.</p>';
    selectedDate.textContent = activeIssueKey
      ? `${dateLabelFromKey(activeIssueKey)} (${weekdayLabelFromKey(activeIssueKey)})`
      : `${WEEKDAYS[activeWeekday]}요일`;
    selectedCount.textContent = "0개 카드뉴스";
    return;
  }

  selectedDate.textContent = `${issue.dateLabel} (${issue.weekday})`;
  selectedCount.textContent = `${issue.cards.length}개 카드뉴스`;
  cardGrid.innerHTML = issue.cards.map((card, index) => `
    <button class="thumb-card tone-${cardTone(index)} ${index === activeCardIndex ? "active" : ""}" type="button" data-index="${index}" style="--reveal-delay:${index * 70}ms">
      <span class="card-index">${String(index + 1).padStart(2, "0")}</span>
      <div class="thumb-copy">
        <p class="thumb-meta">${escapeHtml(card.tier || card.topic || "카드뉴스")}</p>
        <h2>${escapeHtml(card.title)} ${index === 0 ? '<span class="new-badge">N</span>' : ""}</h2>
        <p class="thumb-desc">${escapeHtml((card.summary && card.summary[0]) || card.why || "")}</p>
      </div>
      <div class="thumb-art" style="background:${escapeHtml(card.thumbColor)}">
        <span class="thumb-fallback">${escapeHtml(topicInitial(card))}</span>
        <span class="thumb-number">${String(index + 1).padStart(2, "0")}</span>
        ${card.thumbnailUrl ? `<img src="${escapeHtml(card.thumbnailUrl)}" alt="" loading="lazy" onerror="this.remove()">` : ""}
      </div>
    </button>
  `).join("");

  [...cardGrid.querySelectorAll(".thumb-card")].forEach((button) => {
    button.addEventListener("click", () => setCard(Number(button.dataset.index)));
  });
}

function renderDetail() {
  const issue = currentIssue();
  const card = issue?.cards[activeCardIndex];
  if (!issue || !card) {
    detailPanel.innerHTML = "";
    return;
  }

  const summaryItems = (card.summary || [])
    .map((summary) => `<li>${escapeHtml(summary)}</li>`)
    .join("");

  detailPanel.innerHTML = `
    <div class="detail-card" role="dialog" aria-modal="true" aria-label="카드뉴스 본문">
      <button class="detail-close" type="button" aria-label="닫기">×</button>
      <div class="detail-hero tone-${cardTone(activeCardIndex)}">
        ${card.thumbnailUrl ? `<img src="${escapeHtml(card.thumbnailUrl)}" alt="" onerror="this.remove()">` : ""}
        <span>${escapeHtml(topicInitial(card))}</span>
      </div>
      <p class="detail-kicker">${escapeHtml(card.topic || card.tier || issue.title)}</p>
      <h2>${escapeHtml(card.title)}</h2>
      <section class="detail-section">
        <h3>간단 설명</h3>
        <ul>${summaryItems || `<li>${escapeHtml(card.why || "요약 정보가 없습니다.")}</li>`}</ul>
      </section>
      <section class="detail-section">
        <h3>왜 중요한가</h3>
        <p>${escapeHtml(card.why)}</p>
      </section>
      <section class="detail-section">
        <h3>내게 적용할 점</h3>
        <p>${escapeHtml(card.action)}</p>
      </section>
      <div class="detail-actions">
        <a class="primary" href="${escapeHtml(issue.href)}">전체 카드뉴스 보기</a>
        <a href="${escapeHtml(card.url)}" target="_blank" rel="noreferrer">원문 기사 보기</a>
      </div>
    </div>
  `;
  detailPanel.querySelector(".detail-close").addEventListener("click", closeDetail);
}

function render() {
  renderWeekdays();
  renderCalendar();
  renderCards();
  renderDetail();
}

weekdayButtons.forEach((button) => {
  button.addEventListener("click", () => setWeekday(Number(button.dataset.weekday)));
});

calendarButton.addEventListener("click", () => {
  pendingIssueKey = activeIssueKey;
  renderCalendar();
  calendarPopover.classList.toggle("open");
});

calendarInput.addEventListener("change", () => {
  pendingIssueKey = calendarInput.value;
});

calendarConfirm.addEventListener("click", () => {
  if (pendingIssueKey) {
    if (pendingIssueKey > todayKey()) {
      pendingIssueKey = todayKey();
    }
    setIssue(pendingIssueKey);
  }
  calendarPopover.classList.remove("open");
});

document.addEventListener("click", (event) => {
  if (!calendarPopover.contains(event.target) && !calendarButton.contains(event.target)) {
    calendarPopover.classList.remove("open");
  }
});

detailPanel.addEventListener("click", (event) => {
  if (event.target === detailPanel) {
    closeDetail();
  }
});

window.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeDetail();
  }
});

render();
