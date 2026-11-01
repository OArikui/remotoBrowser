# アーキテクチャ

## 全体像

```
ブラウザ(利用者)
  │  HTTPS / WSS
  ▼
FastAPI (Uvicorn) ── Discord OAuth2 ── SQLite
  │  ├─ /auth/*        ログイン・コールバック・ログアウト
  │  ├─ /api/*         ユーザー・ブラウザ・セッション操作
  │  └─ /ws/vnc/{id}   認証済みの所有者だけが使えるWebSocket中継
  │          │ TCP (127.0.0.1)
  │          ▼
  │     x11vnc ── Xvfb(仮想ディスプレイ) ── Chromium(使い捨てプロファイル)
  └─ 静的配信: frontend/ と noVNC クライアント(/novnc)
```

- **Playwright** はChromiumの起動・終了・戻る/進む/再読み込み/URL移動を担当。
- **noVNC** は画面表示とマウス・キーボード入力の伝達を担当(画面転送の独自実装なし)。
- x11vnc はセッションごとに `127.0.0.1` の空きポートだけで待ち受け、外部には出さない。
  利用者は FastAPI の WebSocket 中継 (`/ws/vnc/{session_id}`) を通してのみ到達でき、
  中継の前に「ログイン済み」「セッションの所有者本人」「Originが自サイト」を検証する。
  → 計画書の「noVNC接続先は認証済みセッションにのみ発行」「他人のセッションIDでは接続不可」を満たす。

## セッションのライフサイクル

`starting → running → stopping → stopped`

- 1ユーザーにつき有効なセッションは1つ(DBの部分ユニークインデックスでも保証)。
- 終了理由は `end_reason` に記録: `user` / `expired` / `idle` / `crashed` / `replaced` / `restart` / `shutdown` / `start_failed` / `rejected_url`。
- 15秒ごとのスイーパーが、異常終了(プロセス消失)→ 期限切れ → アイドルの順に回収する。
- アプリ再起動時は、DB上の有効セッションをすべて `restart` で閉じる(以前のプロセスが残っていると仮定しない)。
- アイドル判定はフロントエンドが画面操作時に30秒ごとに送る `/api/browser/activity` が起点。
  (noVNCは無操作でも常に通信するため、WebSocketの通信量は操作の指標にならない)
- 終了時にChromiumプロファイル(Cookie・履歴)ごと一時ディレクトリを削除する。

## 計画書からの変更点

| 計画書 | 実装 | 理由 |
| --- | --- | --- |
| Authlib | httpx で直接実装 | Authorization Code Grantだけなので依存を減らし、テストしやすくするため |
| websockify(想定) | FastAPIのWebSocket中継 | VNCポートを外に出さず、認証・所有者検証を同じ場所で行うため |
| api / browser / proxy の別コンテナ | 試作は1コンテナ | 計画書2-1の「初期試作では同居可」に従う。公開前に分離する |
| `src/utils.py` | `src/package/utils.py` | `utils` というトップレベル名は他ライブラリと衝突しやすいため |
| 本番DBはPostgreSQL | SQLite(`Repository` 経由) | Cloud Runでは永続化できないため、公開時にPostgreSQL実装へ差し替える |
| (なし) | `ALLOWED_DISCORD_IDS` | 任意サイトを中継するサービスなので、公開前に利用者を絞れるようにするため |

## 公開前に必要な分離(Phase 5〜6)

1. Browser Runtime を別コンテナ/別サービスへ分離し、API からは内部ネットワーク経由で操作する。
2. Browser Runtime のコンテナに **外部(公開インターネット)宛のみ許可する出口制限** をかける(`docs/security.md`)。
3. セッション状態の外部管理(Cloud Run の複数インスタンス対策)。
