const MESSAGES = {
  not_allowed: "このDiscordアカウントは利用が許可されていません。",
  denied: "ログインがキャンセルされました。",
  discord: "Discordとの通信に失敗しました。時間をおいて再度お試しください。",
};

const code = new URLSearchParams(location.search).get("error");
if (code) {
  document.getElementById("error").textContent = MESSAGES[code] ?? "ログインに失敗しました。";
}
