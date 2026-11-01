import RFB from "/novnc/core/rfb.js";
import { api, loadMe } from "/js/common.js";

const $ = (id) => document.getElementById(id);
const CONTROLS = ["btn-back", "btn-forward", "btn-reload", "url-input", "btn-go", "btn-fullscreen", "btn-stop"];

let rfb = null;
let expiresAt = null; // ms。セッションが無ければ null
let userActive = false;

function setStatus(text, kind = "") {
  const el = $("status");
  el.textContent = text;
  el.className = `badge ${kind}`.trim();
}

function showMessage(text) {
  const el = $("message");
  el.textContent = text ?? "";
  el.classList.toggle("hidden", !text);
}

function setRunning(running) {
  for (const id of CONTROLS) $(id).disabled = !running;
  $("btn-start").disabled = running;
}

function formatRemaining(totalSeconds) {
  const s = Math.max(0, totalSeconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function disconnectScreen() {
  if (rfb) {
    const current = rfb;
    rfb = null;
    try {
      current.disconnect();
    } catch {
      // 既に切断済み
    }
  }
  $("screen").replaceChildren();
}

function connectScreen(session) {
  disconnectScreen();
  const scheme = location.protocol === "https:" ? "wss:" : "ws:";
  const next = new RFB($("screen"), `${scheme}//${location.host}${session.vnc_path}`);
  next.scaleViewport = true;
  next.resizeSession = false;
  next.background = "#111";
  next.addEventListener("connect", () => {
    setStatus("接続中", "ok");
    showMessage("");
  });
  next.addEventListener("disconnect", () => {
    if (rfb === next) {
      rfb = null;
      setStatus("切断されました", "warn");
    }
  });
  rfb = next;
}

function applySession(session) {
  if (session.status === "running") {
    expiresAt = Date.now() + session.remaining_seconds * 1000;
    setRunning(true);
    if (!rfb) {
      setStatus("接続中…", "warn");
      connectScreen(session);
    }
    return;
  }
  const hadSession = expiresAt !== null;
  expiresAt = null;
  setRunning(false);
  disconnectScreen();
  $("remaining").textContent = "--:--";
  setStatus("未接続");
  showMessage(
    hadSession
      ? "セッションが終了しました。もう一度使うには「ブラウザを起動」を押してください。"
      : "「ブラウザを起動」を押すと、使い捨てのChromiumが開きます。\n終了するとCookieや履歴はすべて破棄されます。",
  );
}

async function refresh() {
  try {
    applySession(await api("/api/session"));
  } catch (err) {
    if (err.status === 401) location.replace("/login.html");
  }
}

async function run(action) {
  try {
    await action();
  } catch (err) {
    if (err.status === 401) {
      location.replace("/login.html");
      return;
    }
    setStatus("エラー", "err");
    showMessage(err.message);
  }
}

async function main() {
  const me = await loadMe();
  if (!me) {
    location.replace("/login.html");
    return;
  }
  $("user-name").textContent = me.username;
  await refresh();

  $("btn-start").addEventListener("click", () =>
    run(async () => {
      $("btn-start").disabled = true;
      setStatus("起動中…", "warn");
      showMessage("ブラウザを起動しています…");
      applySession(await api("/api/browser/start", { method: "POST", body: {} }));
    }).finally(refresh),
  );
  $("btn-stop").addEventListener("click", () =>
    run(async () => {
      await api("/api/browser/stop", { method: "POST" });
      await refresh();
    }),
  );
  for (const [id, action] of [
    ["btn-back", "back"],
    ["btn-forward", "forward"],
    ["btn-reload", "reload"],
  ]) {
    $(id).addEventListener("click", () =>
      run(() => api("/api/browser/navigate", { method: "POST", body: { action } })),
    );
  }
  $("url-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const url = $("url-input").value.trim();
    if (!url) return;
    run(() => api("/api/browser/navigate", { method: "POST", body: { action: "goto", url } }));
  });
  $("btn-fullscreen").addEventListener("click", () => $("screen-wrap").requestFullscreen?.());
  $("btn-logout").addEventListener("click", () =>
    run(async () => {
      await api("/auth/logout", { method: "POST" });
      location.replace("/login.html");
    }),
  );

  // 画面上の操作があった間だけ、30秒ごとにサーバーへ通知する(アイドルタイムアウト用)
  for (const type of ["mousedown", "mousemove", "keydown", "wheel", "touchstart"]) {
    $("screen").addEventListener(type, () => {
      userActive = true;
    });
  }
  setInterval(() => {
    if (userActive && expiresAt !== null) {
      userActive = false;
      api("/api/browser/activity", { method: "POST" }).catch(() => {});
    }
  }, 30_000);

  setInterval(refresh, 5_000);
  setInterval(() => {
    if (expiresAt !== null) {
      $("remaining").textContent = formatRemaining(Math.round((expiresAt - Date.now()) / 1000));
    }
  }, 1_000);
}

main().catch(() => {
  setStatus("エラー", "err");
  showMessage("サーバーに接続できませんでした。");
});
