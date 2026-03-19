import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import PageWrapper from "../components/layout/PageWrapper";

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
    <PageWrapper>
      <div className="page-root">
        <section className="hero section">
          <motion.div className="container hero-grid" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
            <div className="hero-copy">
              <motion.p
                className="eyebrow"
                initial={{ opacity: 0, y: 24 }}
                animate={{ opacity: 1, y: 0, transition: { duration: 0.35, delay: 0.06 } }}
              >
                Event Intelligence Platform
              </motion.p>
              <motion.h1
                initial={{ opacity: 0, y: 24 }}
                animate={{ opacity: 1, y: 0, transition: { duration: 0.42, delay: 0.14 } }}
              >
                Turn noisy web signals into
                <span className="hero-emphasis"> decision-grade intelligence.</span>
              </motion.h1>
              <motion.p
                className="hero-sub"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0, transition: { duration: 0.44, delay: 0.22 } }}
              >
                A resilient data pipeline with live ingestion, AI enrichment, semantic retrieval,
                and an automatic Groq fallback that keeps answers flowing during outages.
              </motion.p>
              <motion.div
                className="hero-actions"
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0, transition: { duration: 0.4, delay: 0.3 } }}
              >
                <Link to="/signup" className="btn btn-primary">Launch Workspace</Link>
                <Link to="/dashboard" className="btn btn-outline">View Live Dashboard</Link>
              </motion.div>
            </div>

            <motion.div
              className="hero-panel"
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0, transition: { duration: 0.48, delay: 0.18 } }}
            >
              <p className="hero-panel-title">Live Pipeline Snapshot</p>
              <div className="hero-metrics">
                <div>
                  <span>Events/day</span>
                  <strong>124,280</strong>
                </div>
                <div>
                  <span>Median latency</span>
                  <strong>182ms</strong>
                </div>
                <div>
                  <span>Healthy connectors</span>
                  <strong>18 / 19</strong>
                </div>
              </div>
            </motion.div>
          </motion.div>
        </section>

        <section className="section trust-strip">
          <div className="container trust-row">
            {trust.map((item) => (
              <span key={item}>{item}</span>
            ))}
          </div>
        </section>

        <motion.section
          className="section"
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-60px" }}
          transition={{ duration: 0.5 }}
        >
          <div className="container">
            <div className="section-heading">
              <p className="eyebrow">Core Capabilities</p>
              <h2>Designed for high-signal workflows.</h2>
            </div>
            <div className="feature-grid">
              {features.map((feature) => (
                <article key={feature.title} className="feature-card">
                  <h3>{feature.title}</h3>
                  <p>{feature.description}</p>
                </article>
              ))}
            </div>
          </div>
        </motion.section>

        <motion.section
          className="section how-it-works"
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-60px" }}
          transition={{ duration: 0.5 }}
        >
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
        </motion.section>

        <motion.section
          className="section testimonials"
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-60px" }}
          transition={{ duration: 0.5 }}
        >
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
        </motion.section>

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
    </PageWrapper>
  );
}
