#!/usr/bin/env bash
set -Eeuo pipefail

# Restrict only the application/browser container. Replies to inbound Caddy
# connections are allowed; new connections to private/link-local ranges are dropped.
IPTABLES="${IPTABLES:-iptables}"
APP_IP="${APP_IP:-172.30.0.3}"
FILTER_CHAIN="RB-APP-EGRESS"
PARENT_CHAIN="DOCKER-USER"

if ! command -v "$IPTABLES" >/dev/null 2>&1; then
    echo "iptables is required" >&2
    exit 1
fi

for _ in $(seq 1 30); do
    if "$IPTABLES" -nL "$PARENT_CHAIN" >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

if ! "$IPTABLES" -nL "$PARENT_CHAIN" >/dev/null 2>&1; then
    echo "Docker chain $PARENT_CHAIN is not available" >&2
    exit 1
fi

"$IPTABLES" -N "$FILTER_CHAIN" 2>/dev/null || true
"$IPTABLES" -F "$FILTER_CHAIN"
"$IPTABLES" -A "$FILTER_CHAIN" -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN

for cidr in \
    0.0.0.0/8 \
    10.0.0.0/8 \
    100.64.0.0/10 \
    127.0.0.0/8 \
    169.254.0.0/16 \
    172.16.0.0/12 \
    192.0.0.0/24 \
    192.0.2.0/24 \
    192.88.99.0/24 \
    192.168.0.0/16 \
    198.18.0.0/15 \
    198.51.100.0/24 \
    203.0.113.0/24 \
    224.0.0.0/4 \
    240.0.0.0/4; do
    "$IPTABLES" -A "$FILTER_CHAIN" -d "$cidr" -j DROP
done

# App callbacks (Discord OAuth2) and approved site checks use TCP 80/443 only.
# Chromium QUIC is disabled; all other new protocols/ports are dropped.
"$IPTABLES" -A "$FILTER_CHAIN" -p tcp -m multiport --dports 80,443 -j RETURN
"$IPTABLES" -A "$FILTER_CHAIN" -j DROP

if ! "$IPTABLES" -C "$PARENT_CHAIN" -s "$APP_IP/32" -j "$FILTER_CHAIN" 2>/dev/null; then
    "$IPTABLES" -I "$PARENT_CHAIN" 1 -s "$APP_IP/32" -j "$FILTER_CHAIN"
fi

echo "Applied browser egress filter for $APP_IP"
