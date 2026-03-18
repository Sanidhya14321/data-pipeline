import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type HealthStatus = "ok" | "degraded" | "error" | "healthy" | string;

type HealthResponse = {
  status: HealthStatus;
  checks: Record<string, HealthStatus>;
  timestamp: string;
};

type StatsResponse = {
  events_today: number;
  events_total: number;
  sources_active: number;
  connectors: ConnectorState[];
};

type ConnectorState = {
  source_id: string;
  run_count: number;
  error_count: number;
  last_run: string | null;
  last_error: string | null;
};

type ThroughputPoint = {
  time: string;
  eventsPerMin: number;
};

type SearchFilter = {
  source_type?: string[];
  category?: string[];
};

type SearchResult = {
  id: string;
  title: string;
  summary: string;
  score: number;
  source: string;
  source_url: string;
  published: string;
  category: string;
  source_type: string;
};

type SearchResponse = {
  results: SearchResult[];
  total: number;
  latency_ms: number;
};

const rawApiBase = (import.meta as { env?: Record<string, string> }).env?.VITE_API_BASE || "";
const API_BASE = rawApiBase || (import.meta.env.DEV ? "http://127.0.0.1:8080" : "");
const PIPELINE_API_KEY =
  (import.meta as { env?: Record<string, string> }).env?.VITE_PIPELINE_API_KEY || "test-key";

// --- UI Components ---

function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-2xl border border-white/[0.05] bg-white/[0.02] p-6 backdrop-blur-sm shadow-xl shadow-black/10 transition-all ${className}`}>
      {children}
    </div>
  );
}

function StatusDot({ status }: { status: HealthStatus }) {
  const normalized = (status || "").toLowerCase();
  const colorClass =
    normalized === "ok" || normalized === "healthy"
      ? "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.5)]"
      : normalized === "degraded"
        ? "bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.5)]"
        : "bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.5)]";

  return <span className={`inline-block h-2 w-2 rounded-full ${colorClass}`} />;
}

function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <Card className="flex flex-col justify-between hover:bg-white/[0.04]">
      <p className="text-xs font-medium uppercase tracking-wider text-zinc-400">{label}</p>
      <div className="mt-4">
        <p className="text-4xl font-semibold tracking-tight text-white">
          {typeof value === "number" ? value.toLocaleString() : value}
        </p>
        {sub && <p className="mt-2 text-xs font-medium text-zinc-500">{sub}</p>}
      </div>
    </Card>
  );
}

function HealthPanel({ health }: { health: HealthResponse | null }) {
  if (!health) {
    return (
      <Card>
        <div className="mb-6 h-6 w-40 animate-pulse rounded bg-zinc-800" />
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
          {Array.from({ length: 6 }).map((_, idx) => (
            <div key={idx} className="h-10 animate-pulse rounded-xl bg-zinc-800" />
          ))}
        </div>
      </Card>
    );
  }

  const overall = (health.status || "error").toLowerCase();
  const badgeClass =
    overall === "ok" || overall === "healthy"
      ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
      : overall === "degraded"
        ? "bg-amber-500/10 text-amber-400 border-amber-500/20"
        : "bg-rose-500/10 text-rose-400 border-rose-500/20";

  return (
    <Card>
      <div className="mb-6 flex items-center justify-between">
        <h3 className="text-lg font-medium text-zinc-100 tracking-tight">System Health</h3>
        <span className={`rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-wider ${badgeClass}`}>
          {overall}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
        {Object.entries(health.checks || {}).map(([name, status]) => (
          <div key={name} className="flex items-center gap-3 rounded-xl border border-white/[0.02] bg-black/20 px-4 py-3 transition-colors hover:bg-black/40">
            <StatusDot status={status} />
            <span className="text-sm font-medium text-zinc-300">{name}</span>
          </div>
        ))}
      </div>
    </Card>
  );
}

function ThroughputChart({ data }: { data: ThroughputPoint[] }) {
  return (
    <Card>
      <h3 className="mb-6 text-lg font-medium text-zinc-100 tracking-tight">Throughput <span className="text-zinc-500 text-sm font-normal">(events/min)</span></h3>
      <div className="h-[200px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data}>
            <CartesianGrid stroke="#27272a" strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="time" stroke="#52525b" tick={{ fontSize: 11, fill: "#71717a" }} axisLine={false} tickLine={false} dy={10} />
            <YAxis stroke="#52525b" tick={{ fontSize: 11, fill: "#71717a" }} axisLine={false} tickLine={false} dx={-10} />
            <Tooltip
              contentStyle={{
                backgroundColor: "rgba(9, 9, 11, 0.9)",
                border: "1px solid rgba(255, 255, 255, 0.1)",
                borderRadius: "12px",
                backdropFilter: "blur(8px)",
                color: "#f4f4f5",
                boxShadow: "0 10px 15px -3px rgba(0, 0, 0, 0.5)",
              }}
              itemStyle={{ color: "#34d399" }}
            />
            <Line 
              type="monotone" 
              dataKey="eventsPerMin" 
              stroke="#34d399" 
              strokeWidth={3}
              dot={false}
              activeDot={{ r: 6, fill: "#059669", stroke: "#fff", strokeWidth: 2 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}

function ConnectorsTable({ connectors }: { connectors: ConnectorState[] }) {
  return (
    <Card className="overflow-hidden flex flex-col h-full">
      <h3 className="mb-6 text-lg font-medium text-zinc-100 tracking-tight">Active Connectors</h3>
      <div className="-mx-6 -mb-6 overflow-x-auto">
        <table className="w-full text-left text-sm whitespace-nowrap">
          <thead className="bg-white/[0.02] text-zinc-400">
            <tr>
              <th className="px-6 py-4 font-medium">Source</th>
              <th className="px-6 py-4 font-medium">Runs</th>
              <th className="px-6 py-4 font-medium">Errors</th>
              <th className="px-6 py-4 font-medium">Last Run</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/[0.05]">
            {connectors.map((connector) => {
              const status: HealthStatus = connector.error_count > 0 ? "degraded" : "ok";
              return (
                <tr key={connector.source_id} className="transition-colors hover:bg-white/[0.02]">
                  <td className="px-6 py-4 text-zinc-100">
                    <div className="flex items-center gap-3">
                      <StatusDot status={status} />
                      <span className="font-medium">{connector.source_id}</span>
                    </div>
                    {connector.last_error && (
                      <p className="mt-1.5 max-w-xs truncate text-xs text-rose-400">{connector.last_error}</p>
                    )}
                  </td>
                  <td className="px-6 py-4 text-zinc-300">{(connector.run_count || 0).toLocaleString()}</td>
                  <td className={`px-6 py-4 ${(connector.error_count || 0) > 0 ? "text-rose-400 font-medium" : "text-zinc-300"}`}>
                    {(connector.error_count || 0).toLocaleString()}
                  </td>
                  <td className="px-6 py-4 text-zinc-400">{formatDateTime(connector.last_run)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function SearchPanel() {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [sourceType, setSourceType] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  const runSearch = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setSearchError(null);
    try {
      const filters: SearchFilter = {};
      if (category) filters.category = [category];
      if (sourceType) filters.source_type = [sourceType];

      const payload: Record<string, unknown> = { query, top_k: 10 };
      if (Object.keys(filters).length > 0) payload.filter = filters;

      const response = await fetch(`${API_BASE}/api/v1/search`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Pipeline-Key": PIPELINE_API_KEY,
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const errorPayload = (await response.json().catch(() => ({}))) as { detail?: string };
        setResults([]);
        setLatencyMs(null);
        setSearchError(errorPayload.detail || `Search failed with HTTP ${response.status}`);
        return;
      }

      const data = (await response.json()) as SearchResponse;
      setResults(data.results || []);
      setLatencyMs(data.latency_ms ?? null);
    } catch {
      setResults([]);
      setLatencyMs(null);
      setSearchError("Cannot reach backend API. Check VITE_API_BASE and backend server.");
    } finally {
      setLoading(false);
    }
  };

  const inputClasses = "rounded-xl border border-white/[0.05] bg-black/20 px-4 py-2.5 text-sm text-zinc-100 placeholder-zinc-500 outline-none transition-all focus:border-emerald-500/50 focus:bg-black/40 focus:ring-1 focus:ring-emerald-500/50";

  return (
    <Card className="flex flex-col h-full">
      <div className="mb-6 flex items-center justify-between">
        <h3 className="text-lg font-medium text-zinc-100 tracking-tight">Semantic Search</h3>
        {latencyMs !== null && <span className="text-xs font-medium text-emerald-400 bg-emerald-400/10 px-2 py-1 rounded-md">{latencyMs}ms</span>}
      </div>
      
      {/* UPDATE: Added wrapping and responsive widths to this control block */}
      <div className="mb-6 flex flex-col gap-3 2xl:flex-row">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => { if (event.key === "Enter") void runSearch(); }}
          placeholder="Search events, entities, filings..."
          className={`w-full flex-1 ${inputClasses}`}
        />
        <div className="flex flex-wrap gap-3 sm:flex-nowrap">
          <select
            value={category}
            onChange={(event) => setCategory(event.target.value)}
            className={`flex-1 min-w-[130px] sm:w-36 sm:flex-none appearance-none ${inputClasses}`}
          >
            <option value="">All categories</option>
            <option value="EARNINGS">Earnings</option>
            <option value="MACRO">Macro</option>
            <option value="COMPANY_NEWS">Company News</option>
            <option value="REGULATORY">Regulatory</option>
            <option value="MARKET_DATA">Market Data</option>
            <option value="TECH">Tech</option>
          </select>
          <select
            value={sourceType}
            onChange={(event) => setSourceType(event.target.value)}
            className={`flex-1 min-w-[130px] sm:w-36 sm:flex-none appearance-none ${inputClasses}`}
          >
            <option value="">All sources</option>
            <option value="rss">RSS</option>
            <option value="api">API</option>
            <option value="sec">SEC</option>
            <option value="github">GitHub</option>
          </select>
          <button
            onClick={() => void runSearch()}
            disabled={loading}
            // UPDATE: Added 'w-full sm:w-auto shrink-0' to keep the button fully visible
            className="w-full sm:w-auto shrink-0 rounded-xl bg-emerald-500 px-6 py-2.5 text-sm font-semibold text-black transition-all hover:bg-emerald-400 active:scale-95 disabled:pointer-events-none disabled:opacity-50 shadow-[0_0_15px_rgba(16,185,129,0.3)] hover:shadow-[0_0_20px_rgba(52,211,153,0.4)]"
          >
            {loading ? "Searching" : "Search"}
          </button>
        </div>
      </div>

      <div className="space-y-3 overflow-y-auto max-h-[400px] pr-2 custom-scrollbar">
        {searchError ? (
          <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
            {searchError}
          </div>
        ) : null}
        {results.map((item) => (
          <a
            key={item.id}
            href={item.source_url}
            target="_blank"
            rel="noreferrer"
            className="group block rounded-xl border border-white/[0.05] bg-black/20 p-4 transition-all hover:border-emerald-500/30 hover:bg-white/[0.02]"
          >
            <div className="mb-2 flex items-start justify-between gap-4">
              <h4 className="text-sm font-medium text-zinc-100 group-hover:text-emerald-400 transition-colors line-clamp-1">{item.title}</h4>
              <span className="shrink-0 rounded-md bg-emerald-500/10 px-2 py-1 text-xs font-medium text-emerald-400">
                {Math.round(item.score * 100)}%
              </span>
            </div>
            <p className="mb-3 text-xs leading-relaxed text-zinc-400 line-clamp-2">{item.summary}</p>
            <div className="flex items-center gap-3 text-xs font-medium text-zinc-500">
              <span className="rounded-md border border-white/5 bg-white/5 px-2 py-1 text-zinc-300">{item.category}</span>
              <span className="flex items-center gap-1.5">
                <span className="h-1 w-1 rounded-full bg-zinc-600"></span>
                {formatDate(item.published)}
              </span>
            </div>
          </a>
        ))}
        {results.length === 0 && !loading && (
           <div className="py-10 text-center text-sm text-zinc-500 flex flex-col items-center">
             <span className="block mb-2 text-2xl opacity-20">⌘</span>
             Enter a query to explore the pipeline
           </div>
        )}
      </div>
    </Card>
  );
}
// --- Helpers ---

function formatDate(value: string): string {
  if (!value) return "-";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function formatDateTime(value: string | null): string {
  if (!value) return "-";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

// --- Main App ---

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [throughputData, setThroughputData] = useState<ThroughputPoint[]>([]);
  const [lastStatsSample, setLastStatsSample] = useState<{ ts: number; eventsToday: number } | null>(null);

  // Data fetching logic remains exactly the same
  useEffect(() => {
    let active = true;
    const fetchHealth = async () => {
      try {
        const response = await fetch(`${API_BASE}/api/v1/health`);
        const data = (await response.json()) as HealthResponse;
        if (active) setHealth(data);
      } catch {
        if (active) setHealth({ status: "error", checks: { api: "error" }, timestamp: new Date().toISOString() });
      }
    };
    void fetchHealth();
    const interval = window.setInterval(() => void fetchHealth(), 10_000);
    return () => { active = false; window.clearInterval(interval); };
  }, []);

  useEffect(() => {
    let active = true;
    const fetchStats = async () => {
      try {
        const response = await fetch(`${API_BASE}/api/v1/stats`);
        const data = (await response.json()) as StatsResponse;
        if (!active) return;
        setStats(data);
        const now = Date.now();
        setLastStatsSample((previous) => {
          if (!previous) return { ts: now, eventsToday: data.events_today || 0 };
          const minutesElapsed = Math.max((now - previous.ts) / 60_000, 0.001);
          const delta = Math.max((data.events_today || 0) - previous.eventsToday, 0);
          const eventsPerMin = Math.round(delta / minutesElapsed);
          setThroughputData((existing) => {
            const label = new Date(now).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
            return [...existing, { time: label, eventsPerMin }].slice(-30);
          });
          return { ts: now, eventsToday: data.events_today || 0 };
        });
      } catch {}
    };
    void fetchStats();
    const interval = window.setInterval(() => void fetchStats(), 15_000);
    return () => { active = false; window.clearInterval(interval); };
  }, []);

  const statsCards = useMemo(() => [
    { label: "Events Today", value: stats?.events_today ?? 0, sub: "Last 24h ingested" },
    { label: "Events Total", value: stats?.events_total ?? 0, sub: "All-time normalized" },
    { label: "Sources Active", value: stats?.sources_active ?? 0, sub: "Reporting this window" },
    { label: "Connectors", value: stats?.connectors?.length ?? 0, sub: "Configured workers" },
  ], [stats]);

  return (
    <div className="min-h-screen bg-[#09090b] text-zinc-100 font-sans selection:bg-emerald-500/30">
      {/* Subtle background glow */}
      <div className="pointer-events-none fixed inset-0 flex justify-center overflow-hidden">
        <div className="h-[40rem] w-[80rem] bg-emerald-500/[0.03] blur-[120px] rounded-full mt-[-20rem]"></div>
      </div>

      <div className="relative mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <header className="mb-10 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <div className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse shadow-[0_0_8px_rgba(16,185,129,0.8)]" />
              <span className="text-xs font-semibold uppercase tracking-widest text-emerald-500">Live Telemetry</span>
            </div>
            <h1 className="text-3xl font-semibold tracking-tight text-white sm:text-4xl">Pipeline Dashboard</h1>
          </div>
          <div className="flex items-center gap-2 rounded-full border border-white/5 bg-white/[0.02] px-4 py-2 text-xs font-medium text-zinc-400 backdrop-blur-md">
            <span className="flex h-2 w-2">
              <span className="absolute inline-flex h-2 w-2 animate-ping rounded-full bg-zinc-400 opacity-75"></span>
              <span className="relative inline-flex h-2 w-2 rounded-full bg-zinc-500"></span>
            </span>
            Last updated: {new Date().toLocaleTimeString()}
          </div>
        </header>

        <section className="mb-6 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {statsCards.map((card) => (
            <StatCard key={card.label} label={card.label} value={card.value} sub={card.sub} />
          ))}
        </section>

        <section className="mb-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
          <ThroughputChart data={throughputData} />
          <HealthPanel health={health} />
        </section>

        <section className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <ConnectorsTable connectors={stats?.connectors || []} />
          <SearchPanel />
        </section>

        <footer className="mt-12 flex items-center justify-between border-t border-white/5 pt-8 text-xs font-medium text-zinc-500">
          <p>Pipeline v1.0 Enterprise</p>
          <div className="flex items-center gap-4">
            <span>Kafka</span>
            <span>·</span>
            <span>Qdrant</span>
            <span>·</span>
            <span>PostgreSQL</span>
          </div>
        </footer>
      </div>
    </div>
  );
}