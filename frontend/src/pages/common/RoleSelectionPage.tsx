import { Link, useNavigate } from "react-router-dom";
import { ArrowLeft, ArrowRight, BookOpen, Check, GraduationCap, ShieldCheck, Sparkles } from "lucide-react";
import { setDemoSession } from "../../services/demo-session";
import { useAppState } from "../../App";

export function RoleSelectionPage() {
  const navigate = useNavigate();
  const { setUser } = useAppState();

  const handleSelectRole = (role: "teacher" | "student") => {
    const demoUser = setDemoSession(role);
    setUser(demoUser);
    navigate("/app");
  };

  return (
    <div className="demo-select-page">
      {/* Top Header */}
      <header className="demo-select-header">
        <Link to="/" className="tg-nav-brand">
          <span className="tg-brand-symbol">
            <GraduationCap size={18} />
          </span>
          <span className="tg-brand-name">
            Trust<span>Grade</span>
          </span>
        </Link>
        <Link to="/" className="demo-back-link">
          <ArrowLeft size={14} />
          <span>Back to Landing Page</span>
        </Link>
      </header>

      {/* Main Content Area */}
      <main className="demo-select-container">
        <div className="demo-select-intro">
          <span className="demo-pill-badge">
            <Sparkles size={13} />
            HACKATHON DEMO ACCESS
          </span>
          <h1 className="demo-select-title">
            Experience TrustGrade from <em>both perspectives</em>.
          </h1>
          <p className="demo-select-subtitle">
            Choose an interactive persona to explore the complete platform with pre-loaded coursework, submissions, and OCR evaluation—no credentials required.
          </p>
        </div>

        {/* 2-Column Persona Cards */}
        <div className="demo-cards-grid">
          {/* FACULTY CARD */}
          <div className="demo-persona-card faculty-card">
            <div className="demo-card-tag">FACULTY WORKSPACE</div>
            <div className="demo-persona-header">
              <div className="demo-avatar-icon">
                <GraduationCap size={26} />
              </div>
              <div>
                <h2>Faculty Demo</h2>
                <span className="demo-email-chip">faculty.demo@trustgrade.local</span>
              </div>
            </div>

            <p className="demo-persona-desc">
              Experience the comprehensive instructor workflow: design assignments, supervise course enrollments, inspect OCR student submissions, and approve transparent rubric grades.
            </p>

            <ul className="demo-features-list">
              <li>
                <span className="demo-check-circle"><Check size={13} /></span>
                <span><strong>Teacher Dashboard:</strong> Classroom metrics & assignment velocity</span>
              </li>
              <li>
                <span className="demo-check-circle"><Check size={13} /></span>
                <span><strong>Course & Assignment Editor:</strong> Create questions & rubrics</span>
              </li>
              <li>
                <span className="demo-check-circle"><Check size={13} /></span>
                <span><strong>Multimodal OCR Queue:</strong> Inspect student handwriting recognition</span>
              </li>
              <li>
                <span className="demo-check-circle"><Check size={13} /></span>
                <span><strong>Evaluation Center:</strong> Review, adjust, and approve grades</span>
              </li>
            </ul>

            <button
              className="demo-btn-enter faculty-btn"
              onClick={() => handleSelectRole("teacher")}
            >
              <span>Enter Faculty Demo</span>
              <ArrowRight size={16} />
            </button>
          </div>

          {/* STUDENT CARD */}
          <div className="demo-persona-card student-card">
            <div className="demo-card-tag student-tag">STUDENT WORKSPACE</div>
            <div className="demo-persona-header">
              <div className="demo-avatar-icon student-avatar">
                <BookOpen size={24} />
              </div>
              <div>
                <h2>Student Demo</h2>
                <span className="demo-email-chip">student.demo@trustgrade.local</span>
              </div>
            </div>

            <p className="demo-persona-desc">
              Experience the modern student portal: track upcoming deadlines, upload answer sheet PDFs with live OCR feedback, and review verified instructor evaluations.
            </p>

            <ul className="demo-features-list">
              <li>
                <span className="demo-check-circle"><Check size={13} /></span>
                <span><strong>Student Dashboard:</strong> Coursework progress orb & deadlines</span>
              </li>
              <li>
                <span className="demo-check-circle"><Check size={13} /></span>
                <span><strong>My Courses:</strong> View enrolled courses and class syllabi</span>
              </li>
              <li>
                <span className="demo-check-circle"><Check size={13} /></span>
                <span><strong>Submit Assignment:</strong> Drag-and-drop PDF with submission receipt</span>
              </li>
              <li>
                <span className="demo-check-circle"><Check size={13} /></span>
                <span><strong>Results & Feedback:</strong> Verified teacher-approved scores</span>
              </li>
            </ul>

            <button
              className="demo-btn-enter student-btn"
              onClick={() => handleSelectRole("student")}
            >
              <span>Enter Student Demo</span>
              <ArrowRight size={16} />
            </button>
          </div>
        </div>

        {/* Footer info */}
        <div className="demo-select-footer">
          <div className="demo-footer-info">
            <ShieldCheck size={16} />
            <span>Demo sessions run in isolated memory and can be switched or exited at any time.</span>
          </div>
          <div className="demo-footer-login-link">
            <span>Need real account authentication?</span>
            <Link to="/login">Sign in with Supabase</Link>
          </div>
        </div>
      </main>
    </div>
  );
}
