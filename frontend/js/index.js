import { loadMe } from "/js/common.js";

try {
  const me = await loadMe();
  location.replace(me ? "/browser.html" : "/login.html");
} catch {
  document.getElementById("msg").textContent = "サーバーに接続できませんでした。";
}
