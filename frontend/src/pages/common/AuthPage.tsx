import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { GraduationCap } from "lucide-react";
import { signIn, signUp } from "../../services/auth";
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
      if (register) {
        await signUp(email, password);
        await signIn(email, password);
        await refreshSession();
      } else {
        await signIn(email, password);
        await refreshSession();
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
      <Link to="/" className="tg-nav-brand auth-brand"><span className="tg-brand-symbol"><GraduationCap size={18} /></span><span className="tg-brand-name">Trust<span>Grade</span></span></Link>
      <form className="auth-card" onSubmit={submit}>
        <h1>{register ? "Create your account" : "Sign in to TrustGrade"}</h1>
        <p>{register ? "Register for a faculty or student account." : "Use the account credentials provided by your institution."}</p>
        {error && <div className="auth-error" role="alert">{error}</div>}
        <label>Email address<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></label>
        <label>Password<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} minLength={6} required /></label>
        <button className="tg-btn-primary auth-submit" disabled={busy}>{busy ? "Please wait…" : register ? "Create account" : "Sign in"}</button>
        <Link className="auth-switch" to={register ? "/login" : "/register"}>{register ? "Already have an account? Sign in" : "Need an account? Create one"}</Link>
      </form>
    </main>
  );
}
