# Public Cardnews Archive

매일 발송한 `Morning Insight Cards`를 공개 사이트에 날짜별로 누적 보관하는 구조입니다.

## 생성 흐름

1. `src/morning_news.py`가 당일 카드뉴스 HTML을 생성합니다.
2. 결과 파일은 `output/morning-insight-cards-YYYY-MM-DD.html`에 저장됩니다.
3. `src/build_archive.py`가 루트 `index.html`을 갱신합니다.
4. GitHub Actions가 `index.html`과 `output/*.html`을 저장소에 커밋합니다.
5. GitHub Pages가 정적 사이트로 배포합니다.

## 최초 설정

GitHub 저장소에서 `Settings > Pages`로 이동한 뒤, 배포 소스를 `GitHub Actions`로 설정합니다.

이후 평일 오전 8시 실행분은 자동으로 공개 아카이브에 누적됩니다.

## 로컬 실행

아카이브 인덱스만 다시 만들려면 다음 명령을 실행합니다.

```powershell
python .\src\build_archive.py
```

새 카드뉴스를 강제로 생성한 뒤 아카이브까지 갱신하려면 다음 순서로 실행합니다.

```powershell
python .\src\morning_news.py --force
python .\src\build_archive.py
```
