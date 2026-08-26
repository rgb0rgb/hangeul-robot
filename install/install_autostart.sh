#!/usr/bin/env bash
# 컴퓨터를 켜면 콘솔이 저절로 뜨게 한다 (systemd)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
sudo tee /etc/systemd/system/hangeul-console.service >/dev/null <<UNIT
[Unit]
Description=Hangeul Robot Console
After=network.target

[Service]
Type=simple
WorkingDirectory=$ROOT
ExecStart=$ROOT/run.sh
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now hangeul-console
echo "등록 완료. 상태 보기: systemctl status hangeul-console"
