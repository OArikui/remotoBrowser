let csrfToken = null;

/** ログイン中なら /api/me の内容を返し、未ログインなら null を返す。 */
export async function loadMe() {
  const res = await fetch("/api/me", { credentials: "same-origin" });
  if (res.status === 401) return null;
  if (!res.ok) throw new Error(`/api/me failed: ${res.status}`);
  const me = await res.json();
  csrfToken = me.csrf_token;
  return me;
}

/** JSON API呼び出し。POST等には自動でCSRFトークンを付ける。 */
export async function api(path, { method = "GET", body } = {}) {
  const headers = {};
  if (method !== "GET") headers["X-CSRF-Token"] = csrfToken ?? "";
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(path, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    credentials: "same-origin",
  });
  let data = null;
  try {
    data = await res.json();
  } catch {
    // 本文なし
  }
  if (!res.ok) {
    const detail = typeof data?.detail === "string" ? data.detail : res.statusText;
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  return data;
}
