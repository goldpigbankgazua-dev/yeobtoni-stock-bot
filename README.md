# 여비또니 주식봇

RS 스크리너 · CHART 스크리너 · ETF 검색기를 한 화면에서 보는 통합 대시보드.

## 구조

```
index.html   # 탭 + iframe 허브 페이지 (3개 모듈을 통합)
```

내부적으로 3개 외부 모듈을 iframe으로 임베드합니다:

| 탭 | 출처 | 상태 |
|---|---|---|
| RS 스크리너 | `goldpigbankgazua-dev/rs-screener-kr` | ✅ GitHub 푸시됨 |
| CHART 스크리너 | `goldpigbankgazua-dev/chart-screener-kr` (예정) | ⚠️ 새 리포 생성 필요 |
| ETF 검색기 | `goldpigbankgazua-dev/kr-new-listed-etf` | ✅ GitHub 푸시됨 |

URL은 `index.html` 안의 `MODULES` 객체에서 변경 가능합니다.

---

## 1. CHART 스크리너 새 리포 만들기

현재 `/Users/yeob/Documents/Claude/Projects/매일매일 종목찾기/index_눌림목.html` 은 GitHub에 올라가 있지 않습니다. 한 번만 하면 됩니다.

```bash
cd "/Users/yeob/Documents/Claude/Projects/매일매일 종목찾기"

# index_눌림목.html 을 index.html 로 복사 (GitHub Pages가 index.html 을 찾도록)
cp index_눌림목.html index.html

git init
git add .
git commit -m "init chart screener"
git branch -M main
git remote add origin https://github.com/goldpigbankgazua-dev/chart-screener-kr.git
git push -u origin main
```

GitHub에서 [새 리포](https://github.com/new) `chart-screener-kr` 를 먼저 생성한 뒤 위 명령 실행.

리포 → **Settings → Pages → Source: `main` / `(root)` → Save**

생성된 URL: `https://goldpigbankgazua-dev.github.io/chart-screener-kr/`

---

## 2. RS 스크리너 / ETF 검색기 Pages 활성화

이미 푸시되어 있으니 각 리포에서 **Settings → Pages → main / (root)** 만 활성화하면 끝.

- https://goldpigbankgazua-dev.github.io/rs-screener-kr/
- https://goldpigbankgazua-dev.github.io/kr-new-listed-etf/

---

## 3. 허브 페이지 (이 리포) 배포

```bash
cd "/Users/yeob/Documents/Claude/Projects/여비또니 주식봇"

git init
git add .
git commit -m "init yeobtoni hub"
git branch -M main
git remote add origin https://github.com/goldpigbankgazua-dev/yeobtoni-stock-bot.git
git push -u origin main
```

GitHub → `yeobtoni-stock-bot` 리포 생성 → **Settings → Pages → main / (root)**.

접속: `https://goldpigbankgazua-dev.github.io/yeobtoni-stock-bot/`

---

## 4. 커스텀 도메인 (jusikbot.com 처럼 도메인 붙이기)

도메인이 있다면 (예: `yeobtoni.com`):

1. 리포 → **Settings → Pages → Custom domain** 에 도메인 입력
2. 도메인 DNS에 GitHub Pages IP A 레코드 추가:
   ```
   185.199.108.153
   185.199.109.153
   185.199.110.153
   185.199.111.153
   ```
3. `Enforce HTTPS` 체크

---

## 모듈 URL 바꾸기

`index.html` 상단의 이 블록만 수정:

```js
const MODULES = {
  rs:    "https://...",
  chart: "https://...",
  etf:   "https://...",
};
```

다른 URL을 쓰고 싶거나 모듈이 늘어나면 여기서 관리.
