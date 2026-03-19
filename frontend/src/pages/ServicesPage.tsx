import { Link } from "react-router-dom";
import PageWrapper from "../components/layout/PageWrapper";
import { services } from "../lib/theme";

export default function ServicesPage() {
  return (
    <PageWrapper>
      <div className="page-root page-offset section">
        <div className="container">
        <div className="section-heading">
          <p className="eyebrow">Services</p>
          <h1>Everything needed to operate a modern event intelligence stack.</h1>
          <p className="lead-copy">
            Services are modular, composable, and built to integrate with your existing architecture.
          </p>
        </div>

        <section className="services-grid">
          {services.map((service) => (
            <article key={service.id} className="service-card">
              <p className="service-metric">{service.metric}</p>
              <h3>{service.title}</h3>
              <p>{service.description}</p>
              <Link to="/contact" className="service-link">Talk to us</Link>
            </article>
          ))}
        </section>

        <section className="section why-us">
          <div>
            <p className="eyebrow">Why Us</p>
            <h2>We optimize for uptime, not demos.</h2>
            <p>
              Your pipeline should survive burst traffic, flaky sources, and connector regressions
              without dropping strategic visibility.
            </p>
          </div>
          <Link to="/signup" className="btn btn-primary">Get Started</Link>
        </section>
        </div>
      </div>
    </PageWrapper>
  );
}
