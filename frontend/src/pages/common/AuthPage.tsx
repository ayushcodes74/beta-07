import { useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AlertCircle, ArrowRight, BookOpen, Check, GraduationCap, ShieldCheck, Sparkles } from "lucide-react";
import { authService, extractErrorMessage } from "../../services/api";
import { isDemoMode, setDemoSession } from "../../services/demo-session";
import { Button, Panel } from "../../components/ui";
import type { User } from "../../types/models";

export function AuthPage({
  mode,
  onAuthenticated,
}: {
  mode: "login" | "register";
  onAuthenticated: (user: User) => void;
}) {
  const navigate = useNavigate();
  const submissionInProgress = useRef(false);
  const [role, setRole] = useState<"teacher" | "student">("teacher");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const register = mode === "register";

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (submissionInProgress.current) return;
    setError("");
    setNotice("");
    const form = new FormData(event.currentTarget);
    const email = String(form.get("email") ?? "").trim();
    const password = String(form.get("password") ?? "");
    const name = String(form.get("name") ?? "").trim();

    if (register && !name) {
      setError("Enter your name to create an account.");
      return;
    }
    if (!email.includes("@") || password.length < 6) {
      setError("Use a valid email and a password of at least 6 characters.");
      return;
    }

    submissionInProgress.current = true;
    setLoading(true);
    try {
      if (register) {
        const user = await authService.register(name, email, password, role);
        onAuthenticated(user);
      } else {
        onAuthenticated(await authService.login(email, password));
      }
      navigate("/app");
    } catch (reason) {
      const message = extractErrorMessage(
        reason,
        "Authentication failed. Check your credentials and server status."
      );
      const isEmailRateLimited =
        /email rate limit exceeded/i.test(message) ||
        (typeof reason === "object" &&
          reason !== null &&
          "code" in reason &&
          (reason as { code?: string }).code === "over_email_send_rate_limit");
      setError(
        isEmailRateLimited
          ? "Confirmation emails are temporarily rate-limited. Please wait a moment before trying again."
          : message
      );
    } finally {
      submissionInProgress.current = false;
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-backdrop" />
      <Link to="/" className="brand auth-brand">
        <span className="brand-mark">
          <Check size={19} />
        </span>
        <span className="brand-word">
          Trust<span>Grade</span>
        </span>
      </Link>
      <div className="auth-layout">
        <section className="auth-story">
          <span className="eyebrow">A MORE THOUGHTFUL ACADEMIC PLATFORM</span>
          <h1>
            Clarity for your work.
            <br />
            <em>Confidence in every evaluation.</em>
          </h1>
          <p>Intelligent, course-grounded assistance that respects the faculty and students at the heart of learning.</p>
          <div className="auth-promise">
            <ShieldCheck size={18} />
            <span>
              <strong>AI assists. Teachers decide.</strong>
              <small>Human authority is always the final word.</small>
            </span>
          </div>
        </section>
        <Panel className="auth-card">
          <span className="eyebrow">{register ? "JOIN YOUR CLASSROOM" : "WELCOME BACK"}</span>
          <h2>{register ? "Create your account" : "Welcome back"}</h2>
          <p>{register ? "Join an intelligent, clear way to teach and learn." : "Sign in to your TrustGrade workspace."}</p>

          {isDemoMode() && (
            <div className="demo-login-callout">
              <div className="demo-callout-text">
                <Sparkles size={16} />
                <span>Hackathon Demo Active</span>
              </div>
              <div className="demo-callout-actions">
                <button
                  type="button"
                  className="demo-switch-btn"
                  onClick={() => {
                    const u = setDemoSession("teacher");
                    onAuthenticated(u);
                    navigate("/app");
                  }}
                >
                  Faculty Demo
                </button>
                <button
                  type="button"
                  className="demo-switch-btn"
                  onClick={() => {
                    const u = setDemoSession("student");
                    onAuthenticated(u);
                    navigate("/app");
                  }}
                >
                  Student Demo
                </button>
                <Link to="/demo" className="demo-switch-btn" style={{ textDecoration: "none" }}>
                  All Roles →
                </Link>
              </div>
            </div>
          )}

          <form onSubmit={submit}>
            {register && (
              <div className="field-block">
                <label htmlFor="name">Your name</label>
                <input
                  className="field-input"
                  id="name"
                  name="name"
                  autoComplete="name"
                  placeholder="Professor Morgan"
                  required
                />
              </div>
            )}
            <div className="field-block">
              <label htmlFor="email">Email address</label>
              <input
                className="field-input"
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                placeholder="you@university.edu"
                required
              />
            </div>
            <div className="field-block">
              <div className="field-label-row">
                <label htmlFor="password">Password</label>
              </div>
              <input
                className="field-input"
                id="password"
                name="password"
                type="password"
                autoComplete={register ? "new-password" : "current-password"}
                minLength={6}
                placeholder="At least 6 characters"
                required
              />
            </div>
            {register && (
              <div className="field-block">
                <label>Role</label>
                <div className="role-picker">
                  {(["teacher", "student"] as const).map((value) => (
                    <button
                      type="button"
                      key={value}
                      className={role === value ? "active" : ""}
                      onClick={() => setRole(value)}
                    >
                      <span>{value === "teacher" ? <GraduationCap size={16} /> : <BookOpen size={16} />}</span>
                      {value === "teacher" ? "Faculty" : "Student"}
                      {role === value && <Check size={13} />}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {error && (
              <div role="alert" className="form-error">
                <AlertCircle size={14} />
                {error}
              </div>
            )}
            {notice && (
              <div role="status" className="form-success">
                {notice}
              </div>
            )}
            <Button className="full-button" disabled={loading}>
              {loading ? (
                <>
                  <span className="button-spinner" />
                  {register ? "Creating account…" : "Signing in…"}
                </>
              ) : (
                <>
                  {register ? "Create account" : "Sign in"}
                  <ArrowRight size={14} />
                </>
              )}
            </Button>
          </form>
          <div className="auth-switch">
            {register ? "Already have an account?" : "New to TrustGrade?"}{" "}
            <Link to={register ? "/login" : "/register"}>{register ? "Sign in" : "Create account"}</Link>
          </div>
        </Panel>
      </div>
      <footer className="auth-footer">
        <span>© 2026 TrustGrade</span>
        <span>AI assists. Teachers decide. Students understand.</span>
      </footer>
    </div>
  );
}

