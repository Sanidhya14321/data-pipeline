import { Link } from "react-router-dom";

const trust = ["SEC", "NewsAPI", "GitHub", "Kafka", "Qdrant", "Postgres"];

const features = [
  {
    title: "Ingest at Source Speed",
    description: "Stream from APIs, feeds, and filings with connector-level fault tolerance."
  },
  {
    title: "Normalize with Guarantees",
    description: "Transform every record into a consistent contract with traceable lineage."
  },
  {
    title: "Search by Meaning",
    description: "Semantic retrieval across all ingested events with relevance scoring."
  },
  {
    title: "Operate with Confidence",
    description: "Real-time telemetry for worker health, connector status, and throughput."
  }
];

const steps = [
  "Connect your data sources and define ingestion schedules.",
  "Process, classify, and enrich events automatically.",
  "Query intelligence through APIs and dashboards."
];

const testimonials = [
  {
    quote: "We cut analyst triage time by 61% in the first month.",
    by: "Head of Research, QuantDesk"
  },
  {
    quote: "The reliability model is exceptional; we finally trust our event feed.",
    by: "Platform Lead, Atlas Finance"
  },
  {
    quote: "Search quality is consistently strong even with noisy source data.",
    by: "Data Product Manager, SignalOS"
  }
];

export default function HomePage() {
  return (
    <div className="page-root">
      <section className="hero section">
        <div className="container hero-grid">
          <div className="hero-copy reveal-up">
            <p className="eyebrow">Event Intelligence Platform</p>
            <h1>
              Turn live web data into
              <span className="hero-emphasis"> production-grade signals.</span>
            </h1>
            <p className="hero-sub">
              Ingest, normalize, enrich, and search high-value events in real time. Built for teams
              that need speed without sacrificing reliability.
            </p>
            <div className="hero-actions">
              <Link to="/signup" className="btn btn-primary">Launch Workspace</Link>
              <Link to="/dashboard" className="btn btn-outline">View Live Dashboard</Link>
            </div>
          </div>

          <div className="hero-panel reveal-up delay-1">
            <p className="hero-panel-title">Live Pipeline Snapshot</p>
            <div className="hero-metrics">
              <div>
                <span>Events/day</span>
                <strong>124,280</strong>
              </div>
              <div>
                <span>Mean latency</span>
                <strong>182ms</strong>
              </div>
              <div>
                <span>Healthy connectors</span>
                <strong>18 / 19</strong>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="section trust-strip">
        <div className="container trust-row">
          {trust.map((item) => (
            <span key={item}>{item}</span>
          ))}
        </div>
      </section>

      <section className="section">
        <div className="container">
          <div className="section-heading">
            <p className="eyebrow">Core Capabilities</p>
            <h2>Designed for high-signal workflows.</h2>
          </div>
          <div className="feature-grid">
            {features.map((feature, idx) => (
              <article key={feature.title} className={`feature-card reveal-up delay-${(idx % 3) + 1}`}>
                <h3>{feature.title}</h3>
                <p>{feature.description}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="section how-it-works">
        <div className="container">
          <div className="section-heading">
            <p className="eyebrow">How It Works</p>
            <h2>From raw feeds to actionable answers.</h2>
          </div>
          <ol className="steps-grid">
            {steps.map((step, index) => (
              <li key={step} className="step-item">
                <span>{`0${index + 1}`}</span>
                <p>{step}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="section testimonials">
        <div className="container">
          <div className="section-heading">
            <p className="eyebrow">What Teams Say</p>
            <h2>Trusted in real production environments.</h2>
          </div>
          <div className="testimonial-grid">
            {testimonials.map((item) => (
              <blockquote key={item.by} className="testimonial-card">
                <p>"{item.quote}"</p>
                <cite>{item.by}</cite>
              </blockquote>
            ))}
          </div>
        </div>
      </section>

      <section className="section final-cta">
        <div className="container cta-shell">
          <div>
            <p className="eyebrow">Ready to Ship</p>
            <h2>Deploy an event pipeline your team can trust.</h2>
          </div>
          <Link to="/signup" className="btn btn-primary">Create Account</Link>
        </div>
      </section>
    </div>
  );
}
