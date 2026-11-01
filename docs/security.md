# セキュリティ

## 実装済みの対策

| 項目 | 内容 |
| --- | --- |
| 認証 | Discord OAuth2(Authorization Code Grant, scope=`identify`)。`state` はHttpOnly Cookieと突き合わせる |
| トークン | Discordのアクセストークンは認証直後に失効(revoke)し、保存・ログ出力しない |
| セッションCookie | 署名付き(itsdangerous)、HttpOnly、SameSite=Lax、HTTPS時はSecure。中身はユーザーIDとCSRFトークンのみ |
| CSRF | 状態を変えるAPIは `X-CSRF-Token`(セッションに紐づく値)と `Origin` を検証 |
| 認可 | VNC中継は「セッションの所有者本人」だけ。他人のIDを指定しても接続不可。許可リストから外すと既存Cookieも即無効 |
| WebSocket | Originを検証(クロスサイトWebSocketハイジャック対策) |
| 利用者の制限 | `ALLOWED_DISCORD_IDS`。本番環境では空欄を許可しない |
| レート制限 | ログイン開始・ブラウザ起動(インメモリ。単一インスタンス用) |
| ヘッダー | CSP / X-Frame-Options / nosniff / Referrer-Policy / Permissions-Policy / APIはno-store |
| 接続先許可リスト | `BROWSER_ALLOWED_HOSTS` の完全一致ホストだけ許可。ワイルドカード・IPアドレス・別サブドメインは拒否 |
| URLポリシー | http/https以外・埋め込み認証情報・非標準ポート・非公開IP宛を拒否。名前解決後の全IPも検査 |
| HTTPリクエスト検査 | Chromiumのリダイレクト先・サブリソースを含むHTTP(S)リクエストを `BrowserContext.route()` で検査。Service Workerは無効 |
| WebSocket検査 | ページが開始するWebSocketも `route_web_socket()` で同じホスト・IP許可ポリシーを適用 |
| 分離 | セッションごとに別Xvfb・別プロファイル。終了時にプロファイルを削除 |
| コンテナ | 非root、`cap_drop: ALL`、`no-new-privileges`、メモリ/PID上限、`/tmp` はtmpfs |
| ログ | 標準出力。トークン・Cookie・閲覧内容・入力内容は記録しない |

## OCI運用上の限界・必須事項

1. **DNS rebinding / TOCTOU**: DNSの確認後とChromiumの実接続で名前解決結果が変わる競合を、アプリ層だけで完全には排除できない。OCI構成では `deployment/oci/remotobrowser-egress-filter.sh` をDockerの `DOCKER-USER` チェーンへ適用し、アプリ/ブラウザコンテナからプライベート・ループバック・リンクローカル・メタデータ宛の新規IPv4接続を遮断する。
2. **出口ポート**: アプリコンテナの新規外向き通信はTCP 80/443だけに制限し、ChromiumのQUICを無効化する。IPv6はComposeネットワークで無効化している。ネットワーク設定を変更する場合は同等のIPv6ルールも追加する。なお、このホストファイアウォールはFQDN単位の制御ではない。管理対象ホストの完全一致制限はPlaywrightのHTTP(S)・WebSocket検査で適用しており、DNS rebindingや別トランスポートまでネットワーク層で完全に防ぐものではない。
3. **許可リスト管理**: `BROWSER_ALLOWED_HOSTS` は管理対象ホストの正確な一覧として保守する。必要なCDN・API・WebSocketホストを所有者が確認してから列挙する。ワイルドカードは禁止。
4. **同一コンテナ構成**: 現段階ではFastAPIとChromiumを同じコンテナで動かす。ホスト出口フィルタは私有ネットワーク等への到達を抑えるが、コンテナ全体が侵害された場合の完全分離を保証しない。一般公開前にAPIとBrowser Runtimeを別コンテナ/別権限へ分離し、脅威モデルを再評価する。
5. **レート制限・セッション状態はインメモリ**: 単一インスタンス運用を前提とする。複数インスタンスにするなら外部ストア(Redis/DB)へ。
6. **VNC経路**: x11vnc は `-nopw` + `127.0.0.1` 限定で、認証はAPIの中継に依存する。VNCポートは公開しない。

## 自動テスト(`tests/security/`)

- 未認証アクセスの拒否 / CSRFトークン・Originの検証 / Cookie改ざんの拒否
- 他ユーザーのセッションへのWebSocket接続拒否 / 外部Originの拒否
- 許可リストから外したユーザーの即時失効
- 非許可ホスト・非標準ポート・SSRF対象URLの拒否(`tests/unit/test_policies.py`)
- WebSocket宛先にも許可リストを適用する検査
- セキュリティヘッダー・Cookie属性
