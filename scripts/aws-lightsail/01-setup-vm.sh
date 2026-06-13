#!/bin/bash
# AWS Lightsail (yeobtoni-vm) Amazon Linux 2023 기본 셋업
# 한 번만 실행. dnf update + Python + git + swap 2GB + timezone
set -e

echo "=== 1단계: VM 기본 셋업 시작 ==="

# 1. 시스템 업데이트
sudo dnf update -y

# 2. 기본 패키지
sudo dnf install -y python3 python3-pip git gcc gcc-c++ make wget curl jq tar

# 3. timezone 서울
sudo timedatectl set-timezone Asia/Seoul

# 4. swap 2GB (RAM 2GB 부족 대비)
if ! swapon --show | grep -q swapfile; then
  sudo fallocate -l 2G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
fi

# 5. Python 패키지
pip3 install --user --upgrade pip
pip3 install --user requests pandas python-dotenv

# 6. 결과
echo ""
echo "=========================================="
echo "OS: $(grep PRETTY_NAME /etc/os-release | cut -d= -f2 | tr -d '\"')"
python3 --version
echo "Memory:"
free -h | head -2
echo "Swap:"
swapon --show
echo "Time: $(date)"
echo "=========================================="
echo "✅ 1단계 (VM 기본 셋업) 완료"
