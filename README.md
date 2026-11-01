# Remote Browser

Discord OAuth2で認証した利用者が、サーバー上の使い捨てChromiumを操作して、**自分が所有・管理するWebサイトを検査する**ためのリモートブラウザテスト環境です。

ブラウザの接続先は `BROWSER_ALLOWED_HOSTS` に列挙した完全一致ホストだけです。ワイルドカードは使えず、サブドメインやCDNは個別に登録します。HTTP(S)リクエストとWebSocketの両方を制限します。

> これはVPNではありません。通信全体の暗号化や匿名性を提供せず、許可リスト外の一般サイトを閲覧するためのプロキシとしては設計していません。

## 最初にやること(あなたの作業)

1. **Discordアプリを作る**: [Discord Developer Portal](https://discord.com/developers/applications) → New Application
   - OAuth2 → Redirects に `http://localhost:8000/auth/callback` を追加(本番公開時は本番URLの `/auth/callback` も追加)
   - Client ID / Client Secret を控える(Botは不要、scopeは `identify` のみ)
2. **`.env` を作る**: `cp .env.example .env` して、`APP_SECRET_KEY`・`DISCORD_CLIENT_ID`・`DISCORD_CLIENT_SECRET` を埋める
3. **自分のDiscord IDを `ALLOWED_DISCORD_IDS` に入れる**(Discordの設定 → 詳細設定 → 開発者モードON → 自分を右クリック → IDをコピー)。開発時は空欄も使えますが、本番環境では必須です
4. **ローカルUI確認**: `BROWSER_RUNTIME=fake python run.py` (実ブラウザを起動しません)
5. **OCI本番構築**: [docs/oci.md](docs/oci.md) を参照。ローカルPCにはDocker/WSL2不要です。
6. **GitHub Actions**: `ci.yml` でテストとAMD64/ARM64イメージを検証。`deploy-oci.yml` は手動実行です。

## 起動方法

### ローカル(UI・APIの疑似環境確認)

```bash
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
cp .env.example .env
# APP_SECRET_KEY / Discord OAuth2 / ALLOWED_DISCORD_IDS / BROWSER_ALLOWED_HOSTS を設定
BROWSER_RUNTIME=fake python run.py
```

`fake` ランタイムはChromiumを起動せず、APIと画面中継の一部だけを模擬します。実ブラウザの起動確認はOCI上で行います。

### OCI (本番)

OCI Ampere A1 / Ubuntu 24.04 ARM64 / Docker Engine / Docker Compose / Caddyで動作します。セットアップ・GitHub Actions・DNS・NSG・出口制限は [docs/oci.md](docs/oci.md) を参照してください。

## 開発

```bash
ruff check . && ruff format --check .   # Lint / Format
basedpyright                             # 型検査
pytest                                   # テスト
```

## 構成

```
src/main.py            アプリ組み立て(create_app)
src/package/
  config.py            設定(環境変数)
  api/                 HTTPエンドポイント + noVNC WebSocket中継
  auth/                Discord OAuth2 / セッションCookie署名
  browser/             完全一致ホスト許可リスト / 実行環境(Xvfb+x11vnc+Chromium)
  sessions/            セッション管理・期限切れ回収
  database/            SQLite(users / browser_sessions / user_settings)
  security/            CSRF・セキュリティヘッダー・レート制限・所有者検証
  services/            ユーザー・ブラウザ操作の業務処理
frontend/              ログイン画面・ブラウザ操作画面(noVNCクライアント組み込み)
deployment/            Dockerfile / Compose / Caddy / OCI bootstrap・出口制限
tests/                 unit / integration / security
docs/                  設計・開発・OCIデプロイ・セキュリティ
```

## 主な環境変数

`.env.example` を参照。初期の運営制限(計画書 5章)は次のとおりです。

| 変数 | 既定値 | 内容 |
| --- | --- | --- |
| `MAX_CONCURRENT_SESSIONS` | 1 | 同時ブラウザ数 |
| `SESSION_MAX_SECONDS` | 1800 | 1回の利用上限(30分) |
| `IDLE_TIMEOUT_SECONDS` | 300 | 無操作タイムアウト(5分) |
| `ALLOWED_DISCORD_IDS` | 空 | 本番必須。利用を許可するDiscord ID |
| `BROWSER_ALLOWED_HOSTS` | `example.com` | 本番必須。ブラウザが接続できる完全一致ホスト名 |
| `BASE_URL` | `http://localhost:8000` | サービスの公開URL。OCI本番はHTTPS |
| `SCREEN_WIDTH` / `SCREEN_HEIGHT` | 1280 / 720 | 画面解像度 |

## 実装範囲

| Phase | 内容 | 状態 |
| --- | --- | --- |
| 0 | リポジトリ・Docker・FastAPI・CI | 実装済み |
| 1 | Discord OAuth2 / ログイン・ログアウト / CSRF | 実装済み・自動テスト済み |
| 2 | Chromium + Xvfb + noVNC | 実装済み・**実機未検証**(下記) |
| 3 | セッション管理・タイムアウト・異常終了回収 | 実装済み・自動テスト済み |
| OCI基盤 | ARM64ビルド・Compose・Caddy・出口フィルタ・手動デプロイ | 構成追加済み・OCI実機未検証 |
| 4〜7 | UI仕上げ・実機セキュリティ検証・公開・運営 | 未着手(UIは最小構成あり) |

「実機未検証」: Xvfb・x11vnc・Chromiumを起動する `browser/lifecycle.py` は、開発環境にこれらが無く実行できていません。
ロジックの大半は `FakeRuntime` で自動テストしていますが、最初のDocker起動で調整が要る可能性があります(`docs/development.md` のトラブルシュート参照)。
