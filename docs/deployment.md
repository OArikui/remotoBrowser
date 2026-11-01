# デプロイ

本プロジェクトの初期サーバー運用先は Oracle Cloud Infrastructure (OCI) Ampere A1 / Ubuntu 24.04 ARM64 です。

## OCI

構築手順、VM・VCN・NSG、Docker Engine、Caddy HTTPS、SQLite永続化、ブラウザ出口制限、GitHub Actionsの手動デプロイは [oci.md](oci.md) を参照してください。

- Compose: `deployment/compose.oci.yaml`
- Caddy: `deployment/Caddyfile`
- 初期セットアップ: `deployment/oci/bootstrap.sh`
- ブラウザコンテナ出口制限: `deployment/oci/remotobrowser-egress-filter.sh`
- systemd unit: `deployment/oci/remotobrowser-egress-filter.service`
- CI: `.github/workflows/ci.yml`
- 手動デプロイ: `.github/workflows/deploy-oci.yml`

## ローカル開発

Windows PCにDocker DesktopやWSL2を入れる必要はありません。Python環境で `BROWSER_RUNTIME=fake` を指定すれば、API・認証・セッションのテストができます。実Chromiumの統合確認はOCI上で実施します。

## デプロイ前チェック

- [ ] `APP_ENV=production`
- [ ] `BASE_URL` はHTTPSの公開URL
- [ ] Discord OAuth2 Redirect URIが `${BASE_URL}/auth/callback` と一致
- [ ] `ALLOWED_DISCORD_IDS` が空でない
- [ ] `BROWSER_ALLOWED_HOSTS` に管理対象の正確なホスト名のみを列挙
- [ ] `DEFAULT_START_URL` のホストが許可リスト内
- [ ] OCI NSGで公開するのはSSH(管理元IP限定)・TCP 80/443のみ
- [ ] `DOCKER-USER` 出口フィルタが適用済み
- [ ] SQLite/Caddyデータのバックアップを確認
- [ ] 実ブラウザ起動、WebSocket、許可ホスト外拒否を実機確認

## 旧Cloud Run案について

Cloud Run構成は初期OCI構成の対象外です。WebSocketの接続寿命、複数インスタンス間の状態共有、SQLite永続化の問題があるため、別途アーキテクチャを設計し直す必要があります。
