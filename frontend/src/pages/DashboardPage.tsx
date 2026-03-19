import { useEffect, useMemo, useState } from "react";
import PageWrapper from "../components/layout/PageWrapper";

type HealthStatus = "ok" | "degraded" | "error" | "healthy" | string;

type HealthResponse = {
  status: HealthStatus;
  checks: Record<string, HealthStatus>;
  timestamp: string;
};

type ConnectorState = {
  source_id: string;
  run_count: number;
  error_count: number;
  last_run: string | null;
  last_error: string | null;
};

type StatsResponse = {
  events_today: number;
  events_total: number;
  sources_active: number;
  connectors: ConnectorState[];
};

type SearchResult = {
  id: string;
  title: string;
  summary: string;
  source_url: string;
  category: string;
  score: number;
};

type SearchResponse = {
  results: SearchResult[];
  latency_ms: number;
};

const rawApiBase = (import.meta as { env?: Record<string, string> }).env?.VITE_API_BASE || "";
const apiBase = rawApiBase || (import.meta.env.DEV ? "http://127.0.0.1:8080" : "");
const pipelineKey =
  (import.meta as { env?: Record<string, string> }).env?.VITE_PIPELINE_API_KEY || "dev-key";

function formatDateTime(value: string | null): string {
  if (!value) return "-";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function statusClass(status: HealthStatus): string {
  const normalized = status.toLowerCase();
  if (normalized === "ok" || normalized === "healthy") return "pill-ok";
  if (normalized === "degraded") return "pill-degraded";
  return "pill-error";
}

export default function DashboardPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searchLatency, setSearchLatency] = useState<number | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    const fetchHealth = async () => {
      try {
        const response = await fetch(`${apiBase}/api/v1/health`);
        const data = (await response.json()) as HealthResponse;
        if (active) setHealth(data);
      } catch {
        if (active) {
          setHealth({
            status: "error",
            checks: { api: "error" },
            timestamp: new Date().toISOString()
          });
        }
      }
    };

    const fetchStats = async () => {
      try {
        const response = await fetch(`${apiBase}/api/v1/stats`);
        const data = (await response.json()) as StatsResponse;
        if (active) setStats(data);
      } catch {
        if (active) setStats(null);
      }
    };

    void fetchHealth();
    void fetchStats();

    const healthTicker = window.setInterval(() => void fetchHealth(), 10000);
    const statsTicker = window.setInterval(() => void fetchStats(), 15000);

    return () => {
      active = false;
      window.clearInterval(healthTicker);
      window.clearInterval(statsTicker);
    };
  }, []);

  const cards = useMemo(
    () => [
      { label: "Events Today", value: stats?.events_today ?? 0 },
      { label: "Events Total", value: stats?.events_total ?? 0 },
      { label: "Sources Active", value: stats?.sources_active ?? 0 },
      { label: "Connectors", value: stats?.connectors?.length ?? 0 }
    ],
    [stats]
  );

  const runSearch = async () => {
    if (!query.trim()) return;

    setSearchLoading(true);
    setSearchError(null);

    try {
      const response = await fetch(`${apiBase}/api/v1/search`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Pipeline-Key": pipelineKey
        },
        body: JSON.stringify({ query, top_k: 8 })
      });

      if (!response.ok) {
        const payload = (await response.json().catch(() => ({}))) as { detail?: string };
        setSearchResults([]);
        setSearchLatency(null);
        setSearchError(payload.detail || `Search failed with HTTP ${response.status}`);
        setSearchLoading(false);
        return;
      }

      const data = (await response.json()) as SearchResponse;
      setSearchResults(data.results || []);
      setSearchLatency(data.latency_ms ?? null);
    } catch {
      setSearchResults([]);
      setSearchLatency(null);
      setSearchError("Cannot reach backend API.");
    }

    setSearchLoading(false);
  };

  return (
    <PageWrapper>
      <div className="page-root page-offset section dashboard-page">
        <div className="container">
        <div className="section-heading">
          <p className="eyebrow">Telemetry</p>
          <h1>Production Dashboard</h1>
          <p className="lead-copy">
            Monitor health, connector execution, and semantic retrieval from your live deployment.
          </p>
        </div>

        <section className="dashboard-card-grid">
          {cards.map((card) => (
            <article key={card.label} className="metric-card">
              <span>{card.label}</span>
              <strong>{card.value.toLocaleString()}</strong>
            </article>
          ))}
        </section>

        <section className="dashboard-panels">
          <article className="panel">
            <h2>System Health</h2>
            <div className="pill-row">
              <span className={`pill ${statusClass(health?.status || "error")}`}>{health?.status || "error"}</span>
              <span className="muted">
                {health?.timestamp ? new Date(health.timestamp).toLocaleTimeString() : "No data"}
              </span>
            </div>
            <div className="checks-grid">
              {Object.entries(health?.checks || {}).map(([name, value]) => (
                <div key={name} className="check-item">
                  <span>{name}</span>
                  <span className={`pill ${statusClass(value)}`}>{value}</span>
                </div>
              ))}
            </div>
          </article>

          <article className="panel">
            <h2>Connector Runtime</h2>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Source</th>
                    <th>Runs</th>
                    <th>Errors</th>
                    <th>Last Run</th>
                  </tr>
                </thead>
                <tbody>
                  {(stats?.connectors || []).map((connector) => (
                    <tr key={connector.source_id}>
                      <td>{connector.source_id}</td>
                      <td>{connector.run_count.toLocaleString()}</td>
                      <td>{connector.error_count.toLocaleString()}</td>
                      <td>{formatDateTime(connector.last_run)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>
        </section>

        <section className="panel search-panel">
          <div className="search-head">
            <h2>Semantic Search</h2>
            {searchLatency !== null ? <span className="pill pill-info">{searchLatency}ms</span> : null}
          </div>

          <div className="search-controls">
            <input
              type="text"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") void runSearch();
              }}
              placeholder="Search filings, entities, topics..."
            />
            <button type="button" className="btn btn-primary" onClick={() => void runSearch()} disabled={searchLoading}>
              {searchLoading ? "Searching" : "Search"}
            </button>
          </div>

          {searchError ? <p className="error-text">{searchError}</p> : null}

          <div className="search-results">
            {searchResults.map((result) => (
              <a key={result.id} href={result.source_url} target="_blank" rel="noreferrer" className="search-item">
                <div>
                  <h3>{result.title}</h3>
                  <p>{result.summary}</p>
                </div>
                <div className="search-meta">
                  <span className="pill pill-info">{Math.round(result.score * 100)}%</span>
                  <span className="muted">{result.category}</span>
                </div>
              </a>
            ))}
            {!searchLoading && searchResults.length === 0 ? (
              <p className="muted">No results yet. Enter a query to test your deployment.</p>
            ) : null}
          </div>
        </section>
        </div>
      </div>
    </PageWrapper>
  );
}
