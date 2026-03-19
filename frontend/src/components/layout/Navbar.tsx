import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { motion } from "framer-motion";
import { cn } from "../../lib/utils";
import { navLinks } from "../../lib/theme";

export default function Navbar() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  const location = useLocation();

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    window.addEventListener("scroll", onScroll);
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={cn(
        "site-navbar",
        scrolled ? "site-navbar-scrolled" : "site-navbar-top"
      )}
    >
      <div className="container nav-shell">
        <Link to="/" className="brand-mark" aria-label="Data Pipeline Home">
          <span className="brand-kicker">Realtime</span>
          <span className="brand-name">Data Pipeline</span>
        </Link>

        <nav className="nav-desktop" aria-label="Primary">
          {navLinks.map((link) => {
            const active =
              link.to === "/"
                ? location.pathname === "/"
                : location.pathname.startsWith(link.to);

            return (
              <Link
                key={link.to}
                to={link.to}
                className={cn("nav-link", active && "nav-link-active")}
              >
                {link.label}
                {active ? (
                  <motion.span
                    layoutId="nav-active-pill"
                    className="nav-active-pill"
                    transition={{ type: "spring", stiffness: 420, damping: 34 }}
                  />
                ) : null}
              </Link>
            );
          })}
        </nav>

        <div className="nav-actions nav-desktop">
          <Link to="/login" className="btn btn-ghost">Log in</Link>
          <Link to="/signup" className="btn btn-primary">Start Free</Link>
        </div>

        <button
          type="button"
          className="nav-toggle"
          onClick={() => setOpen((prev) => !prev)}
          aria-expanded={open}
          aria-controls="mobile-nav"
          aria-label="Toggle menu"
        >
          <span />
          <span />
          <span />
        </button>
      </div>

      <div id="mobile-nav" className={cn("mobile-drawer", open && "mobile-drawer-open")}>
        <div className="container mobile-drawer-inner">
          {navLinks.map((link) => (
            <Link
              key={link.to}
              to={link.to}
              className="mobile-link"
              onClick={() => setOpen(false)}
            >
              {link.label}
            </Link>
          ))}
          <div className="mobile-auth">
            <Link to="/login" className="btn btn-ghost" onClick={() => setOpen(false)}>
              Log in
            </Link>
            <Link to="/signup" className="btn btn-primary" onClick={() => setOpen(false)}>
              Start Free
            </Link>
          </div>
        </div>
      </div>
    </header>
  );
}
