# 보고서 모듈 — VM 인프라 설계 (작성: 2026-06-06)

목표: 모바일 Claude 앱에서 "디스패치 — [종목] 보고서 작성해줘" 한 줄 → 맥북 켜져있을 필요 없이 Oracle Cloud VM이 실행 → 결과가 여비또니 주식봇 대시보드 "보고서" 탭에 실시간 표시.

## 전체 흐름

```
[모바일 Claude 앱]
        ↓ (사용자: "디스패치 — 삼성전자 보고서")
[다리 — 사용자가 골라야 함]
        ↓
[Oracle VM (168.110.125.122)]
        ↓ Claude Agent SDK가 보고서 작성
        ↓ Markdown 파일 → /home/opc/yeobtoni-stock-bot/modules/report/data/
        ↓ 기존 KOFIA 스크립트와 동일한 패턴으로 GitHub Contents API push
[GitHub yeobtoni-stock-bot 리포]
        ↓ Pages 자동 갱신 (~1분)
[사용자 브라우저 / 모바일 — 보고서 탭에 카드 자동 추가]
```

## "다리" 옵션 (사용자가 골라야 함)

모바일 → VM 트리거가 핵심. 3가지 후보:

### A. Telegram 봇 (추천)
- VM에 텔레그램 봇 띄움 (long polling, 메모리 ~50MB)
- 모바일 텔레그램 앱에서 `/report 삼성전자` 보내면 VM이 받아서 SDK 실행
- 장점: 설치 간단, 무료, 응답 알림(보고서 완료시)을 텔레그램으로 푸시 가능
- 단점: 텔레그램 별도 앱 필요

### B. 모바일 Claude의 디스패치가 직접 VM API 호출
- 디스패치 = Anthropic 클라우드에서 실행되는 에이전트라면 직접 VM의 HTTPS endpoint 호출 가능
- VM에 nginx + Cloudflare Tunnel 추가, `/report` endpoint 노출
- 장점: 별도 앱 없음
- 단점: 디스패치가 임의 외부 API 호출 가능한지 확인 필요 (Claude.ai 기능 상세 모름)

### C. GitHub Issue 트리거 (Polling 또는 Actions)
- 모바일 → GitHub 앱에서 Issue 생성 (제목: "보고서 — 삼성전자")
- GitHub Actions이 라벨 보고 VM에 SSH 명령 또는 webhook 발사
- 장점: GitHub 앱 이미 사용 중
- 단점: 응답 알림 따로 만들어야 함, 약간 우회

**추천**: A (Telegram). 사용자 카카오톡/텔레그램 사용 중이면 가장 간단.

## VM 셋업 (Telegram 옵션 기준)

### 1. Claude Agent SDK 설치
```bash
# VM에 SSH
ssh -i ~/Downloads/ssh-key-2026-06-04.key opc@168.110.125.122

# Node 22 LTS 설치 (이미 KOFIA용 있으면 skip)
curl -fsSL https://rpm.nodesource.com/setup_22.x | sudo bash -
sudo dnf install -y nodejs

# Claude Agent SDK
mkdir -p /home/opc/yeobtoni-report
cd /home/opc/yeobtoni-report
npm init -y
npm install @anthropic-ai/claude-agent-sdk node-telegram-bot-api

# Anthropic API key 환경변수
echo "ANTHROPIC_API_KEY=sk-ant-..." >> .env
echo "TELEGRAM_TOKEN=..." >> .env
echo "GITHUB_PAT=ghp_..." >> .env  # KOFIA용 .env에서 재사용
chmod 600 .env
```

### 2. 메모리 점검
- Oracle VM E2.1.Micro = 1GB RAM
- Node + Claude SDK 메모리 사용 ~200-300MB
- KOFIA 스크래퍼 동시 실행시 +100MB
- 여유 600MB → 가벼운 보고서 작성은 OK
- 위험: 보고서 작성 중 SDK가 KIS API + WebSearch + 파일I/O 동시에 → 일시적 700MB 가능. swap 추가 권장:
```bash
sudo fallocate -l 1G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo "/swapfile swap swap defaults 0 0" | sudo tee -a /etc/fstab
```

### 3. Telegram 봇 코드 스켈레톤
```js
// /home/opc/yeobtoni-report/bot.js
require('dotenv').config();
const TelegramBot = require('node-telegram-bot-api');
const { query } = require('@anthropic-ai/claude-agent-sdk');
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const bot = new TelegramBot(process.env.TELEGRAM_TOKEN, { polling: true });
const REPORT_DIR = '/home/opc/yeobtoni-stock-bot/modules/report/data';

bot.onText(/^\/report (.+)/, async (msg, match) => {
  const chatId = msg.chat.id;
  const subject = match[1].trim();
  await bot.sendMessage(chatId, `📊 ${subject} 보고서 작성 시작...`);

  try {
    // Claude SDK로 보고서 생성
    const prompt = `한국 주식 ${subject}에 대한 분석 보고서를 작성해줘.
구조: 1) 종목 개요 2) 최근 주가 흐름 3) 재무 지표 요약 4) 업종 비교 5) 리스크 6) 결론.
WebSearch와 KIS API로 최신 데이터 수집. 결과는 마크다운으로 출력.`;

    let fullText = '';
    for await (const message of query({ prompt })) {
      if (message.type === 'assistant') {
        fullText += message.message.content.map(c => c.text || '').join('');
      }
    }

    // 파일 저장
    const date = new Date().toISOString().slice(0,10);
    const safeName = subject.replace(/[^\w가-힣]/g, '_');
    const filename = `${date}_${safeName}.md`;
    fs.writeFileSync(path.join(REPORT_DIR, filename), fullText);

    // index.json 갱신
    updateIndex(filename, subject, fullText);

    // GitHub push (기존 KOFIA 스크립트 재사용)
    execSync(`cd /home/opc/yeobtoni-stock-bot && bash push-to-github.sh modules/report/data/${filename}`);

    await bot.sendMessage(chatId, `✅ 완료! 대시보드 "보고서" 탭에서 확인 가능합니다.\n파일: ${filename}`);
  } catch (e) {
    await bot.sendMessage(chatId, `❌ 실패: ${e.message}`);
  }
});

function updateIndex(filename, name, content) {
  const indexPath = path.join(REPORT_DIR, 'index.json');
  let arr = [];
  try { arr = JSON.parse(fs.readFileSync(indexPath, 'utf8')); } catch (_) {}
  const summary = content.split('\n').filter(l => l.trim() && !l.startsWith('#')).slice(0,2).join(' ').slice(0, 200);
  arr.unshift({
    file: filename,
    name,
    date: new Date().toISOString().slice(0,10),
    summary,
  });
  // 중복 제거 (같은 file 키)
  const seen = new Set();
  arr = arr.filter(r => seen.has(r.file) ? false : (seen.add(r.file), true));
  fs.writeFileSync(indexPath, JSON.stringify(arr, null, 2));
}

console.log('Telegram 봇 시작');
```

### 4. systemd 서비스로 영구 실행
```ini
# /etc/systemd/system/yeobtoni-report.service
[Unit]
Description=Yeobtoni Report Bot
After=network.target

[Service]
Type=simple
User=opc
WorkingDirectory=/home/opc/yeobtoni-report
ExecStart=/usr/bin/node bot.js
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now yeobtoni-report
```

## 비용 추정
- Anthropic API: 보고서 1건당 ~$0.10~0.30 (Claude Sonnet 기준, WebSearch 포함)
- Telegram: 무료
- Oracle VM: 이미 사용 중, 추가 비용 0

## 보안
- ANTHROPIC_API_KEY는 VM의 .env에만 (chmod 600)
- Telegram 봇은 chat_id whitelist 추가해서 본인만 트리거 가능하게:
```js
const ALLOWED_CHATS = [123456789]; // 이렌 텔레그램 chat_id
if (!ALLOWED_CHATS.includes(msg.chat.id)) return;
```

## 사용자가 결정해야 할 것

1. **다리 선택**: A (Telegram) / B (디스패치 직접 호출) / C (GitHub Issue)
2. **Anthropic API key 발급**: console.anthropic.com에서 발급 후 VM에 저장
3. **(A 선택시) Telegram 봇 토큰**: @BotFather로 생성

위 셋 결정되면 30분 내 셋업 완료 가능.

## 1단계 검증 시나리오

1. 사용자가 텔레그램에서 `/report 삼성전자` 보냄
2. VM 봇이 받음 → "작성 시작" 응답
3. SDK가 Claude Sonnet으로 보고서 작성 (~30초~2분)
4. data/2026-06-06_삼성전자.md 저장
5. push-to-github.sh로 GitHub push
6. ~1분 후 GitHub Pages 갱신
7. 사용자가 대시보드 "보고서" 탭 새로고침 → 카드 표시
8. 카드 클릭 → 본문 렌더링

위 모든 단계가 맥북 무관하게 작동.
