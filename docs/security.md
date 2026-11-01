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
| 利用者の制限 | `ALLOWED_DISCORD_IDS`(空なら全員許可) |
| レート制限 | ログイン開始・ブラウザ起動(インメモリ。単一インスタンス用) |
| ヘッダー | CSP / X-Frame-Options / nosniff / Referrer-Policy / Permissions-Policy / APIはno-store |
| URLポリシー | http/https以外・埋め込み認証情報・非公開IP(localhost, 10/8, 172.16/12, 192.168/16, 169.254/16, 100.64/10 等)宛を拒否。名前解決後のIPも検査 |
| リクエスト検査 | Chromiumの全HTTP(S)リクエスト(リダイレクト先・サブリソース含む)を `route()` で検査。Service Workerは無効 |
| 分離 | セッションごとに別Xvfb・別プロファイル。終了時にプロファイルを削除 |
| コンテナ | 非root、`cap_drop: ALL`、`no-new-privileges`、メモリ/PID上限、`/tmp` はtmpfs |
| ログ | 標準出力。トークン・Cookie・閲覧内容・入力内容は記録しない |

## 既知の限界(公開前に必ず対応)

1. **DNS rebinding / TOCTOU**: URL検査時とChromiumの実接続時で名前解決結果が変わる可能性が残る。
   アプリ層の検査は「第一層」で、**最終的な境界はネットワーク**にある。Browser Runtimeのコンテナに
   プライベート/リンクローカル/メタデータ宛(`169.254.169.254` など)を遮断する出口制限を必ず設定する。
2. **WebSocket通信**: Playwrightの `route()` はページ内WebSocketを検査しない。上記の出口制限で補う。
3. **レート制限・セッション状態はインメモリ**: 複数インスタンスにするなら外部ストア(Redis/DB)へ。
4. **ブラウザ経由の悪用**: 認証済み利用者はサーバーのIPからWebを閲覧できる。許可リスト運用と利用規約・ログ方針を決めること。
5. **VNC経路**: x11vnc は `-nopw` + `127.0.0.1` 限定で、認証はAPIの中継に依存する。
   Browser Runtimeを別コンテナに分離する際は、内部ネットワークを閉じ、VNCポートを公開しないこと。

## 自動テスト(`tests/security/`)

- 未認証アクセスの拒否 / CSRFトークン・Originの検証 / Cookie改ざんの拒否
- 他ユーザーのセッションへのWebSocket接続拒否 / 外部Originの拒否
- 許可リストから外したユーザーの即時失効
- SSRF対象URLの拒否(`tests/unit/test_policies.py`)
- セキュリティヘッダー・Cookie属性
