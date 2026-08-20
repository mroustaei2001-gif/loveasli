#!/bin/bash
source /root/proxy_bot/secrets.env
COUNT=${1:-20}
QUOTA="5GB"
EXPIRY_DAYS=2
HOST="www.speedtest.net"
IP="91.107.157.255"
PORT=8443
LINK_HOST="91.107.157.255"

EXPIRES=$(date -u -d "+${EXPIRY_DAYS} days" +%Y-%m-%dT%H:%M:%SZ)
mkdir -p /var/lib/mtg
CONF=/root/mtg-multi.config.toml
LINKS=/root/mtg_links.txt

{
  echo "bind-to = \"0.0.0.0:${PORT}\""
  echo "public-ipv4 = \"${IP}\""
  echo "ad-tag = \"${AD_TAG}\""
  echo "usage-state-file = \"/var/lib/mtg/usage.json\""
  echo ""
  echo "[secrets]"
  echo "sponsor = \"${SPONSOR_SECRET}\""
} > "$CONF"

> "$LINKS"

for i in $(seq 1 $COUNT); do
  SEC=$(mtg-multi generate-secret "$HOST" --hex | grep -oE 'ee[0-9a-fA-F]+' | head -1)
  if [ -z "$SEC" ]; then
    SEC=$(mtg generate-secret "$HOST" --hex | grep -oE 'ee[0-9a-fA-F]+' | head -1)
  fi
  if [ -z "$SEC" ]; then echo "❌ خطا در ساخت secret کاربر $i"; exit 1; fi
  echo "user${i} = \"${SEC}\"" >> "$CONF"
  echo "https://t.me/proxy?server=${LINK_HOST}&port=${PORT}&secret=${SEC}" >> "$LINKS"
done

echo "" >> "$CONF"
for i in $(seq 1 $COUNT); do
  echo "[secret-limits.user${i}]" >> "$CONF"
  echo "quota = \"${QUOTA}\"" >> "$CONF"
  echo "expires = \"${EXPIRES}\"" >> "$CONF"
done

systemctl restart mtg-multi
echo "✅ $COUNT پروکسی ساخته شد | expires=$EXPIRES"
