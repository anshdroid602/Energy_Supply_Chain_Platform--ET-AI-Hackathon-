// Thin fetch wrapper over the FastAPI backend (api/main.py). One file, no
// client-side framework beyond fetch — this project's differentiation is
// the backend (scenario engine + LangGraph pipeline), not the frontend
// plumbing, so this stays deliberately simple.

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${options.method || "GET"} ${path} -> ${res.status}: ${text}`);
  }
  return res.json();
}

export const getMeta = () => request("/meta");

export const getGraph = (windowDays = 30, halfLifeDays = 7) =>
  request(`/graph?window_days=${windowDays}&half_life_days=${halfLifeDays}`);

export const getVessels = (limit = 500) => request(`/vessels/latest?limit=${limit}`);

export const getCorridorRiskScore = (corridor, windowDays = 30, halfLifeDays = 7) =>
  request(`/corridors/${encodeURIComponent(corridor)}/risk-score?window_days=${windowDays}&half_life_days=${halfLifeDays}`);

export const runScenario = (params) =>
  request("/scenario/run", { method: "POST", body: JSON.stringify(params) });

export const runPipeline = (payload) =>
  request("/pipeline/run", { method: "POST", body: JSON.stringify(payload) });

export const getFreshness = () => request("/freshness");

export { API_BASE };
