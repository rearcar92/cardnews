# Morning Insight Cards

매일 평일 오전 8시에 개인용 핵심 뉴스 카드뉴스 HTML을 생성하는 MVP입니다.
기본 운영 방식은 GitHub Actions에서 생성 후 이메일로 발송하는 구조입니다.

## 목표

- 혼자 보는 아침 브리핑
- 하루 5개 뉴스: 핵심 3개 + 참고 2개
- 기사 기준일: 발송일 당일 또는 전날 발행 기사만 포함
- 주제: PG/결제/정산, 커머스/플랫폼, PM/PO/서비스기획, AI/업무자동화, 경제/스타트업/테크
- 선정 기준: 업무 적용성 60%, 시장 흐름 40%
- 결과물: 이메일 본문에서 바로 읽는 HTML 카드뉴스

## 폴더 구조

- `src/morning_news.py`: 뉴스 수집, 점수화, HTML 생성
- `config/sources.json`: 수집 키워드, 주제, 선호 출처 설정
- `scripts/run_morning_cardnews.ps1`: 매일 실행할 PowerShell 래퍼
- `scripts/register_scheduled_task.ps1`: Windows 작업 스케줄러 등록
- `.github/workflows/morning-insight-cards.yml`: GitHub Actions 자동 발송 워크플로우
- `output/`: 생성된 HTML 저장 위치
- `logs/`: 실행 로그 저장 위치

## GitHub Actions 자동 발송

GitHub Actions가 평일 오전 8시(KST)에 실행되어 HTML 카드뉴스를 이메일 본문으로 발송합니다.
첨부 HTML 파일은 보내지 않고, 백업용 HTML은 GitHub Actions artifact로만 보관합니다.

GitHub의 `Settings > Secrets and variables > Actions > Repository secrets`에 아래 값을 등록하세요.

- `EMAIL_TO`: 받을 이메일 주소
- `EMAIL_FROM`: 보낼 이메일 주소
- `SMTP_HOST`: SMTP 서버 주소
- `SMTP_PORT`: SMTP 포트, 보통 `587`
- `SMTP_USER`: SMTP 로그인 계정
- `SMTP_PASSWORD`: SMTP 비밀번호 또는 앱 비밀번호
- `SMTP_USE_TLS`: 보통 `true`

스케줄은 GitHub Actions가 UTC 기준으로 동작하기 때문에 `0 23 * * 0-4`로 설정되어 있습니다.
이는 한국 시간 기준 월요일부터 금요일 오전 8시에 해당합니다.

수동으로 테스트하려면 GitHub 저장소의 `Actions > Morning Insight Cards > Run workflow`를 실행하세요.
일반 `push`에서는 이메일을 보내지 않고 HTML 생성만 검증합니다.

## 바로 실행

```powershell
python .\src\morning_news.py
```

생성된 파일은 `output\morning-insight-cards-YYYY-MM-DD.html`에 저장됩니다.

주말에도 테스트하려면:

```powershell
python .\src\morning_news.py --force
```

브라우저까지 자동으로 열려면:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_morning_cardnews.ps1 -Open
```

SMTP 환경 변수가 설정되어 있다면 이메일 발송까지 테스트할 수 있습니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_morning_cardnews.ps1 -Force -Email
```

## 작업 스케줄러 등록

로컬 PC에서도 계속 쓰고 싶을 때만 사용하세요. GitHub Actions 방식은 이 단계가 필요 없습니다.

평일 오전 8시에 자동 실행되도록 등록합니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register_scheduled_task.ps1
```

등록 후 Windows 작업 스케줄러에서 `Morning Insight Cards` 작업을 확인할 수 있습니다.

## 설정 변경

뉴스 키워드와 선호 출처는 `config/sources.json`에서 바꿉니다.

- `topics`: 주제별 검색어와 인사이트 문구
- `trusted_domains`: 가중치를 더 줄 출처
- `blocked_terms`: 제외할 키워드
- `daily_card_count`: 하루 카드 개수

## 참고

이 MVP는 Google News RSS를 사용합니다. 회사 네트워크나 지역 설정에 따라 일부 결과가 비거나 지연될 수 있습니다. 실행 실패나 수집 결과는 `logs\morning-news.log`에 기록됩니다.
