#!/bin/bash
apt update && apt install -y python3 python3-pip python3-venv git
python3 -m venv venv
source venv/bin/activate
pip install aiogram==3.13.1 telethon aiosqlite
cp pubbot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now pubbot
