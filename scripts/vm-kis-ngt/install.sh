#!/usr/bin/env bash
# K200 야간선물 실시간 데몬 — Lightsail 설치
# - kis_ngt_realtime.py 를 ~/kis_ngt_realtime.py 로 복사
# - systemd service 등록 (kis-ngt-realtime.service)
# - 포트 8766
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET="$HOME/kis_ngt_realtime.py"
SERVICE="/etc/systemd/system/kis-ngt-realtime.service"

cp "$DIR/kis_ngt_realtime.py" "$TARGET"
chmod +x "$TARGET"
echo "✓ scraper: $TARGET"

# .env — 기존 morning/market/kofia 에서 자동 복사 (KIS_APP_KEY/SECRET 있는 곳)
if [ ! -d "$HOME/kis-ngt" ]; then
  mkdir -p "$HOME/kis-ngt"
fi
if [ ! -f "$HOME/kis-ngt/.env" ]; then
  if [ -f "$HOME/morning/.env" ] && grep -q "^KIS_APP_KEY=" "$HOME/morning/.env"; then
    cp "$HOME/morning/.env" "$HOME/kis-ngt/.env"
    echo "✓ ~/morning/.env 복사"
  elif [ -f "$HOME/market/.env" ] && grep -q "^KIS_APP_KEY=" "$HOME/market/.env"; then
    cp "$HOME/market/.env" "$HOME/kis-ngt/.env"
    echo "✓ ~/market/.env 복사"
  else
    echo "⚠️  ~/kis-ngt/.env 에 KIS_APP_KEY/SECRET 직접 설정 필요"
  fi
  chmod 600 "$HOME/kis-ngt/.env" 2>/dev/null || true
fi

# systemd unit
sudo tee "$SERVICE" > /dev/null <<EOF
[Unit]
Description=KIS K200 Night Futures Realtime Bridge (H0MFCNT0)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ec2-user
WorkingDirectory=/home/ec2-user
EnvironmentFile=-/home/ec2-user/kis-ngt/.env
EnvironmentFile=-/home/ec2-user/morning/.env
ExecStart=/usr/bin/python3 /home/ec2-user/kis_ngt_realtime.py
Restart=always
RestartSec=5
StandardOutput=append:/home/ec2-user/kis_ngt_realtime.log
StandardError=append:/home/ec2-user/kis_ngt_realtime.log

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable kis-ngt-realtime.service
sudo systemctl restart kis-ngt-realtime.service

echo ""
echo "✓ 설치 완료"
echo "  service: kis-ngt-realtime.service"
echo "  포트:    8766"
echo "  로그:    tail -f ~/kis_ngt_realtime.log"
echo "  상태:    sudo systemctl status kis-ngt-realtime.service"
