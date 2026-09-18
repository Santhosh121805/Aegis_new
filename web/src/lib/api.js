// The dashboard's whole data contract: GET /agents/state, polled. Nothing is derived here.
const params = new URLSearchParams(window.location.search);

export const API_BASE = (params.get("api") || "http://127.0.0.1:8000").replace(/\/$/, "");
export const STATE_URL = `${API_BASE}/agents/state`;
export const POLL_MS = 1500;

// ?stub=1 renders docs/api_stub.json instead of polling, for offline previews.
export const USE_STUB = params.get("stub") === "1";
