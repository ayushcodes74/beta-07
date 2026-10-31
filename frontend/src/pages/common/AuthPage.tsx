import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AlertCircle, ArrowRight, GraduationCap, ShieldCheck } from "lucide-react";
import { signIn, signUp } from "../../services/auth";
import { Button, Panel } from "../../components/ui";
import { useAppState } from "../../App";

export function AuthPage({ register = false }: { register?: boolean }) {
  const navigate = useNavigate();
  const { refreshSession } = useAppState();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (register) await signUp(email, password);
      await signIn(email, password);
      const failure = await refreshSession();
      if (failure) {
        setError(failure);
        return;
      }
      navigate("/app");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : `Unable to ${register ? "create" : "sign in to"} your account.`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="auth-page">
      <div className="auth-backdrop" />
      <Link to="/" className="tg-nav-brand auth-brand"><span className="tg-brand-symbol"><GraduationCap size={18} /></span><span className="tg-brand-name">Trust<span>Grade</span></span></Link>
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
          <h2>{register ? "Create your account" : "Sign in to TrustGrade"}</h2>
          <p>{register ? "Register for a faculty or student account." : "Use the account credentials provided by your institution."}</p>
          <form onSubmit={submit}>
            <div className="field-block">
              <label htmlFor="email">Email address</label>
              <input className="field-input" id="email" type="email" autoComplete="email" placeholder="you@university.edu" value={email} onChange={(event) => setEmail(event.target.value)} required />
            </div>
            <div className="field-block">
              <label htmlFor="password">Password</label>
              <input className="field-input" id="password" type="password" autoComplete={register ? "new-password" : "current-password"} placeholder="At least 6 characters" value={password} onChange={(event) => setPassword(event.target.value)} minLength={6} required />
            </div>
            {error && <div role="alert" className="form-error"><AlertCircle size={14} />{error}</div>}
            <Button className="full-button auth-submit" disabled={busy}>
              {busy ? <><span className="button-spinner" />{register ? "Creating account…" : "Signing in…"}</> : <>{register ? "Create account" : "Sign in"}<ArrowRight size={14} /></>}
            </Button>
          </form>
          <div className="auth-switch">
            {register ? "Already have an account?" : "New to TrustGrade?"}{" "}
            <Link to={register ? "/login" : "/register"}>{register ? "Sign in" : "Create account"}</Link>
          </div>
        </Panel>
      </div>
    </main>
  );
}
