import { Link } from "react-router-dom";

export default function Footer() {
  return (
    <footer className="site-footer">
      <div className="container footer-grid">
        <div>
          <p className="footer-brand">Data Pipeline</p>
          <p className="footer-copy">
            High-signal event intelligence from live sources, transformed into searchable insights.
          </p>
        </div>

        <div>
          <p className="footer-title">Platform</p>
          <ul className="footer-list">
            <li><Link to="/services">Capabilities</Link></li>
            <li><Link to="/dashboard">Live Dashboard</Link></li>
            <li><Link to="/contact">Integrations</Link></li>
          </ul>
        </div>

        <div>
          <p className="footer-title">Company</p>
          <ul className="footer-list">
            <li><Link to="/about">About</Link></li>
            <li><Link to="/contact">Contact</Link></li>
            <li><Link to="/signup">Get Started</Link></li>
          </ul>
        </div>

        <div>
          <p className="footer-title">Stay Updated</p>
          <p className="footer-copy">Get release updates and connector alerts in your inbox.</p>
          <div className="footer-newsletter">
            <input type="email" placeholder="you@company.com" aria-label="Email" />
            <button type="button" className="btn btn-primary">Subscribe</button>
          </div>
        </div>
      </div>

      <div className="container footer-bottom">
        <span>© 2026 Data Pipeline. All rights reserved.</span>
        <div className="footer-bottom-links">
          <a href="#">Privacy</a>
          <a href="#">Terms</a>
          <a href="#">Security</a>
        </div>
      </div>
    </footer>
  );
}
