import { useState } from "react";
import { Link } from "react-router-dom";
import PageWrapper from "../components/layout/PageWrapper";

export default function SignupPage() {
  const [agree, setAgree] = useState(false);

  return (
    <PageWrapper>
      <div className="auth-page">
        <div className="auth-card">
        <p className="eyebrow">Create Account</p>
        <h1>Start your production pipeline</h1>

        <label>
          Full Name
          <input type="text" placeholder="Jane Doe" />
        </label>

        <label>
          Email
          <input type="email" placeholder="you@company.com" />
        </label>

        <label>
          Password
          <input type="password" placeholder="••••••••" />
        </label>

        <label>
          Confirm Password
          <input type="password" placeholder="••••••••" />
        </label>

        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={agree}
            onChange={(event) => setAgree(event.target.checked)}
          />
          <span>I agree to the Terms and Privacy Policy</span>
        </label>

        <button type="button" className="btn btn-primary btn-full" disabled={!agree}>
          Create Account
        </button>

        <p className="auth-switch">
          Already have an account? <Link to="/login">Log in</Link>
        </p>
        </div>
      </div>
    </PageWrapper>
  );
}
