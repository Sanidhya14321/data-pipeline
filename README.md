# Real-Time Web Data Ingestion Pipeline

A high-performance financial data pipeline with semantic search, LLM-powered classification, and graceful fallback to Groq + web scraping when vector search is unavailable.

## 🏗️ Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     DATA INGESTION LAYER                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  RSS Feeds  │  News API  │  SEC EDGAR  │  GitHub  │  Twitter    │
│     ↓       │     ↓      │      ↓      │    ↓    │      ↓       │
│  Connector Runners (CronJobs, every 5 min)                       │
│  - Fetch raw content                                             │
│  - Detect duplicates (redis dedup)                               │
│  - Emit to Kafka raw.events topic                                │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              KAFKA STREAM PROCESSING                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  raw.events ──→ Normalizer Worker                                │
│                 - Quality gate (Groq)                            │
│                 - Classification (Groq)                          │
│                 - Entity extract (Groq)                          │
│                 - Summarization (Groq)                           │
│                 - Write to PostgreSQL                            │
│                 ↓                                                 │
│         normalized.events topic                                  │
│                 ↓                                                 │
│             Vectorizer Worker                                    │
│             - Embed text (all-MiniLM-L6-v2)                      │
│             - Write to Qdrant                                    │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│           STORAGE & VECTOR INDEX                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  PostgreSQL          │  Qdrant Vector DB      │  Redis          │
│  - raw_events        │  - Embeddings          │  - Session      │
│  - norm_articles     │  - Semantic search     │  - Dedup cache  │
│  - connector_state   │                        │  - Rate limits  │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              API & QUERY LAYER                                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  FastAPI Server                                                  │
│  ├─ /api/v1/search (Qdrant vector search)                        │
│  │  └─ Fallback: Groq + web scrape if Qdrant ✗                  │
│  ├─ /api/v1/health                                               │
│  ├─ /api/v1/ready                                                │
│  ├─ /api/v1/stats                                                │
│  └─ /metrics (Prometheus)                                        │
│                                                                   │
│  Frontend (React + Vite)                                         │
│  ├─ HomePage (hero, features, CTA)                               │
│  ├─ SearchDashboard (semantic search UI)                         │
│  ├─ About / Services / Contact pages                             │
│  └─ Graceful degradation on API errors                           │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

![flowchart](/data-pipeline/flowchart.png)


## 🔄 Fallback Search Flow

When Qdrant is unavailable or slow:

```
User Query
    ↓
[API /search endpoint]
    ↓
Try: Qdrant semantic search
    ├─ Success → Return vector results (score > 0.5)
    └─ Failure → Trigger fallback
         ↓
    [Groq + Web Scrape Fallback]
    ├─ Rewrite query for web recall (Groq)
    ├─ Fetch RSS feed (Google News + query)
    ├─ Scrape article pages in parallel (aiohttp 6 concurrent, 10s timeout)
    ├─ Summarize articles (Groq)
    └─ Return web results (score 0.25-0.85)
         ↓
    Frontend displays search results (vector or web hybrid)
```

**Fallback triggers when:**
- Qdrant unavailable (503 Service Unavailable)
- Qdrant timeout (>15s)
- Network error or API key invalid
- Vector search returns no results (optional threshold mode)

**Result scoring:**
- Qdrant results: `0.5` to `1.0` (vector similarity)
- Fallback results: `0.25` to `0.85` (position and content relevance)
- User sees best results first (sorted by score descending)

## 🚀 Why Docker Build Is Now Fast

### Previous approach (8 GB image, failed)
- Built from `worker.Dockerfile` for API server
- Included full ML stack: `sentence-transformers` (pulls large Torch/transformers)
- Build time: 30+ minutes, image size: 8+ GB
- Result: ❌ Exceeded Railway 4 GB limit, deployment failed

### Current approach (280 MB image, fast)
- Dedicated lightweight `docker/api.Dockerfile`
- Only essential API dependencies: FastAPI, Groq, Qdrant client
- **No `sentence-transformers`** → use Groq fallback instead
- Build time: ~2 minutes
- Image size: 280 MB ✅ Well under 4 GB limit

**Workers still use full stack (separate deployment):**
- Normalizer: deployed on Kubernetes, uses Groq for LLM calls
- Vectorizer: deployed on Kubernetes, uses `sentence-transformers` for embeddings
- Not deployed on Railway (no need for full ML stack on API server)

## 📦 Services

```bash
docker compose up -d
```

### 2. Run frontend locally

```bash
cd frontend
npm install
npm run dev
```

### 3. Build frontend for production

```bash
cd frontend
npm run build
```

## Deploy (Railway)

This repo includes `railway.toml` and a slim Docker path for API deployment.

### Required environment variables

- `PIPELINE_API_KEY`
- `DATABASE_URL`
- `QDRANT_URL`
- `QDRANT_API_KEY` (if required)
- `REDIS_URL`
- `GROQ_API_KEY`
- `KAFKA_BROKERS`
- `NEWS_API_KEY` (if connector path uses it)
- `SEC_USER_AGENT`

### Build config

- Builder: Dockerfile
- Dockerfile: `docker/api.Dockerfile`

## Frontend Revamp Notes

UI has been reworked with:

- Route transitions (`AnimatePresence`)
- Motion-enabled sections and hero choreography
- Updated token system (Neobrutalism x Swiss)
- Stronger typography and contrast
- Responsive nav and auth-first route behavior
- Reduced-motion accessibility fallback

## Health and Resilience

- API startup schema init is tolerant to transient backend failures
- Health endpoint reports degraded mode instead of hard crashing
- Search endpoint now degrades to Groq + scrape fallback when primary search fails

## Suggested Next Improvements

- Add response caching for fallback search to reduce Groq calls
- Add circuit breaker state metrics for fallback activation frequency
- Add integration tests for fallback path (`search` when Qdrant is unavailable)
- Split vector search into dedicated service if high throughput is required
