#!/bin/bash

echo "======================================"
echo "KStockDB 자가 복구 서비스 설치 스크립트"
echo "======================================"

# 현재 접속한 유저명 (보통 ubuntu)
USER_NAME=$(whoami)
# 현재 디렉토리 (보통 /home/ubuntu/KStockDB)
WORK_DIR=$(pwd)

echo "[1] kstockdb.service 템플릿 생성 중..."
cat > kstockdb.service << EOF
[Unit]
Description=Korean Stock Database Auto Updater Scheduler
After=network.target

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$WORK_DIR
ExecStart=/usr/bin/python3 $WORK_DIR/main.py
Restart=always
RestartSec=5
# 만약 .env 파일이 존재하면 읽어옵니다.
EnvironmentFile=-$WORK_DIR/.env

[Install]
WantedBy=multi-user.target
EOF

echo "[2] systemd 서비스 등록 및 활성화..."
sudo cp kstockdb.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable kstockdb.service
sudo systemctl restart kstockdb.service

echo "[3] 상태 확인..."
sudo systemctl status kstockdb.service --no-pager

echo "======================================"
echo "설치가 완료되었습니다!"
echo "실시간 로그를 보시려면 아래 명령어를 입력하세요:"
echo "sudo journalctl -u kstockdb.service -f"
echo "======================================"
