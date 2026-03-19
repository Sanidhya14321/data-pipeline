import { Link } from "react-router-dom";
import PageWrapper from "../components/layout/PageWrapper";

export default function LoginPage() {
  return (
    <PageWrapper>
      <div className="auth-page">
        <div className="auth-card">
        <p className="eyebrow">Welcome Back</p>
        <h1>Log in to your workspace</h1>

        <label>
          Email
          <input type="email" placeholder="you@company.com" />
        </label>

        <label>
          Password
          <input type="password" placeholder="••••••••" />
        </label>

        <div className="auth-links">
          <a href="#">Forgot password?</a>
        </div>

        <button type="button" className="btn btn-primary btn-full">Log In</button>

        <div className="oauth-divider"><span>or continue with</span></div>

        <div className="oauth-grid">
          <button type="button" className="btn btn-outline btn-full">Google</button>
          <button type="button" className="btn btn-outline btn-full">GitHub</button>
        </div>

        <p className="auth-switch">
          New here? <Link to="/signup">Create an account</Link>
        </p>
        </div>
      </div>
    </PageWrapper>
  );
}
