# デプロイ(Phase 6 に向けたメモ)

ローカル確認用の `deployment/compose.yaml` は `127.0.0.1:8000` のみにポートを公開します。これは開発用設定です。外部公開では、そのままポートを開放せず、TLS終端を行うリバースプロキシや利用者制限を含む構成を別途用意してください。

現時点のコードはローカルDockerでの動作確認までが対象。公開する前に次を決めて実施する。

## 手動デプロイの流れ(計画書: 最初は自動デプロイしない)

1. PRをマージし、CIが全部通っていることを確認
2. イメージをビルドしてレジストリへ push
3. ホスティングへ反映(Cloud Run なら `gcloud run deploy`)
4. `/health` と、ログイン〜ブラウザ起動〜終了までを手動確認

## Cloud Run で必要になること(計画書 2-9)

- WebSocketは最大60分で切れる → セッション上限(30分)を超えない設計は済み。切断時の自動再接続は未実装
- インスタンスが複数になるとセッション状態が共有されない → 初期は `max-instances=1`
- ローカルファイルは永続化されない → **SQLiteは本番では使わない**(外部DBへ。`Repository` の差し替え)
- WebSocket接続中は課金対象 → 無料枠内に収まるか実測(Phase 7)
- 環境変数: `BASE_URL`(公開URL)、`TRUST_PROXY_HEADERS=true`、`PORT`(Cloud Runが設定)
- シークレット(`APP_SECRET_KEY`, `DISCORD_CLIENT_SECRET`)は Secret Manager から注入

## 公開前チェックリスト

- [ ] `ALLOWED_DISCORD_IDS` を設定した
- [ ] `BASE_URL` が https の公開URLで、Discordの Redirect URI と一致している
- [ ] Browser Runtime に出口制限(非公開IP宛の遮断)をかけた(`docs/security.md` 限界1)
- [ ] 計画書どおり `MAX_CONCURRENT_SESSIONS=1` から始めた
- [ ] 無料枠の上限アラート(課金アラート)を設定した

## 構成の分離(計画書の最終形)

Cloudflare Pages(フロント)+ Cloud Run(API)に分ける場合、Cookie/CSRF/WebSocketが別オリジンになる。
CookieのSameSite・CORS・Originの扱いを設計し直す必要があるため、まずは「APIと同一オリジンでフロントも配信」(現状)のまま公開して計測することを推奨。
