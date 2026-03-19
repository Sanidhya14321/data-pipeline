import { useState } from "react";
import PageWrapper from "../components/layout/PageWrapper";

export default function ContactPage() {
  const [sent, setSent] = useState(false);

  return (
    <PageWrapper>
      <div className="page-root page-offset section">
        <div className="container contact-layout">
        <section className="contact-form-shell">
          <p className="eyebrow">Contact</p>
          <h1>Tell us what you need.</h1>
          <p className="lead-copy">
            Share your use case, sources, and expected scale. We will suggest an architecture path.
          </p>

          <div className="contact-form-grid">
            <label>
              Name
              <input type="text" placeholder="Jane Doe" />
            </label>
            <label>
              Email
              <input type="email" placeholder="jane@company.com" />
            </label>
            <label className="full-width">
              Subject
              <input type="text" placeholder="Pipeline modernization" />
            </label>
            <label className="full-width">
              Message
              <textarea rows={5} placeholder="Current stack, pain points, goals..." />
            </label>
            <button type="button" className="btn btn-primary" onClick={() => setSent(true)}>
              Send Message
            </button>
            {sent ? <p className="form-success">Thanks. We will get back within one business day.</p> : null}
          </div>
        </section>

        <aside className="contact-info-shell">
          <h2>Contact Details</h2>
          <ul>
            <li><strong>Email</strong><span>support@datapipeline.ai</span></li>
            <li><strong>Phone</strong><span>+91 98XX XXX XXX</span></li>
            <li><strong>Address</strong><span>Bengaluru, India</span></li>
            <li><strong>Hours</strong><span>Mon-Fri, 9:00-18:00 IST</span></li>
          </ul>
          <div className="map-placeholder">Map / office location</div>
        </aside>
        </div>
      </div>
    </PageWrapper>
  );
}
