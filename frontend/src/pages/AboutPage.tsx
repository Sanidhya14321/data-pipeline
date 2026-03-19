import PageWrapper from "../components/layout/PageWrapper";

const values = [
  "Reliability over novelty",
  "Operational clarity",
  "Schema-first engineering",
  "Human-centered intelligence"
];

const timeline = [
  { year: "2024", text: "Built the first ingestion + normalization workers." },
  { year: "2025", text: "Added semantic indexing and LLM enrichment pipeline." },
  { year: "2026", text: "Launched multi-source production telemetry dashboard." }
];

export default function AboutPage() {
  return (
    <PageWrapper>
      <div className="page-root page-offset section">
        <div className="container">
        <div className="section-heading">
          <p className="eyebrow">About</p>
          <h1>We build data systems that stay calm under pressure.</h1>
          <p className="lead-copy">
            Data Pipeline began with one simple problem: most event intelligence stacks break exactly
            when information velocity spikes. We designed a platform that keeps quality high while
            sources, load, and requirements evolve.
          </p>
        </div>

        <section className="about-grid">
          <article>
            <h3>Mission</h3>
            <p>
              Make high-value external intelligence accessible in real time through dependable,
              developer-friendly infrastructure.
            </p>
          </article>
          <article>
            <h3>Vision</h3>
            <p>
              Become the operating layer for organizations that make critical decisions from
              continuously changing information.
            </p>
          </article>
        </section>

        <section className="section">
          <h2 className="subheading">What We Value</h2>
          <div className="value-grid">
            {values.map((value) => (
              <div key={value} className="value-card">
                <span>•</span>
                <p>{value}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="section">
          <h2 className="subheading">Milestones</h2>
          <div className="timeline">
            {timeline.map((item) => (
              <div key={item.year} className="timeline-item">
                <strong>{item.year}</strong>
                <p>{item.text}</p>
              </div>
            ))}
          </div>
        </section>
        </div>
      </div>
    </PageWrapper>
  );
}
