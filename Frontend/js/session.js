const KEY = "automark-session";
export function saveSession({ token, user }) { localStorage.setItem(KEY, JSON.stringify({ token, user })); }
export function getSession() { try { return JSON.parse(localStorage.getItem(KEY)); } catch { return null; } }
export function getToken() { return getSession()?.token ?? null; }
export function clearSession() { localStorage.removeItem(KEY); }
