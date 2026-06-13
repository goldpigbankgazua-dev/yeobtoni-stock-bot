# AWS Lightsail (yeobtoni-vm) 인프라 이관 가이드

Oracle Cloud (1GB RAM, OOM) → AWS Lightsail (2GB RAM) 이관.

**VM 정보:**
- IP: `3.38.179.203` (서울)
- 사용자: `ec2-user`
- 키: `~/Downloads/LightsailDefaultKey-ap-northeast-2.pem`
- OS: Amazon Linux 2023

**SSH 접속:**
```
chmod 600 ~/Downloads/LightsailDefaultKey-ap-northeast-2.pem
ssh -i ~/Downloads/LightsailDefaultKey-ap-northeast-2.pem ec2-user@3.38.179.203
```

## 단계별 실행 순서

### 1단계: VM 기본 셋업 (한 번만)
- 스크립트: `01-setup-vm.sh`
- 작업: dnf update, Python/git/build-tools, swap 2GB, timezone, pip 패키지
- 시간: 3-5분

VM 에 들어간 후 실행:
```bash
curl -fsSL https://raw.githubusercontent.com/goldpigbankgazua-dev/yeobtoni-stock-bot/main/scripts/aws-lightsail/01-setup-vm.sh | bash
```

(또는 맥에서 scp 로 복사 후 실행)

### 2단계: KIS 데몬 + Tailscale Funnel
TBD — chart 모듈 실시간 데이터 (kis_realtime.py + WebSocket 영구 URL)

### 3단계: KOFIA 스크래퍼
TBD — market 모듈 예탁금/신용

### 4단계: market/RS scraper (GitHub Actions → VM cron 복귀)
TBD
