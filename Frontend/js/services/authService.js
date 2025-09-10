import { fetchJSON } from "../http.js";
import { saveSession, clearSession, getSession } from "../session.js";

export async function register(payload) {
  // payload = { username, email, password, role, first_name, last_name }
  return fetchJSON("/auth/register", { method: "POST", body: payload });
}

export async function login({ username, password}) {
  const data = await fetchJSON("/auth/login", {
    method: "POST",
    body: { username, password }
  });
  if (data?.token) saveSession({ token: data.token, user: data.user });
  return data;
}

export async function getLiveSession() {
  const sess = getSession();
  if (!sess?.token) return null;
  try {
    const data = await fetchJSON(`/auth/session/${encodeURIComponent(sess.token)}`);
    if (data?.valid) { saveSession({ token: sess.token, user: data.user }); return data; }
  } catch {}
  clearSession(); return null;
}

export function logout() { clearSession(); }
