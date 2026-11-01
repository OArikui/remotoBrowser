#!/usr/bin/env bash
set -Eeuo pipefail

# Run as root on a fresh Ubuntu 24.04 ARM64 OCI instance.
if [[ "${EUID}" -ne 0 ]]; then
    echo "Run with sudo: sudo bash deployment/oci/bootstrap.sh" >&2
    exit 1
fi

source /etc/os-release
if [[ "${ID:-}" != "ubuntu" || "${VERSION_ID:-}" != "24.04" ]]; then
    echo "This bootstrap script targets Ubuntu 24.04 LTS." >&2
    exit 1
fi
if [[ "$(dpkg --print-architecture)" != "arm64" ]]; then
    echo "This project deployment is prepared for OCI Ampere A1 (ARM64)." >&2
    exit 1
fi

DEPLOY_USER="${DEPLOY_USER:-ubuntu}"
if ! id "$DEPLOY_USER" >/dev/null 2>&1; then
    echo "Deployment user '$DEPLOY_USER' does not exist." >&2
    exit 1
fi

apt-get update
apt-get install -y ca-certificates curl git gnupg iptables
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

cat >/etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${UBUNTU_CODENAME:-$VERSION_CODENAME}
Components: stable
Architectures: arm64
Signed-By: /etc/apt/keyrings/docker.asc
EOF

apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
usermod -aG docker "$DEPLOY_USER"

install -m 0755 deployment/oci/remotobrowser-egress-filter.sh \
    /usr/local/sbin/remotobrowser-egress-filter.sh
install -m 0644 deployment/oci/remotobrowser-egress-filter.service \
    /etc/systemd/system/remotobrowser-egress-filter.service
systemctl daemon-reload
systemctl enable --now remotobrowser-egress-filter.service

install -d -o "$DEPLOY_USER" -g "$DEPLOY_USER" /opt/remotobrowser
if [[ ! -d /opt/remotobrowser/.git ]]; then
    sudo -u "$DEPLOY_USER" git clone \
        https://github.com/OArikui/remotoBrowser.git /opt/remotobrowser
else
    sudo -u "$DEPLOY_USER" git -C /opt/remotobrowser fetch origin
fi

cat <<EOF

Docker Engine and Compose were installed.
Repository: /opt/remotobrowser
Deployment user: $DEPLOY_USER (added to the docker group; this grants root-equivalent privileges)

Next:
  1. Log out and reconnect so the docker group takes effect.
  2. Create /opt/remotobrowser/.env from .env.example and fill every required value.
  3. Set APP_DOMAIN and BROWSER_ALLOWED_HOSTS to domains you own/manage.
  4. Add OCI ingress rules for TCP 80/443 and TCP 22 only (restrict 22 to your IP).
  5. Configure DNS A record to this VM's public IP.
  6. Run docker compose --env-file .env -f deployment/compose.oci.yaml config
  7. Start using the instructions in docs/oci.md.
EOF
