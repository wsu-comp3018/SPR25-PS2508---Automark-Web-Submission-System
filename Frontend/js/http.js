import { API_BASE_URL } from "./config.js";

export async function fetchJSON(path, { method="GET", headers={}, body } = {}) {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: { "Content-Type": "application/json", ...headers },
    body: body ? JSON.stringify(body) : undefined
  });
  const ct = res.headers.get("content-type") || "";
  const data = ct.includes("application/json") ? await res.json() : await res.text();
  if (!res.ok) {
    const msg = (data && (data.detail || data.message)) || res.statusText || "Request failed";
    const err = new Error(msg); err.status = res.status; err.data = data; throw err;
  }
  return data;
}
