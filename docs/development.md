# 開発ガイド

## セットアップ

```bash
python -m venv .venv && source .venv/bin/activate   # Python 3.13
pip install -e ".[dev]"
cp .env.example .env                                  # 値を編集
```

## 品質チェック(CIと同じ)

```bash
ruff check . && ruff format --check .
basedpyright
pytest
pip-audit --skip-editable
```

## テストの構成

- `tests/unit/` — URLポリシー、Cookie署名、レート制限、リクエストガード
- `tests/integration/` — OAuthフロー、セッション開始/終了/期限切れ/アイドル/異常終了、WebSocket中継
- `tests/security/` — 認可・CSRF・ヘッダー・Cookie属性

実ブラウザは使わず、`FakeRuntime`(VNCの代わりにバナーを返すTCPサーバー)とFakeのDiscordクライアントで検証する。
時間経過は `Clock` を進めて `sessions.sweep()` を直接呼ぶ。

## 実ブラウザ(Docker)で最初に確認すること

`browser/lifecycle.py`(Xvfb → x11vnc → Playwright)は実機未検証。初回起動で確認する項目:

1. 「ブラウザを起動」でChromiumの画面が出る(kioskモードでウィンドウが画面いっぱいに出るか)
2. 日本語サイトの文字が表示される(`fonts-noto-cjk` 導入済み)
3. 終了後に `ps` で `Xvfb` / `x11vnc` / `chromium` が残っていない
4. `BROWSER_ALLOWED_HOSTS` に含まれないホストがHTTP(S)・WebSocketともに拒否されることを確認
5. 許可リストのドメインがプライベートIPへ解決された場合に拒否されることを確認

うまく動かない場合の切り分け:

| 症状 | 確認 |
| --- | --- |
| 起動が502で失敗 | `docker compose logs app` に `browser start failed` と例外が出る。XvfbやChromiumの起動エラーを確認 |
| 画面が真っ黒 | Chromiumのウィンドウが出ていない可能性。`--kiosk` を外して `--start-maximized` を試す |
| `/novnc/core/rfb.js` が404 | `NOVNC_DIR` がnoVNCのインストール先を指しているか(Debianは `/usr/share/novnc`) |
| WebSocketがすぐ切れる | リバースプロキシ使用時、WebSocketのUpgradeを通す設定になっているか |

## ブランチ運用(計画書 3-2)

`main` / `develop` / `feature/*` / `release/v*`。バージョンは計画書のv0.1.0〜v1.0.0に沿う
(現在のコードは **v0.6.0** 相当: セッション管理まで)。
