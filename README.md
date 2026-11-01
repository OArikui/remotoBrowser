# Remote Browser

Discordアカウントでログインし、Webブラウザからサーバー上の使い捨てChromium(noVNC)を操作するサービスです。
開発・運営計画書(`discord VPN.md`)のうち **Phase 0〜3**(FastAPI基盤 / Discord OAuth2 / Chromium+Xvfb+noVNC / セッション管理 / Docker / CI)を実装しています。

> 注意: これは「ブラウザ画面の中継」であり、VPNではありません。通信全体の暗号化や匿名性は提供しません。

## 最初にやること(あなたの作業)

1. **Discordアプリを作る**: [Discord Developer Portal](https://discord.com/developers/applications) → New Application
   - OAuth2 → Redirects に `http://localhost:8000/auth/callback` を追加(本番公開時は本番URLの `/auth/callback` も追加)
   - Client ID / Client Secret を控える(Botは不要、scopeは `identify` のみ)
2. **`.env` を作る**: `cp .env.example .env` して、`APP_SECRET_KEY`・`DISCORD_CLIENT_ID`・`DISCORD_CLIENT_SECRET` を埋める
3. **自分のDiscord IDを `ALLOWED_DISCORD_IDS` に入れる**(Discordの設定 → 詳細設定 → 開発者モードON → 自分を右クリック → IDをコピー)。空のままだと誰でも使えてしまうので、公開前は必須です
4. **Dockerで起動して動作確認**: `docker compose -f deployment/compose.yaml up --build` → <http://localhost:8000>
5. **GitHubにpush**してCIが通ることを確認(`.github/workflows/ci.yml`)

## 起動方法

### Docker(推奨・実ブラウザが動く)

```bash
cp .env.example .env   # 編集してから
docker compose -f deployment/compose.yaml up --build
# http://localhost:8000 を開く
```

### ローカル(UI確認だけ・実ブラウザなし)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
BROWSER_RUNTIME=fake python run.py
```

`fake` ランタイムはChromiumを起動せず、画面中継の疎通だけを模擬します(noVNCの静的ファイルも無いため画面は出ません)。
実際にChromiumを動かすには、Xvfb・x11vnc・noVNC・Playwrightのブラウザが必要なのでDockerを使ってください。

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
  browser/             URLポリシー(SSRF対策) / 実行環境(Xvfb+x11vnc+Chromium)
  sessions/            セッション管理・期限切れ回収
  database/            SQLite(users / browser_sessions / user_settings)
  security/            CSRF・セキュリティヘッダー・レート制限・所有者検証
  services/            ユーザー・ブラウザ操作の業務処理
frontend/              ログイン画面・ブラウザ操作画面(noVNCクライアント組み込み)
deployment/            Dockerfile / compose.yaml
tests/                 unit / integration / security
docs/                  設計・開発・デプロイ・セキュリティ
```

## 主な環境変数

`.env.example` を参照。初期の運営制限(計画書 5章)は次のとおりです。

| 変数 | 既定値 | 内容 |
| --- | --- | --- |
| `MAX_CONCURRENT_SESSIONS` | 1 | 同時ブラウザ数 |
| `SESSION_MAX_SECONDS` | 1800 | 1回の利用上限(30分) |
| `IDLE_TIMEOUT_SECONDS` | 300 | 無操作タイムアウト(5分) |
| `SCREEN_WIDTH` / `SCREEN_HEIGHT` | 1280 / 720 | 画面解像度 |

## 実装範囲

| Phase | 内容 | 状態 |
| --- | --- | --- |
| 0 | リポジトリ・Docker・FastAPI・CI | 実装済み |
| 1 | Discord OAuth2 / ログイン・ログアウト / CSRF | 実装済み・自動テスト済み |
| 2 | Chromium + Xvfb + noVNC | 実装済み・**実機未検証**(下記) |
| 3 | セッション管理・タイムアウト・異常終了回収 | 実装済み・自動テスト済み |
| 4〜7 | UI仕上げ・セキュリティ検証・公開・運営 | 未着手(UIは最小構成あり) |

「実機未検証」: Xvfb・x11vnc・Chromiumを起動する `browser/lifecycle.py` は、開発環境にこれらが無く実行できていません。
ロジックの大半は `FakeRuntime` で自動テストしていますが、最初のDocker起動で調整が要る可能性があります(`docs/development.md` のトラブルシュート参照)。
