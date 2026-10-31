import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowUpRight, BookOpen, Check, CheckCircle2, ChevronLeft, ChevronRight,
  FileCheck2, FileText, GraduationCap, Menu, ShieldCheck, Sparkles, X,
} from "lucide-react";
import { isDemoMode } from "../../services/demo-session";

export function LandingPage() {
  const navigate = useNavigate();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [scrollIndex, setScrollIndex] = useState(0);
  const demoMode = isDemoMode();

  const handleGetStarted = () => {
    navigate("/demo");
  };

  const handleSignIn = () => {
    navigate("/demo");
  };

  const capabilities = [
    {
      id: "rubric",
      title: "Automated Rubric Grading",
      desc: "Evaluates multi-tier rubrics with criteria-specific evidence and customizable weight distributions.",
      icon: <FileCheck2 size={18} />,
      badge: "Spring Semester",
      image: "https://images.unsplash.com/photo-1434030216411-0b793f4b4173?auto=format&fit=crop&w=800&q=80",
    },
    {
      id: "syllabus",
      title: "Syllabus & Material Alignment",
      desc: "Verifies questions and student answers against your uploaded lecture notes, PPTs, and course readings.",
      icon: <BookOpen size={18} />,
      badge: "Core Feature",
      image: "https://images.unsplash.com/photo-1497633762265-9d179a990aa6?auto=format&fit=crop&w=800&q=80",
    },
    {
      id: "ocr",
      title: "Handwritten OCR & Diagrams",
      desc: "Extracts formulas, sketches, and handwritten tests from mobile camera photos or scanned PDF files.",
      icon: <FileText size={18} />,
      badge: "Multimodal AI",
      image: "https://images.unsplash.com/photo-1509062522246-3755977927d7?auto=format&fit=crop&w=800&q=80",
    },
    {
      id: "anti-hallucination",
      title: "Anti-Hallucination Guardrails",
      desc: "Zero fabricated justification. Every score is linked to verifiable quotes from course materials.",
      icon: <ShieldCheck size={18} />,
      badge: "100% Grounded",
      image: "https://images.unsplash.com/photo-1451187580459-43490279c0fa?auto=format&fit=crop&w=800&q=80",
    },
    {
      id: "confidence",
      title: "Confidence & Review Routing",
      desc: "Calculates multi-factor confidence and routes ambiguous or flagged papers for priority human review.",
      icon: <Sparkles size={18} />,
      badge: "Human in the Loop",
      image: "https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?auto=format&fit=crop&w=800&q=80",
    },
    {
      id: "feedback",
      title: "Actionable Student Feedback",
      desc: "Generates tailored feedback emphasizing strengths, correcting misconceptions, and guiding study.",
      icon: <GraduationCap size={18} />,
      badge: "Formative Insights",
      image: "https://images.unsplash.com/photo-1523240795612-9a054b0db644?auto=format&fit=crop&w=800&q=80",
    },
  ];

  return (
    <div className="tg-landing">
      {/* 1. FLOATING PILL NAVBAR */}
      <header className="tg-pill-nav">
        <div className="tg-nav-inner">
          <Link to="/" className="tg-nav-brand">
            <span className="tg-brand-symbol">
              <GraduationCap size={18} />
            </span>
            <span className="tg-brand-name">
              Trust<span>Grade</span>
            </span>
          </Link>

          <nav className="tg-nav-links">
            <a href="#about">About Us</a>
            <a href="#capabilities">Capabilities</a>
            <a href="#process">How It Works</a>
            <a href="#showcase">Platform</a>
            <a href="#faculty">For Faculty</a>
          </nav>

          <div className="tg-nav-actions">
            {demoMode && (
              <span
                className="demo-mode-pill"
                style={{ cursor: "pointer" }}
                onClick={() => navigate("/demo")}
                title="Hackathon Demo Active - Click to select role"
              >
                <span className="demo-pulse-dot" />
                DEMO MODE
              </span>
            )}
            <button className="tg-btn-ghost" onClick={handleSignIn}>
              Demo Access
            </button>
            <button className="tg-btn-primary" onClick={handleGetStarted}>
              <span>Enter Demo</span>
              <ArrowUpRight size={15} />
            </button>
            <button
              className="tg-mobile-toggle"
              aria-label="Toggle navigation"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            >
              {mobileMenuOpen ? <X size={20} /> : <Menu size={20} />}
            </button>
          </div>
        </div>

        {mobileMenuOpen && (
          <div className="tg-mobile-drawer">
            <a href="#about" onClick={() => setMobileMenuOpen(false)}>About Us</a>
            <a href="#capabilities" onClick={() => setMobileMenuOpen(false)}>Capabilities</a>
            <a href="#process" onClick={() => setMobileMenuOpen(false)}>How It Works</a>
            <a href="#showcase" onClick={() => setMobileMenuOpen(false)}>Platform</a>
            <a href="#faculty" onClick={() => setMobileMenuOpen(false)}>For Faculty</a>
            <div className="tg-mobile-buttons">
              <button className="tg-btn-ghost" onClick={handleSignIn}>
                Demo Access
              </button>
              <button className="tg-btn-primary" onClick={handleGetStarted}>
                <span>Enter Demo</span>
                <ArrowUpRight size={15} />
              </button>
            </div>
          </div>
        )}
      </header>

      {/* 2. CINEMATIC HERO SECTION */}
      <section className="tg-hero-wrapper">
        <div className="tg-hero-card">
          <div className="tg-hero-bg-overlay" />
          <div className="tg-hero-grid">
            {/* Left Column: Editorial Academic Content */}
            <div className="tg-hero-left">
              <div className="tg-hero-eyebrow">
                <span className="tg-lime-pip" />
                <span>ACADEMIC INTELLIGENCE PLATFORM</span>
              </div>

              <h1 className="tg-hero-title">
                Every answer<br />
                deserves a<br />
                <em className="tg-hero-serif-fair">fair evaluation<span className="tg-hero-dot">.</span></em>
              </h1>

              <p className="tg-hero-desc">
                Intelligent grading, syllabus-aware assessment and transparent feedback designed to empower educators and students.
              </p>

              <div className="tg-hero-actions">
                <button className="tg-hero-btn-primary" onClick={handleGetStarted}>
                  <span>{demoMode ? "Explore Demo Platform" : "Explore Platform"}</span>
                  <ArrowUpRight size={15} />
                </button>
                <button
                  className="tg-hero-btn-secondary"
                  onClick={() => navigate(demoMode ? "/demo" : "/login")}
                >
                  <span>{demoMode ? "Faculty Demo" : "For Educators"}</span>
                </button>
              </div>
            </div>

            {/* Right Column: Realistic Academic Grading Dashboard Preview + 2 Small Floating Cards */}
            <div className="tg-hero-right">
              <div className="tg-hero-board-wrap">
                {/* Floating Card 1: Rubric Evaluation */}
                <div className="tg-hero-float-chip tg-chip-top">
                  <div className="tg-chip-icon">
                    <FileCheck2 size={15} />
                  </div>
                  <div className="tg-chip-text">
                    <strong>Rubric Evaluation</strong>
                    <small>Concept-wise scoring</small>
                  </div>
                  <span className="tg-chip-tag">9.3 / 10</span>
                </div>

                {/* Realistic Academic Grading Dashboard Preview */}
                <div className="tg-hero-preview-board">
                  <div className="tg-board-header">
                    <div className="tg-board-title-group">
                      <span className="tg-board-badge">CS 302</span>
                      <div>
                        <strong>Algorithms & Data Structures</strong>
                        <small>Midterm Exam · Student: Julian Vance (ID: #2481)</small>
                      </div>
                    </div>
                    <span className="tg-board-status">
                      <span className="tg-status-dot" /> Faculty Sign-Off Ready
                    </span>
                  </div>

                  <div className="tg-board-section">
                    <div className="tg-section-label">STUDENT ANSWER SHEET EXTRACT · Q3</div>
                    <div className="tg-answer-preview">
                      <div className="tg-answer-q">Q3: Quicksort Worst-Case Degradation & Mitigations</div>
                      <p className="tg-answer-text">
                        "Quicksort exhibits O(n²) worst-case when partition pivots are unbalanced. Adopting a <mark>randomized pivot selection</mark> guarantees expected <mark>O(n log n)</mark> runtime by eliminating deterministic worst-case inputs."
                      </p>
                      <div className="tg-answer-citation">
                        <span>✓ Grounded in Lecture 6 & CLRS Sec 7.3</span>
                      </div>
                    </div>
                  </div>

                  <div className="tg-board-rubric-row">
                    <div className="tg-rubric-mini">
                      <div className="tg-rubric-head">
                        <span>Rubric Criteria</span>
                        <strong className="tg-rubric-total">9.3 / 10</strong>
                      </div>
                      <div className="tg-rubric-bars">
                        <div className="tg-rubric-item">
                          <div className="tg-rubric-info">
                            <span>Time Complexity Proof</span>
                            <div className="tg-rubric-bar">
                              <div className="tg-rubric-bar-fill" style={{ width: "96%" }} />
                            </div>
                          </div>
                          <strong>4.8 / 5.0</strong>
                        </div>
                        <div className="tg-rubric-item">
                          <div className="tg-rubric-info">
                            <span>Pivot Randomization</span>
                            <div className="tg-rubric-bar">
                              <div className="tg-rubric-bar-fill" style={{ width: "90%" }} />
                            </div>
                          </div>
                          <strong>4.5 / 5.0</strong>
                        </div>
                      </div>
                    </div>

                    <div className="tg-concept-mini">
                      <span className="tg-section-label">CONCEPT MASTERY</span>
                      <div className="tg-concept-stat">
                        <strong className="tg-concept-percent">94%</strong>
                        <span className="tg-concept-badge">Grade A</span>
                      </div>
                      <small>Syllabus Match: 100% Verified</small>
                    </div>
                  </div>

                  <div className="tg-board-footer">
                    <div className="tg-board-feedback">
                      <span className="tg-feedback-label">FACULTY REVIEW NOTE</span>
                      <p>"Rigorous recurrence derivation. Expected bound proof fully grounded."</p>
                    </div>
                    <div className="tg-confidence-badge">
                      <Sparkles size={12} />
                      <span>Confidence: <strong>98.4%</strong></span>
                    </div>
                  </div>
                </div>

                {/* Floating Card 2: Academic Integrity */}
                <div className="tg-hero-float-chip tg-chip-bottom">
                  <div className="tg-chip-icon">
                    <ShieldCheck size={15} />
                  </div>
                  <div className="tg-chip-text">
                    <strong>Academic Integrity</strong>
                    <small>Similarity & Trust Check</small>
                  </div>
                  <span className="tg-chip-verified">Verified</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 3. CAPABILITIES / TRUST PARTNER STRIP */}
      <section className="tg-trust-bar">
        <div className="tg-container">
          <div className="tg-partner-strip">
            <span className="tg-partner-item"><strong>STANFORD</strong> APPLIED AI</span>
            <span className="tg-partner-sep">•</span>
            <span className="tg-partner-item"><strong>OXFORD</strong> CURRICULUM</span>
            <span className="tg-partner-sep">•</span>
            <span className="tg-partner-item"><strong>CAMBRIDGE</strong> DIGITAL ED</span>
            <span className="tg-partner-sep">•</span>
            <span className="tg-partner-item"><strong>BERKELEY</strong> COMPUTING</span>
            <span className="tg-partner-sep">•</span>
            <span className="tg-partner-item"><strong>MIT</strong> INTEGRITY LAB</span>
          </div>
        </div>
      </section>

      {/* 4. ABOUT SECTION */}
      <section className="tg-about-section" id="about">
        <div className="tg-container">
          <div className="tg-about-grid">
            <div className="tg-about-image-card">
              <img
                src="https://images.unsplash.com/photo-1524178232363-1fb2b075b655?auto=format&fit=crop&w=900&q=80"
                alt="University classroom collaboration"
                className="tg-about-img"
                loading="lazy"
              />
              <div className="tg-about-img-overlay" />
              <div className="tg-about-img-badge">
                <span className="tg-badge-pulse" />
                <span>Active in 140+ Academic Courses</span>
              </div>
              <div className="tg-about-img-footer">
                <span>Verified Source Citations</span>
                <span className="tg-bullet">•</span>
                <span>100% Audit Trail</span>
              </div>
            </div>

            <div className="tg-about-content">
              <span className="tg-section-eyebrow">
                <span className="tg-eyebrow-dot" /> ABOUT TRUSTGRADE
              </span>
              <h2 className="tg-about-headline">
                Assessment should be more than assigning marks. It should <em>elevate learning</em>.
              </h2>
              <p className="tg-about-p">
                TrustGrade started with a clear observation: professors spend countless hours reading repetitive exams, leaving minimal energy for personalized guidance. Standard AI tools fail because they lack institutional course grounding and hallucinate criteria.
              </p>
              <p className="tg-about-p">
                We engineered TrustGrade to fuse custom course syllabi, lecture slides, and faculty-crafted rubrics into an evidence-driven evaluation engine. Every grade suggestion references specific passages—reducing grading fatigue by up to 70% while keeping teachers completely in control.
              </p>
              <div className="tg-about-actions">
                <button className="tg-btn-primary" onClick={() => navigate("/register")}>
                  <span>Explore Capabilities</span>
                  <ArrowUpRight size={15} />
                </button>
                <a href="#process" className="tg-btn-outline">
                  <span>How It Works</span>
                  <ArrowUpRight size={14} />
                </a>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 5. CAPABILITIES GRID */}
      <section className="tg-services-section" id="capabilities">
        <div className="tg-container">
          <div className="tg-services-header">
            <div>
              <span className="tg-section-eyebrow">
                <span className="tg-eyebrow-dot" /> OUR CAPABILITIES
              </span>
              <h2 className="tg-services-headline">
                Everything your <em>faculty needs</em>
              </h2>
            </div>
            <div className="tg-services-header-right">
              <p>
                From raw student PDF ingestion to final published marks—rigorous, evidence-backed evaluation at institutional scale.
              </p>
              <div className="tg-carousel-controls">
                <button
                  className="tg-ctrl-btn"
                  onClick={() => setScrollIndex(Math.max(0, scrollIndex - 1))}
                  aria-label="Previous"
                >
                  <ChevronLeft size={16} />
                </button>
                <button
                  className="tg-ctrl-btn"
                  onClick={() => setScrollIndex(Math.min(capabilities.length - 3, scrollIndex + 1))}
                  aria-label="Next"
                >
                  <ChevronRight size={16} />
                </button>
              </div>
            </div>
          </div>

          <div className="tg-cards-grid">
            {capabilities.map((item) => (
              <div key={item.id} className="tg-feature-card">
                <img src={item.image} alt={item.title} className="tg-card-bg-img" loading="lazy" />
                <div className="tg-card-overlay" />
                <div className="tg-card-top">
                  <span className="tg-card-badge">{item.badge}</span>
                  <span className="tg-card-icon">{item.icon}</span>
                </div>
                <div className="tg-card-body">
                  <h3 className="tg-card-title">{item.title}</h3>
                  <p className="tg-card-desc">{item.desc}</p>
                  <button className="tg-card-pill-btn" onClick={() => navigate("/register")}>
                    <span>Learn More</span>
                    <ArrowUpRight size={13} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 6. HOW IT WORKS */}
      <section className="tg-process-section" id="process">
        <div className="tg-container">
          <div className="tg-process-header">
            <div>
              <span className="tg-section-eyebrow">
                <span className="tg-eyebrow-dot" /> OUR WORKFLOW
              </span>
              <h2 className="tg-process-headline">
                How we evaluate, <em>start to finish</em>
              </h2>
            </div>
            <p className="tg-process-header-sub">
              A transparent, 4-step pipeline that combines high-precision syllabus retrieval with absolute teacher authority.
            </p>
          </div>

          <div className="tg-process-grid">
            <div className="tg-step-card tg-step-1">
              <span className="tg-step-num">Step 01</span>
              <h3 className="tg-step-title">Course & Rubric Ingestion</h3>
              <p className="tg-step-desc">
                Upload your syllabus, slide decks, and custom rubrics. The AI builds a dedicated course vector index with strict grounding boundaries.
              </p>
              <div className="tg-step-img-box">
                <img
                  src="https://images.unsplash.com/photo-1456513080510-7bf3a84b82f8?auto=format&fit=crop&w=600&q=80"
                  alt="Syllabus and lecture notes"
                  loading="lazy"
                />
                <div className="tg-step-img-tag">
                  <CheckCircle2 size={13} />
                  <span>Private Course Vector Store</span>
                </div>
              </div>
            </div>

            <div className="tg-step-card tg-step-2">
              <span className="tg-step-num">Step 02</span>
              <h3 className="tg-step-title">Intake Student Submissions</h3>
              <p className="tg-step-desc">
                Students upload typed PDFs or photos of handwritten answer sheets. OCR normalizes text, extracts mathematical notation, and segments questions.
              </p>
              <div className="tg-step-metric-chip">
                <div className="tg-chip-radar">
                  <span className="tg-radar-core" />
                </div>
                <div>
                  <strong>OCR Normalization Engine</strong>
                  <small>Typed PDFs & Handwritten Sheets</small>
                </div>
              </div>
            </div>

            <div className="tg-step-card tg-step-3">
              <span className="tg-step-num">Step 03</span>
              <h3 className="tg-step-title">Multi-Factor AI Evaluation</h3>
              <p className="tg-step-desc">
                Scores each criterion against the rubric, matches exact source quotes from lecture materials, and calculates a confidence score.
              </p>
              <div className="tg-step-confidence-badge">
                <div className="tg-conf-val">98.4%</div>
                <div>
                  <strong>Confidence Index</strong>
                  <small>High Accuracy · Grounded</small>
                </div>
              </div>
            </div>

            <div className="tg-step-card tg-step-4-wide">
              <div className="tg-step-4-content">
                <span className="tg-step-num">Step 04 · Faculty Review</span>
                <h3 className="tg-step-title">Teacher Approval & Publication</h3>
                <p className="tg-step-desc">
                  Every evaluation is provisional until reviewed by the professor. Verify marks with single clicks, adjust rubric scores, and publish constructive feedback directly to student dashboards.
                </p>
                <div className="tg-step-4-badges">
                  <span className="tg-badge-tag"><Check size={12} /> 100% Teacher Authority</span>
                  <span className="tg-badge-tag"><Check size={12} /> One-Click Grade Approval</span>
                  <span className="tg-badge-tag"><Check size={12} /> Anti-Hallucination Verified</span>
                </div>
              </div>
              <div className="tg-step-4-graphic">
                <div className="tg-verification-card">
                  <div className="tg-verif-top">
                    <span className="tg-stamp-mark"><CheckCircle2 size={16} /></span>
                    <div>
                      <strong>Evaluation Verified</strong>
                      <small>Prof. Alex Morgan · CS 301</small>
                    </div>
                  </div>
                  <div className="tg-verif-criteria">
                    <div><span>Theoretical Bounds</span><strong>5.0 / 5.0</strong></div>
                    <div><span>Empirical Analysis</span><strong>4.8 / 5.0</strong></div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 7. AI INTELLIGENCE SHOWCASE */}
      <section className="tg-showcase-section" id="showcase">
        <div className="tg-container">
          <div className="tg-showcase-header">
            <span className="tg-section-eyebrow">
              <span className="tg-eyebrow-dot" /> LIVE PLATFORM INSPECTION
            </span>
            <h2 className="tg-showcase-headline">
              Academic rigor in <em>every single detail</em>
            </h2>
            <p className="tg-showcase-sub">
              Inspect how TrustGrade anchors criteria evaluation in verified lecture citations and provides full faculty oversight before publishing.
            </p>
          </div>

          <div className="tg-showcase-container">
            <div className="tg-showcase-topbar">
              <div className="tg-window-dots">
                <span className="tg-dot" />
                <span className="tg-dot" />
                <span className="tg-dot" />
              </div>
              <div className="tg-window-title">
                <span>CS 401: Advanced Algorithms — Midterm Assessment</span>
                <span className="tg-status-pill">Ready for Faculty Approval</span>
              </div>
              <div className="tg-window-user">
                <span className="tg-user-avatar">DR</span>
                <span>Dr. David Rossi</span>
              </div>
            </div>

            <div className="tg-showcase-body">
              <div className="tg-showcase-left">
                <div className="tg-pane-header">
                  <span className="tg-pane-tag">STUDENT SUBMISSION</span>
                  <span className="tg-submission-id">ID: #4092 · Julian Vance</span>
                </div>
                <div className="tg-student-snippet">
                  <h4>Question 2: Quicksort Worst-Case Degradation & Mitigation</h4>
                  <div className="tg-snippet-box">
                    <p>
                      "In worst-case scenarios, Quicksort degrades to <mark className="tg-highlight">O(n²)</mark> when the chosen pivot is consistently the minimum or maximum element in an already sorted or reverse-sorted array. This yields maximally unbalanced partitions containing 0 and n-1 elements respectively."
                    </p>
                    <p>
                      "To mitigate this degradation, we can adopt a <mark className="tg-highlight">randomized pivot selection strategy</mark> or the Median-of-Three heuristic. Randomization guarantees an expected runtime of O(n log n) regardless of the input distribution, effectively eliminating adversarial permutations."
                    </p>
                  </div>
                </div>

                <div className="tg-citation-box">
                  <div className="tg-citation-head">
                    <BookOpen size={13} />
                    <span>Retrieved Course Evidence</span>
                  </div>
                  <p>
                    <strong>Lecture 6, Slide 18:</strong> "Quicksort worst-case recurrence T(n) = T(n-1) + O(n) resolves to O(n²). Mitigated via randomized pivot choosing with uniform probability over [p..r]."
                  </p>
                  <span className="tg-citation-match">● 98.7% Semantic Material Match</span>
                </div>
              </div>

              <div className="tg-showcase-right">
                <div className="tg-pane-header">
                  <span className="tg-pane-tag">AI CRITERIA BREAKDOWN</span>
                  <span className="tg-score-tag">Score: 9.8 / 10.0</span>
                </div>

                <div className="tg-rubric-cards">
                  <div className="tg-criterion-card">
                    <div className="tg-crit-top">
                      <strong>1. Worst-Case Recurrence Analysis</strong>
                      <span className="tg-crit-score">5.0 / 5.0</span>
                    </div>
                    <p>Correctly identified O(n²) degradation and unbalanced partition depth.</p>
                    <small>Evidence Grounded: Lecture 6 (Slide 18)</small>
                  </div>

                  <div className="tg-criterion-card">
                    <div className="tg-crit-top">
                      <strong>2. Randomized Pivot Mitigation</strong>
                      <span className="tg-crit-score">4.8 / 5.0</span>
                    </div>
                    <p>Accurately explained randomized selection and expected O(n log n) proof.</p>
                    <small>Evidence Grounded: CLRS Textbook, Chapter 7</small>
                  </div>
                </div>

                <div className="tg-confidence-panel">
                  <div className="tg-conf-row">
                    <div>
                      <small>EVALUATION CONFIDENCE</small>
                      <strong>99.2% — High Confidence</strong>
                    </div>
                    <span className="tg-conf-tag">Audit Clean</span>
                  </div>
                  <div className="tg-conf-meter">
                    <div className="tg-conf-fill" style={{ width: "99.2%" }} />
                  </div>
                </div>

                <div className="tg-approval-actions">
                  <button className="tg-btn-approve" onClick={() => navigate("/login")}>
                    <CheckCircle2 size={16} />
                    <span>Approve Grade & Publish</span>
                  </button>
                  <button className="tg-btn-adjust" onClick={() => navigate("/login")}>
                    Adjust Score
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 8. FINAL CALL TO ACTION BANNER */}
      <section className="tg-cta-section" id="faculty">
        <div className="tg-container">
          <div className="tg-cta-banner">
            <div className="tg-cta-glow" />
            <div className="tg-cta-content">
              <span className="tg-section-eyebrow">
                <span className="tg-eyebrow-dot" /> ELEVATE YOUR INSTITUTION
              </span>
              <h2 className="tg-cta-headline">
                Make every evaluation <em>meaningful</em>.
              </h2>
              <p className="tg-cta-sub">
                Join forward-thinking faculty and university departments using TrustGrade to streamline grading while delivering transparent, evidence-based feedback.
              </p>
              <div className="tg-cta-buttons">
                <button className="tg-btn-primary-lg" onClick={handleGetStarted}>
                  <span>{demoMode ? "Enter Hackathon Demo" : "Get Started for Free"}</span>
                  <ArrowUpRight size={16} />
                </button>
                <button
                  className="tg-btn-glass-lg"
                  onClick={() => navigate(demoMode ? "/demo" : "/login")}
                >
                  <span>{demoMode ? "Role Selection" : "Schedule Faculty Demo"}</span>
                  <ArrowUpRight size={16} />
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 9. FOOTER */}
      <footer className="tg-footer">
        <div className="tg-container">
          <div className="tg-footer-grid">
            <div className="tg-footer-col tg-footer-brand-col">
              <Link to="/" className="tg-nav-brand">
                <span className="tg-brand-symbol">
                  <GraduationCap size={18} />
                </span>
                <span className="tg-brand-name">
                  Trust<span>Grade</span>
                </span>
              </Link>
              <p className="tg-footer-tagline">
                The intelligent academic assessment platform grounded in course materials, rigorous rubrics, and faculty authority.
              </p>
              <div className="tg-footer-badges">
                <span className="tg-security-pill">FERPA Compliant</span>
                <span className="tg-security-pill">SOC2 Ready</span>
              </div>
            </div>

            <div className="tg-footer-col">
              <strong className="tg-col-title">Platform</strong>
              <ul className="tg-footer-links">
                <li><a href="#capabilities">Automated Rubric Grading</a></li>
                <li><a href="#capabilities">Syllabus Alignment Engine</a></li>
                <li><a href="#capabilities">Handwritten OCR Processing</a></li>
                <li><a href="#capabilities">Anti-Hallucination Guard</a></li>
                <li><a href="#capabilities">Confidence & Review Routing</a></li>
              </ul>
            </div>

            <div className="tg-footer-col">
              <strong className="tg-col-title">Resources</strong>
              <ul className="tg-footer-links">
                <li><a href="#about">Academic Documentation</a></li>
                <li><a href="#about">Pedagogical Research</a></li>
                <li><a href="#showcase">Case Studies</a></li>
                <li><a href="#showcase">Security Architecture</a></li>
                <li><a href="#showcase">Faculty Guidelines</a></li>
              </ul>
            </div>

            <div className="tg-footer-col">
              <strong className="tg-col-title">Faculty Support</strong>
              <ul className="tg-footer-links">
                <li><span>Institutional Inquiries</span></li>
                <li><strong className="tg-support-phone">+1 (800) 459-7812</strong></li>
                <li><span>support@trustgrade.edu</span></li>
                <li><span>Available Mon - Fri, 8am - 6pm EST</span></li>
              </ul>
            </div>
          </div>

          <div className="tg-footer-bottom">
            <span>© 2026 TrustGrade AI Inc. All rights reserved.</span>
            <div className="tg-bottom-links">
              <a href="#">Privacy Policy</a>
              <a href="#">Terms of Service</a>
              <a href="#">Academic Integrity Pledge</a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
