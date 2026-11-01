# Oracle Cloud Infrastructure (OCI) deployment

This deployment targets **OCI Ampere A1 / Ubuntu 24.04 LTS / ARM64**. It runs FastAPI and the controlled Chromium test browser in one application container, with Caddy providing HTTPS. The browser can connect only to the exact hostnames listed in `BROWSER_ALLOWED_HOSTS`; only add domains that you own or are explicitly authorized to test.

The OCI Always Free A1 allowance is currently equivalent to 2 OCPUs and 12 GB RAM per tenancy. The 200 GB Always Free block-volume allowance includes boot volumes. Availability and eligibility are controlled by OCI and can vary by home region and capacity. See the official [Always Free resources](https://docs.oracle.com/ja-jp/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm).

## 1. Create the OCI VM

1. Use an OCI account that is eligible to create and manage the resources. Account registration, payment verification, and billing settings must be handled by an eligible account holder with the required adult supervision.
2. In the tenancy's **home region**, create a VM using `VM.Standard.A1.Flex`.
3. Select **Ubuntu 24.04 Minimal, ARM64/aarch64**.
4. Allocate at most **2 OCPUs and 12 GB RAM** in total for Always Free use. Start with a single VM using both allocations; one browser session is the intended initial limit.
5. Keep the boot volume at its default 50 GB unless there is a measured reason to increase it. The free 200 GB storage allowance is shared by boot and block volumes.
6. Configure an SSH key pair and keep the private key on the administrator's device.

If OCI reports an out-of-capacity error for A1, the selected region or availability domain may not currently have capacity. Do not switch to a paid shape without reviewing billing first.

## 2. Configure networking and DNS

Create or use a VCN with a public subnet, Internet Gateway, and a route for `0.0.0.0/0` to the Internet Gateway. Attach a Network Security Group (recommended) or security list with these **ingress** rules:

| Protocol | Port | Source | Purpose |
|---|---:|---|---|
| TCP | 22 | Your current public IP `/32` only | SSH administration |
| TCP | 80 | `0.0.0.0/0` | Caddy ACME HTTP challenge / redirect |
| TCP | 443 | `0.0.0.0/0` | HTTPS and WebSocket access |

Do not add public ingress rules for port 8080, VNC 5900+, or X11. They are not published by the Compose file. Keep egress rules sufficient for DNS, HTTPS, OS updates, and the controlled test sites; the application-container `DOCKER-USER` filter described below blocks private and link-local destination ranges.

Create an `A` record such as `browser.example.org` pointing to the VM public IPv4 address. Do not publish an `AAAA` record unless IPv6 is configured and tested end-to-end. Caddy will request and renew the TLS certificate automatically once DNS and inbound TCP 80/443 are working.

## 3. Install Docker Engine and the container egress filter

Connect through SSH, then clone the public repository and run the bootstrap script:

```bash
git clone https://github.com/OArikui/remotoBrowser.git /opt/remotobrowser
cd /opt/remotobrowser
sudo bash deployment/oci/bootstrap.sh
```

The script checks Ubuntu 24.04 and ARM64, installs Docker Engine and the Compose plugin from Docker's official APT repository, and installs the `DOCKER-USER` filter as a systemd service. It adds the deployment user to the `docker` group; membership in that group is effectively root-level access, so keep SSH access restricted.

Log out and reconnect once so the group membership takes effect. Verify:

```bash
docker version
docker compose version
sudo systemctl status remotobrowser-egress-filter.service
sudo iptables -S DOCKER-USER
sudo iptables -S RB-APP-EGRESS
```

The filter is tied to the static app address `172.30.0.3` in `compose.oci.yaml`. Ensure `172.30.0.0/24` does not overlap your VCN or another host route. It drops new IPv4 connections from the app/browser container to private, loopback, link-local, carrier-grade NAT, and reserved ranges; it then allows only new TCP connections to ports 80/443 and drops other new protocols/ports. Established reply packets are retained so Caddy can reach the app. Chromium QUIC is disabled and IPv6 is disabled on the Compose bridge. **This host firewall is not an FQDN allowlist**: it blocks destination address classes and non-web ports, while the application layer checks HTTP(S) requests and WebSockets against `BROWSER_ALLOWED_HOSTS`. DNS rebinding and non-HTTP browser transports require additional isolation before expanding use. If you change the Compose subnet or app address, update the filter script and re-apply it. Docker documents `DOCKER-USER` as the supported place for user-defined forwarding rules; do not rely on UFW alone for published container ports.

## 4. Configure the application

Copy the example and edit it on the VM. Do not commit `.env` or share its secrets.

```bash
cd /opt/remotobrowser
cp .env.example .env
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
nano .env
```

Set at least these values (replace every example domain and placeholder):

```dotenv
APP_ENV=production
APP_SECRET_KEY=REPLACE_WITH_GENERATED_RANDOM_VALUE
DISCORD_CLIENT_ID=YOUR_DISCORD_CLIENT_ID
DISCORD_CLIENT_SECRET=YOUR_DISCORD_CLIENT_SECRET
BASE_URL=https://browser.example.org
APP_DOMAIN=browser.example.org
APP_IMAGE=ghcr.io/oarikui/remotobrowser:latest
ALLOWED_DISCORD_IDS=YOUR_DISCORD_USER_ID
BROWSER_ALLOWED_HOSTS=app.example.org,static.example.org
DEFAULT_START_URL=https://app.example.org/
TRUST_PROXY_HEADERS=true
MAX_CONCURRENT_SESSIONS=1
```

Important:

- `BASE_URL` and `APP_DOMAIN` must be the same public service host (without a path).
- In Discord Developer Portal, set OAuth2 Redirect URI to `https://browser.example.org/auth/callback`.
- `ALLOWED_DISCORD_IDS` is mandatory in production; otherwise the app refuses to start.
- `BROWSER_ALLOWED_HOSTS` is mandatory in production. It is an exact hostname allowlist; no `*`, IP addresses, ports, or implicit subdomains. Include every first-party hostname and every static/API/WebSocket hostname required by the site under test.
- `DEFAULT_START_URL` must use one of those exact hosts.
- The test-site allowlist applies to navigations, redirects, subresources, and page WebSockets. Unlisted third-party assets will be blocked; add them only when authorized and required for the test.
- Keep `ENABLE_DOCS=false` in production.

Validate the final Compose configuration before starting:

```bash
docker compose --env-file .env -f deployment/compose.oci.yaml config
```

## 5. Publish the ARM64 image and deploy

The repository has two workflows:

- `CI`: runs Ruff, basedpyright, pytest, dependency audit, checks Docker builds for AMD64 and ARM64, and scans an AMD64 image with Trivy.
- `Deploy to OCI`: manually builds and publishes an ARM64 image to GHCR, then connects over SSH and updates the Compose service.

For the deployment workflow, add these GitHub repository **Actions secrets**:

| Secret | Value |
|---|---|
| `OCI_HOST` | VM public IPv4 address or DNS name |
| `OCI_USER` | SSH user (normally `ubuntu`) |
| `OCI_SSH_PRIVATE_KEY` | Private SSH key authorized on the VM |
| `OCI_KNOWN_HOSTS` | Verified `known_hosts` line for that VM |

Optionally add repository variable `OCI_DEPLOY_PATH` (default `/opt/remotobrowser`). Verify the host-key fingerprint from a trusted source before storing `OCI_KNOWN_HOSTS`; do not blindly trust an unverified `ssh-keyscan` result.

The first pushed GHCR package may be private by default. In GitHub Packages, change `ghcr.io/oarikui/remotobrowser` visibility to **Public** before deployment, or separately configure a read-only registry credential on the VM. Do not put a registry token in the repository or `.env` unless private package access is required.

After the workflow completes, check:

```bash
cd /opt/remotobrowser
docker compose --env-file .env -f deployment/compose.oci.yaml ps
docker compose --env-file .env -f deployment/compose.oci.yaml logs --tail=100 app caddy
```

Open `https://browser.example.org`, complete Discord login, start the browser, verify that the managed test site loads, and confirm that an unlisted hostname is blocked. Also confirm that a site dependency on an unlisted CDN is blocked until explicitly approved and added.

Manual first start (without Actions): after making the GHCR package public, use:

```bash
APP_IMAGE=ghcr.io/oarikui/remotebrowser:latest \
  docker compose --env-file .env -f deployment/compose.oci.yaml pull app
APP_IMAGE=ghcr.io/oarikui/remotebrowser:latest \
  docker compose --env-file .env -f deployment/compose.oci.yaml up -d
```

## 6. Backups, updates, and rollback

Persistent state is in named volumes:

- `remotobrowser-appdata`: SQLite database.
- `remotobrowser-caddy-data`: TLS certificates and ACME state.
- `remotobrowser-caddy-config`: Caddy runtime config state.

Back up the SQLite volume and OCI boot volume before upgrades. Stop the app before taking a file-level SQLite backup, or use SQLite's online backup mechanism. Store backups outside the VM and test restore procedures. Do not assume the boot volume alone is a complete backup.

To roll back, run Compose with a previously published immutable image tag (a commit SHA), not `latest`:

```bash
APP_IMAGE=ghcr.io/oarikui/remotobrowser:PREVIOUS_COMMIT_SHA \
  docker compose --env-file .env -f deployment/compose.oci.yaml up -d
```

## 7. Scope and remaining verification

This is a single-VM starting configuration, not a high-availability deployment. It intentionally starts with one browser session. The application and browser runtime still share a container, so a full container compromise could affect the app process as well. The hostname allowlist and host egress filter reduce exposure but do not replace a future split between API and browser workers, per-session isolation, continuous patching, monitoring, and a reviewed threat model.

The Docker image is built for ARM64 in GitHub Actions, but the actual OCI VM, Chromium GUI, VNC/noVNC display, Caddy certificate issuance, and real domain allowlist have not been exercised from this development environment. Complete the verification checklist on the provisioned VM before making the service available to anyone else.
