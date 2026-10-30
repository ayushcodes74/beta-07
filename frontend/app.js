(() => {
  const iconPaths = {
    check: '<path d="m5 12 4 4L19 6"/>',
    overview: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/>',
    courses: '<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21z"/><path d="M4 5.5V21M8 7h8M8 11h7"/>',
    assignments: '<path d="M8 4h11a2 2 0 0 1 2 2v14H8a3 3 0 0 1-3-3V7a3 3 0 0 1 3-3Z"/><path d="M8 4v13M11 9h6M11 13h5"/>',
    submissions: '<path d="M12 16V4m0 0L7 9m5-5 5 5"/><path d="M5 14v5a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-5"/>',
    grading: '<path d="M12 3 4.5 6v5c0 5 3.2 8.2 7.5 10 4.3-1.8 7.5-5 7.5-10V6z"/><path d="m8.5 12 2.2 2.2 4.8-5"/>',
    materials: '<path d="M4 7.5A2.5 2.5 0 0 1 6.5 5H10l2 2h5.5A2.5 2.5 0 0 1 20 9.5v8a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 17.5z"/><path d="M8 12h8M8 15h6"/>',
    ocr: '<path d="M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3"/><path d="M7 10h10M7 14h7"/>',
    results: '<path d="M4 19V5m0 14h17"/><path d="m7 15 4-4 3 2 6-7"/>',
    leaderboard: '<path d="M8 21h8m-4-4v4"/><path d="M6 4h12v5a6 6 0 0 1-12 0z"/><path d="M6 7H3v2a4 4 0 0 0 4 4m11-6h3v2a4 4 0 0 1-4 4"/>',
    settings: '<path d="M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7Z"/><path d="m19.4 15 .1.1a1.8 1.8 0 0 1-2.5 2.5l-.1-.1a1.8 1.8 0 0 0-3 .9v.2a1.8 1.8 0 0 1-3.6 0v-.2a1.8 1.8 0 0 0-3-.9l-.1.1a1.8 1.8 0 0 1-2.5-2.5l.1-.1a1.8 1.8 0 0 0-.9-3h-.2a1.8 1.8 0 0 1 0-3.6h.2a1.8 1.8 0 0 0 .9-3l-.1-.1a1.8 1.8 0 0 1 2.5-2.5l.1.1a1.8 1.8 0 0 0 3-.9v-.2a1.8 1.8 0 0 1 3.6 0v.2a1.8 1.8 0 0 0 3 .9l.1-.1a1.8 1.8 0 0 1 2.5 2.5l-.1.1a1.8 1.8 0 0 0 .9 3h.2a1.8 1.8 0 0 1 0 3.6h-.2a1.8 1.8 0 0 0-.9 3Z"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
    bell: '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"/><path d="M10 21h4"/>',
    chevron: '<path d="m9 18 6-6-6-6"/>',
    down: '<path d="m7 10 5 5 5-5"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    arrow: '<path d="M5 12h14m-7-7 7 7-7 7"/>',
    calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 11h18"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    users: '<path d="M16 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="10" cy="7" r="4"/><path d="M20 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8"/>',
    sparkles: '<path d="m12 3 1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="m19 14 .9 2.1L22 17l-2.1.9L19 20l-.9-2.1L16 17l2.1-.9z"/>',
    more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
    file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h8"/>',
    upload: '<path d="M12 16V4m0 0L7 9m5-5 5 5"/><path d="M4 20h16"/>',
    edit: '<path d="m15 5 4 4M4 20l4-.8L19 8a2.8 2.8 0 0 0-4-4L4 15z"/>',
    trash: '<path d="M3 6h18M8 6V4h8v2m3 0-1 14H6L5 6m4 4v6m6-6v6"/>',
    eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
    close: '<path d="m18 6-12 12M6 6l12 12"/>',
    checkCircle: '<circle cx="12" cy="12" r="9"/><path d="m8 12 2.5 2.5L16 9"/>',
    alert: '<path d="m10.3 3.9-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.7-3.1l-8-14a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4m0 4h.01"/>',
    download: '<path d="M12 3v12m0 0 5-5m-5 5-5-5"/><path d="M4 17v4h16v-4"/>',
    filter: '<path d="M4 7h16M7 12h10m-7 5h4"/>',
    dots: '<circle cx="12" cy="5" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="12" cy="19" r="1"/>',
    refresh: '<path d="M20 7v5h-5"/><path d="M4 17v-5h5"/><path d="M5.6 9a7 7 0 0 1 11.6-2L20 12M4 12l2.8 5a7 7 0 0 0 11.6-2"/>',
    award: '<circle cx="12" cy="8" r="6"/><path d="m8.2 13-1 8 4.8-2.5 4.8 2.5-1-8"/>',
    send: '<path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/>',
    book: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2Z"/>',
  };
  const icon = (name, size = 17) => `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${iconPaths[name] || iconPaths.file}</svg>`;
  const initials = (name) => name.split(" ").map((part) => part[0]).slice(0, 2).join("");
  const students = [
    { name: "Maya Chen", initials: "MC", avatar: "" },
    { name: "Ethan Brooks", initials: "EB", avatar: "a2" },
    { name: "Sofia Patel", initials: "SP", avatar: "a3" },
    { name: "Noah Williams", initials: "NW", avatar: "a4" },
    { name: "Amara Okafor", initials: "AO", avatar: "a5" },
    { name: "Leo Fischer", initials: "LF", avatar: "a3" },
  ];
  const courses = [
    ["Data Structures", "CS 204", "Dr. Alex Morgan", 42, 6, 74],
    ["Operating Systems", "CS 301", "Dr. Alex Morgan", 38, 5, 62],
    ["Database Systems", "CS 220", "Dr. Alex Morgan", 46, 7, 86],
    ["Computer Networks", "CS 315", "Dr. Alex Morgan", 31, 4, 54],
    ["Software Engineering", "CS 410", "Dr. Alex Morgan", 29, 3, 68],
    ["Discrete Mathematics", "MATH 210", "Dr. Alex Morgan", 32, 4, 79],
    ["Intro to Algorithms", "CS 220A", "Dr. Alex Morgan", 18, 3, 51],
    ["Human-Computer Interaction", "CS 340", "Dr. Alex Morgan", 12, 2, 44],
  ];
  const submissions = [
    { student: "Maya Chen", assignment: "Data Structures — Assignment 03", submitted: "Today, 9:42 AM", ocr: "Verified", grade: "18 / 20", status: "Reviewed" },
    { student: "Ethan Brooks", assignment: "Data Structures — Assignment 03", submitted: "Today, 9:18 AM", ocr: "Verified", grade: "—", status: "Pending" },
    { student: "Sofia Patel", assignment: "Operating Systems — Assignment 02", submitted: "Yesterday, 11:51 PM", ocr: "Needs review", grade: "—", status: "Late" },
    { student: "Noah Williams", assignment: "Database Systems — Project 01", submitted: "Yesterday, 4:27 PM", ocr: "Verified", grade: "—", status: "Pending" },
    { student: "Amara Okafor", assignment: "Data Structures — Assignment 03", submitted: "Yesterday, 2:10 PM", ocr: "Verified", grade: "16 / 20", status: "Published" },
    { student: "Leo Fischer", assignment: "Computer Networks — Quiz 04", submitted: "Oct 26, 10:34 AM", ocr: "Processing", grade: "—", status: "Needs OCR Review" },
    { student: "Maya Chen", assignment: "Database Systems — Project 01", submitted: "Oct 25, 3:12 PM", ocr: "Verified", grade: "19 / 20", status: "Published" },
  ];
  const materials = [
    { name: "CS204_Course_Syllabus_2026.pdf", type: "Syllabus", size: "1.8 MB", date: "Oct 18, 2026", status: "Ready", index: "Ready" },
    { name: "Assignment_03_Grading_Rubric.pdf", type: "Rubric", size: "624 KB", date: "Oct 24, 2026", status: "Ready", index: "Ready" },
    { name: "Week_07_Trees_and_Graphs.pptx", type: "Lecture slides", size: "4.2 MB", date: "Oct 22, 2026", status: "Processing", index: "Processing" },
    { name: "Reference_Notes_Binary_Trees.pdf", type: "Notes", size: "982 KB", date: "Oct 19, 2026", status: "Needs Review", index: "Needs Review" },
    { name: "Course_Rulebook.pdf", type: "Rulebook", size: "746 KB", date: "Oct 16, 2026", status: "Ready", index: "Ready" },
  ];
  let state = {
    page: "Overview",
    role: "teacher",
    submissions: [...submissions],
    materials: [...materials],
    filter: "All",
    courseQuery: "",
    search: "",
    questions: [
      { title: "Explain how a balanced binary search tree maintains O(log n) operations.", type: "Subjective", marks: 10, answer: "A balanced tree keeps height proportional to log n by..." },
      { title: "Which traversal visits nodes in ascending order in a BST?", type: "MCQ", marks: 5, answer: "In-order traversal" },
    ],
    difficulty: "Mixed",
    notificationsOpen: false,
  };

  const app = document.getElementById("app");
  const nav = [
    { group: "Workspace", items: [["Overview", "overview"], ["Courses", "courses"], ["Assignments", "assignments"], ["Submissions", "submissions", "18"], ["AI Grading", "grading"]] },
    { group: "Resources", items: [["Course Materials", "materials"], ["OCR Review", "ocr", "3"], ["Results", "results"], ["Leaderboard", "leaderboard"]] },
  ];
  const statusClass = (status) => {
    const map = { Reviewed: "reviewed", Published: "published", Pending: "pending", Late: "late", "Needs OCR Review": "needs", Verified: "ready", Processing: "processing", Ready: "ready", "Needs Review": "needs", Failed: "failed", Draft: "draft" };
    return map[status] || "pending";
  };
  const avatar = (name, extra = "") => {
    const person = students.find((item) => item.name === name);
    return `<span class="avatar ${person?.avatar || extra}" aria-label="${name}">${person?.initials || initials(name)}</span>`;
  };
  const badge = (text) => `<span class="status status-${statusClass(text)}">${text}</span>`;
  const rowAction = (label, action, ico = "chevron") => `<button class="row-action" data-action="${action}">${label}${icon(ico, 13)}</button>`;
  const getVisibleSubmissions = () => {
    const query = state.search.toLowerCase();
    return state.submissions.filter((item) => {
      const matchesSearch = !query || `${item.student} ${item.assignment} ${item.status}`.toLowerCase().includes(query);
      if (!matchesSearch) return false;
      if (state.filter === "All") return true;
      if (state.filter === "Needs OCR Review") return item.ocr === "Needs review" || item.status === "Needs OCR Review";
      if (state.filter === "Reviewed") return ["Reviewed", "Published"].includes(item.status);
      if (state.filter === "Published") return item.status === "Published";
      return item.status === state.filter;
    });
  };

  function renderShell() {
    const groups = nav.map((section) => `<div class="nav-group"><div class="nav-label">${section.group}</div>${section.items.map(([label, ico, count]) => `<button class="nav-link ${state.page === label ? "active" : ""}" data-page="${label}" aria-label="${label}" title="${label}">${icon(ico)}<span>${label}</span>${count ? `<span class="nav-count">${count}</span>` : ""}</button>`).join("")}</div>`).join("");
    const pageTitle = state.page === "Overview" && state.role === "student" ? "My classroom" : state.page;
    app.innerHTML = `<div class="app-shell">
      <aside class="sidebar" aria-label="Main navigation">
        <a class="brand" href="#" data-page="Overview" aria-label="TrustGrade home"><span class="brand-mark">${icon("check", 19)}</span><span class="brand-name">Trust<span>Grade</span></span></a>
        <button class="workspace-switch" data-action="switch-role" aria-label="Switch workspace role"><span class="workspace-icon">${icon("book", 15)}</span><span class="workspace-meta"><strong>${state.role === "teacher" ? "Faculty workspace" : "Student workspace"}</strong><small>${state.role === "teacher" ? "Spring term · 2026" : "Spring term · CS 204"}</small></span>${icon("down", 13)}</button>
        <nav>${groups}</nav>
        <div class="sidebar-bottom"><div class="nav-group"><div class="nav-label">Account</div><button class="nav-link ${state.page === "Settings" ? "active" : ""}" data-page="Settings" aria-label="Settings" title="Settings">${icon("settings")}<span>Settings</span></button></div>
          <div class="sidebar-footer">${avatar("Alex Morgan", "photo")}<span class="profile-meta"><strong>Alex Morgan</strong><small>${state.role === "teacher" ? "Instructor" : "Student preview"}</small></span><button class="icon-button" data-action="profile-menu" aria-label="Profile menu">${icon("more")}</button></div>
        </div>
      </aside>
      <main class="main-shell">
        <header class="topbar"><div class="breadcrumbs"><button class="icon-button mobile-menu" data-action="menu" aria-label="Menu">${icon("overview")}</button><span>TrustGrade</span><span class="crumb-sep">/</span><span class="crumb-current">${pageTitle}</span></div>
          <div class="topbar-actions"><label class="search-box">${icon("search")}<input id="global-search" type="search" placeholder="Search anything..." aria-label="Search"><span class="search-shortcut">⌘ K</span></label><span class="topbar-divider"></span>
            <div class="notification-wrap"><button class="icon-button" data-action="notifications" aria-label="Notifications">${icon("bell")}<span class="notification-dot"></span></button>${state.notificationsOpen ? `<div class="popover"><h3>Notifications</h3><div class="notification-item"><strong>3 submissions need OCR review</strong>Check handwritten pages before grading.</div><div class="notification-item"><strong>Assignment due tomorrow</strong>Operating Systems — Assignment 02.</div></div>` : ""}</div>
            <button class="icon-button" data-action="profile-menu" aria-label="Open profile">${avatar("Alex Morgan", "photo")}</button>
          </div>
        </header>
        <section class="page-content" id="page-content">${renderPage()}</section>
      </main>
    </div>`;
  }

  function heading(title, subtitle, action = "") {
    return `<div class="page-heading"><div><div class="eyebrow">TrustGrade workspace</div><h1>${title}</h1><p class="page-subtitle">${subtitle}</p></div><div class="heading-actions">${action}</div></div>`;
  }
  function button(label, action, kind = "primary", ico = "") {
    return `<button class="button button-${kind}" data-action="${action}">${ico ? icon(ico) : ""}${label}</button>`;
  }
  function sectionHeader(title, subtitle, link = "") {
    return `<div class="section-heading"><div><h2>${title}</h2>${subtitle ? `<p>${subtitle}</p>` : ""}</div>${link ? `<button class="text-link" data-page="${link}">View all ${icon("arrow", 13)}</button>` : ""}</div>`;
  }
  function sparkline(points) {
    const coords = points.map((point, index) => `${index * 12},${26 - point}`).join(" ");
    return `<svg class="stat-spark" viewBox="0 0 84 30" aria-hidden="true"><polyline points="${coords}" fill="none" stroke="#82927d" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
  }
  function statCard(label, value, note, change, ico, featured = false, alert = false) {
    return `<article class="card stat-card ${featured ? "stat-feature" : ""} ${alert ? "stat-alert" : ""}"><div class="stat-top"><span>${label}</span><span class="stat-icon">${icon(ico, 16)}</span></div><div class="stat-value-row"><strong class="stat-value">${value}</strong><span class="stat-change">${change}</span></div><div class="stat-foot">${note}</div>${sparkline([4,8,7,12,10,16,13])}</article>`;
  }
  function recentTable(items = state.submissions.slice(0, 4), includeAction = true) {
    return `<div class="table-wrap"><table class="data-table"><thead><tr><th>Student</th><th>Assignment</th><th>Submitted</th><th>OCR</th><th>AI grade</th><th>Status</th>${includeAction ? "<th></th>" : ""}</tr></thead><tbody>${items.map((item) => `<tr><td><span class="student-cell">${avatar(item.student)}${item.student}</span></td><td>${item.assignment}</td><td>${item.submitted}</td><td>${badge(item.ocr === "Needs review" ? "Needs Review" : item.ocr)}</td><td class="${item.grade !== "—" ? "grade" : ""}">${item.grade}</td><td>${badge(item.status)}</td>${includeAction ? `<td>${rowAction("Review", "open-review")}</td>` : ""}</tr>`).join("")}</tbody></table></div>`;
  }
  function dashboard() {
    if (state.role === "student") return studentDashboard();
    return `<div class="welcome-row"><div><div class="eyebrow">Saturday, October 31, 2026</div><h1>Good morning, Alex.</h1><p class="page-subtitle">Your classroom, intelligently organized.</p><div class="welcome-context" style="margin-top:9px"><span>12 assignments</span><span class="context-dot"></span><span>248 students</span><span class="context-dot"></span><span>18 pending reviews</span></div></div><div class="heading-actions">${button("Create Assignment", "create-assignment", "primary", "plus")}</div></div>
      <div class="stat-grid">${statCard("Active courses", "8", "Across 3 departments", "+2 this term", "courses", true)}${statCard("Students", "248", "Across all courses", "+12 this month", "users")}${statCard("Pending reviews", "18", "6 need your attention", "3 due today", "clock", false, true)}${statCard("Published assignments", "24", "Feedback shared", "+4 this month", "checkCircle")}</div>
      <div class="dashboard-grid"><article class="card grading-feature"><div class="feature-top"><div class="feature-title"><span class="feature-symbol">${icon("sparkles")}</span><div><h2>AI Grading Activity</h2><p>A little help with the heavy lifting.</p></div></div><span class="live-pill"><i class="live-dot"></i>In progress</span></div>
        <div class="feature-assignment">Data Structures — Assignment 03</div><div class="feature-course">CS 204 <span style="padding:0 5px;color:#c1c1b9">·</span> Due Oct 31, 11:59 PM</div>
        <div class="progress-row"><span><strong>72 / 96</strong> submissions reviewed</span><span>75%</span></div><div class="progress-track"><div class="progress-fill" style="width:75%"></div></div>
        <div class="feature-bottom"><div class="avatar-stack">${students.slice(0,4).map((person) => avatar(person.name)).join("")}<span class="avatar-more">+68</span></div><div class="feature-meta"><span>${icon("checkCircle", 13)} Avg. confidence 91%</span><span>${icon("clock", 13)} 24 awaiting review</span></div></div>
        <div class="feature-actions">${button("Continue review", "open-review", "secondary", "arrow")}</div>
      </article>
      <div class="side-stack"><article class="card mini-card"><h3>Class performance</h3><div class="mini-number">84.6<span style="font:500 11px var(--font);color:#90918a"> / 100</span></div><div class="mini-caption">Average across active courses</div><svg class="mini-ring" viewBox="0 0 50 50" aria-label="84 percent class average"><circle cx="25" cy="25" r="20" fill="none" stroke="#e9ece5" stroke-width="4"/><circle cx="25" cy="25" r="20" fill="none" stroke="#82927d" stroke-width="4" stroke-linecap="round" stroke-dasharray="105 126" transform="rotate(-90 25 25)"/><text x="25" y="28">84%</text></svg></article>
      <article class="card mini-card"><h3>Students to check in with</h3><div class="mini-number">6</div><div class="mini-caption">May benefit from a little support</div><div class="mini-avatars">${students.slice(0,4).map((person) => avatar(person.name)).join("")}<span class="avatar-more">+2</span></div></article></div></div>
      <div class="analytics-grid"><article class="card chart-card"><div class="chart-head"><div><h2>Performance trend</h2><p>Average marks across all courses</p><div class="chart-total">84.6 <span>↑ 3.2% this term</span></div></div><select class="chart-select" aria-label="Chart period"><option>Last 8 weeks</option><option>This term</option></select></div>${trendChart()}</article>
        <article class="card chart-card"><div class="chart-head"><div><h2>Grade distribution</h2><p>248 students · all active courses</p></div><button class="icon-button" data-action="more-options" aria-label="More options">${icon("more")}</button></div><div class="distribution">${[12,20,30,23,15].map((width) => `<span class="distribution-segment" style="flex:${width}"></span>`).join("")}</div><div class="distribution-legend">${[["A", "38", ""], ["B", "61", "k2"], ["C", "74", "k3"], ["D", "51", "k4"], ["F", "24", "k5"]].map(([grade, count, key]) => `<div class="distribution-item"><span class="distribution-key ${key}"></span><span>${grade}<strong>${count}</strong></span></div>`).join("")}</div></article></div>
      <div class="lower-grid"><article class="card deadline-card">${sectionHeader("Upcoming deadlines", "A clear view of what’s next", "Assignments")}<div class="timeline">${[["Operating Systems — Assignment 02", "CS 301 · 31 submissions", "Tomorrow, 11:59 PM", true], ["Database Systems — Project 01", "CS 220 · 38 submissions", "Nov 03, 11:59 PM", false], ["Data Structures — Quiz 04", "CS 204 · 42 submissions", "Nov 05, 9:00 AM", false]].map(([title, detail, due, urgent]) => `<div class="timeline-item ${urgent ? "urgent" : ""}"><p class="timeline-title">${title}</p><div class="timeline-sub"><span>${detail}</span><span class="deadline-when">${due}</span></div></div>`).join("")}</div></article>
      <article class="card recent-card">${sectionHeader("Recent submissions", "Your latest classroom activity", "Submissions")}${recentTable(state.submissions.slice(0,3))}</article></div>`;
  }
  function trendChart() {
    return `<svg class="trend-chart" viewBox="0 0 520 132" preserveAspectRatio="none" role="img" aria-label="Average marks trend rises from 76 to 85 over eight weeks">
      <defs><linearGradient id="chartFill" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#81927f" stop-opacity=".16"/><stop offset="1" stop-color="#81927f" stop-opacity="0"/></linearGradient></defs>
      ${[18,46,74,102].map((y) => `<line x1="35" y1="${y}" x2="510" y2="${y}" class="grid-line"/>`).join("")}
      <text x="2" y="21" class="chart-label">100</text><text x="8" y="49" class="chart-label">90</text><text x="8" y="77" class="chart-label">80</text><text x="8" y="105" class="chart-label">70</text>
      <path d="M38 85 C64 81 72 77 103 78 S143 69 168 73 S206 57 236 61 S277 62 303 50 S342 47 371 51 S410 38 438 40 S477 29 507 24 L507 105 L38 105Z" class="trend-area"/>
      <path d="M38 85 C64 81 72 77 103 78 S143 69 168 73 S206 57 236 61 S277 62 303 50 S342 47 371 51 S410 38 438 40 S477 29 507 24" class="trend-line"/>
      <circle cx="303" cy="50" r="4" class="trend-point"/><rect x="274" y="24" width="59" height="18" rx="5" fill="#34483b"/><text x="303" y="36" fill="#fff" font-size="8" font-family="DM Sans" text-anchor="middle">Week 5 · 84</text>
      ${[["W1",38],["W2",103],["W3",168],["W4",236],["W5",303],["W6",371],["W7",438],["W8",507]].map(([label,x]) => `<text x="${x}" y="125" class="chart-label" text-anchor="middle">${label}</text>`).join("")}
    </svg>`;
  }
  function studentDashboard() {
    const assignmentRows = [
      ["Data Structures — Assignment 03", "CS 204 · Due Oct 31, 11:59 PM", "In progress", "Continue"],
      ["Operating Systems — Assignment 02", "CS 301 · Due Nov 01, 11:59 PM", "Not started", "View assignment"],
      ["Database Systems — Project 01", "CS 220 · Due Nov 03, 11:59 PM", "Submitted · grading", "View status"],
    ];
    return `<div class="page-heading"><div><div class="eyebrow">Student workspace · Saturday, October 31</div><h1>Good morning, Maya.</h1><p class="page-subtitle">Here’s where your learning stands today.</p></div><div class="heading-actions">${button("Join a course", "join-course", "secondary", "plus")}</div></div>
      <div class="student-welcome card"><h2>Keep your momentum.</h2><p>You have 2 assignments coming up this week. A little progress today goes a long way.</p></div>
      <div class="student-columns"><div><div class="section-heading" style="margin-top:17px"><div><h2>My assignments</h2><p>Stay on top of what’s due next.</p></div><button class="text-link" data-page="Assignments">All assignments ${icon("arrow",13)}</button></div>
        ${assignmentRows.map(([title, sub, status, action]) => `<div class="card student-action-card"><div class="student-assignment-title"><span class="course-icon small">${icon("assignments",15)}</span><span><strong>${title}</strong><small>${sub}</small></span></div><div style="display:flex;align-items:center;gap:10px">${badge(status === "Not started" ? "Pending" : status === "In progress" ? "Pending" : "Processing")}${button(action, "student-action", "secondary", "chevron")}</div></div>`).join("")}
        <div class="section-heading" style="margin-top:22px"><div><h2>Recently published</h2><p>Feedback is ready to explore.</p></div></div><div class="card student-action-card"><div class="student-assignment-title">${avatar("Maya Chen")}<span><strong>Binary Search Trees — Quiz 03</strong><small>Data Structures · Published Oct 28</small></span></div><div style="display:flex;align-items:center;gap:12px"><strong class="grade">18 / 20</strong>${button("View feedback", "student-feedback", "secondary", "chevron")}</div></div>
      </div><aside><div class="section-heading" style="margin-top:17px"><div><h2>Your progress</h2><p>A snapshot of your term.</p></div></div><div class="metric-strip" style="grid-template-columns:1fr 1fr"><div class="card result-card"><span>Current average</span><strong>86.4</strong><small>↑ 2.8 this month</small></div><div class="card result-card"><span>Assignments</span><strong>12 / 15</strong><small>3 still to come</small></div></div><div class="card" style="padding:16px;margin-top:12px"><div class="section-heading"><div><h2>Class leaderboard</h2><p>You’re making steady progress.</p></div></div><div style="display:flex;align-items:center;gap:10px;padding-top:6px">${avatar("Maya Chen")}<span style="flex:1;font-size:10px"><strong>#4 in Data Structures</strong><span style="display:block;color:#92938c;font-size:9px">Top 12% of the class</span></span>${icon("award",17)}</div></div><div class="section-heading" style="margin-top:20px"><div><h2>Course updates</h2></div></div><div class="notice-panel"><div class="notice-item"><strong>New course material</strong>Week 07: Trees &amp; Graphs slides are available.</div><div class="notice-item"><strong>Feedback published</strong>Your Quiz 03 feedback is ready to review.</div></div></aside></div>`;
  }
  function coursesPage() {
    const query = state.courseQuery.toLowerCase();
    const filtered = courses.filter((course) => `${course[0]} ${course[1]} ${course[2]}`.toLowerCase().includes(query));
    return `${heading("Your courses", "Every class, thoughtfully brought together.", button("Create course", "create-course", "primary", "plus"))}
      <div class="toolbar"><div class="toolbar-left"><label class="inline-search">${icon("search")}<input id="course-search" type="search" value="${escapeHtml(state.courseQuery)}" placeholder="Search courses..." aria-label="Search courses"></label><select class="filter-select" aria-label="Course term"><option>Spring term 2026</option><option>Fall term 2026</option></select></div><div class="toolbar-right"><button class="button button-secondary button-sm" data-action="course-filter">${icon("filter")}All courses${icon("down",12)}</button></div></div>
      <div class="course-grid">${filtered.length ? filtered.map(([name, code, instructor, count, assignments, activity]) => `<article class="card course-card"><div class="course-top"><span class="course-icon">${icon("courses",18)}</span><span class="course-code">${code}</span></div><h3>${name}</h3><div class="course-instructor">${instructor}</div><div class="course-stats"><div class="course-stat"><strong>${count}</strong><span>Students</span></div><div class="course-stat"><strong>${assignments}</strong><span>Assignments</span></div><div class="course-stat"><strong>${Math.round(count * .75)}</strong><span>Active this week</span></div></div><div class="course-activity"><span>Course activity</span><span style="display:flex;align-items:center;gap:7px"><span class="activity-bar"><span style="width:${activity}%"></span></span>${activity}%</span></div><button class="text-link" style="margin-top:12px" data-action="open-course" data-course="${escapeHtml(name)}">Open course ${icon("arrow",13)}</button></article>`).join("") : `<div class="card empty-state">No courses match “${escapeHtml(state.courseQuery)}”.</div>`}</div>`;
  }
  function materialsPage() {
    return `${heading("Course materials", "Keep the knowledge behind every assignment in one place.", button("Add materials", "upload-trigger", "primary", "plus"))}
      <div class="toolbar"><div class="toolbar-left"><select class="filter-select" aria-label="Select course"><option>Data Structures · CS 204</option><option>Operating Systems · CS 301</option><option>Database Systems · CS 220</option></select><div class="segmented">${["All files", "Course docs", "Reference"].map((item, index) => `<button class="segment ${index === 0 ? "active" : ""}" data-material-filter="${item}">${item}</button>`).join("")}</div></div><div class="toolbar-right"><span style="color:#85877f;font-size:9px">${state.materials.length} files · Demo data</span></div></div>
      <div class="materials-drop" id="drop-zone"><span class="drop-icon">${icon("upload")}</span><strong>Drop your course materials here</strong><p>PDF, PPTX, DOCX up to 25 MB · Processing states shown are mock prototype data.</p><button class="button button-secondary button-sm" data-action="upload-trigger">Browse files</button><input id="file-input" class="hidden" type="file" multiple accept=".pdf,.ppt,.pptx,.doc,.docx,.txt"></div>
      <div class="section-heading"><div><h2>Course library</h2><p>Files are visible to enrolled students when shared.</p></div><button class="text-link" data-action="manage-visibility">Manage visibility ${icon("chevron",13)}</button></div>
      <div class="card file-list"><div class="file-header"><span>Name</span><span>Category</span><span>Size</span><span>Uploaded</span><span>Processing</span><span></span></div>${state.materials.map((file, index) => `<div class="file-row"><div class="file-name"><span class="file-icon">${icon("file",16)}</span><span style="min-width:0"><strong>${escapeHtml(file.name)}</strong><small>AI indexing: ${escapeHtml(file.index)} · Demo</small></span></div><span class="file-cell">${escapeHtml(file.type)}</span><span class="file-cell">${escapeHtml(file.size)}</span><span class="file-cell">${escapeHtml(file.date)}</span><span>${badge(file.status)}</span><button class="icon-button" data-action="material-menu" data-index="${index}" aria-label="More options for ${escapeHtml(file.name)}">${icon("more",15)}</button></div>`).join("")}</div>`;
  }
  function assignmentPage() {
    return `${heading("Create assignment", "Give your class a clear, thoughtful next step.", `<button class="button button-secondary" data-action="save-draft">${icon("file")}Save draft</button>${button("Publish assignment", "publish-assignment", "primary", "send")}`)}
      <div class="editor-layout"><div class="editor-main"><article class="card editor-card"><h2>Assignment details</h2><div class="field-block"><label class="field-label" for="assignment-title">Assignment title</label><input id="assignment-title" class="field-input" placeholder="e.g. Data Structures — Assignment 04"></div><div class="field-block"><label class="field-label" for="assignment-description">Description for students</label><textarea id="assignment-description" class="field-textarea" placeholder="Set the context and let students know what they’ll learn..."></textarea></div></article>
        <article class="card editor-card"><div class="section-heading"><div><h2>Questions</h2><p>2 questions · 15 marks total</p></div><button class="button button-secondary button-sm" data-action="reorder-questions">${icon("filter")}Reorder</button></div><div id="question-list">${renderQuestions()}</div><button class="button button-secondary button-sm add-question" data-action="add-question">${icon("plus")}Add a question</button></article></div>
        <aside class="editor-side"><article class="card ai-panel"><div class="ai-title"><span class="feature-symbol">${icon("sparkles")}</span><h2>Generate with AI</h2></div><p class="ai-caption">A starting point, always yours to review.</p><div class="field-block"><label class="field-label">Difficulty</label><div class="difficulty-options">${["Easy","Medium","Hard","Mixed"].map((item) => `<button class="difficulty-option ${state.difficulty === item ? "active" : ""}" data-difficulty="${item}">${item}</button>`).join("")}</div></div><div class="field-block"><label class="field-label" for="question-count">Question count</label><select id="question-count" class="field-select"><option>3 questions</option><option selected>5 questions</option><option>8 questions</option><option>10 questions</option></select></div><div class="field-block"><label class="field-label" for="question-type">Question type</label><select id="question-type" class="field-select"><option>Mix of subjective &amp; MCQ</option><option>Subjective only</option><option>MCQ only</option></select></div><div class="field-block"><label class="field-label">Source materials</label><label class="material-check"><input type="checkbox" checked> Week 07: Trees &amp; Graphs</label><label class="material-check"><input type="checkbox" checked> Course syllabus</label><label class="material-check"><input type="checkbox"> Grading rubric</label></div><p class="ai-disclaimer">Generated questions are suggestions only. Review for accuracy, fairness, and course fit before publishing.</p><button class="button button-primary ai-generate" data-action="generate-questions">${icon("sparkles")}Generate questions</button></article>
        <article class="card editor-card"><h2>Assignment settings</h2><div class="field-block"><label class="field-label">Course</label><select class="field-select"><option>Data Structures · CS 204</option><option>Operating Systems · CS 301</option><option>Database Systems · CS 220</option></select></div><div class="field-block"><label class="field-label">Due date</label><input class="field-input" type="datetime-local" value="2026-11-07T23:59"></div><div class="field-block"><label class="field-label">Total marks</label><input class="field-input" type="number" value="${state.questions.reduce((total, question) => total + Number(question.marks || 0), 0)}" min="1"></div><div class="field-block"><label class="field-label">Rubric</label><select class="field-select"><option>Data Structures — Standard rubric</option><option>Create a rubric</option></select></div><div class="publish-toggle"><span><strong>Publish when ready</strong><small>Students can see after publishing</small></span><button class="switch" data-action="toggle-switch" role="switch" aria-checked="false" aria-label="Publish when ready"></button></div></article></aside></div>`;
  }
  function renderQuestions() {
    return state.questions.map((question, index) => `<article class="question-card" data-question="${index}"><div class="question-head"><div class="question-label"><span class="question-number">${index + 1}</span>Question ${index + 1}<span class="status status-draft">${question.type}</span></div><div class="question-tools"><button class="icon-button" data-action="move-question-up" data-index="${index}" aria-label="Move question up">${icon("chevron",13)}</button><button class="icon-button" data-action="duplicate-question" data-index="${index}" aria-label="Duplicate question">${icon("file",13)}</button><button class="icon-button" data-action="delete-question" data-index="${index}" aria-label="Delete question">${icon("trash",13)}</button></div></div><div class="question-two-col"><div><label class="field-label">Question prompt</label><textarea class="field-textarea question-title" data-index="${index}" placeholder="Write your question...">${escapeHtml(question.title)}</textarea></div><div><label class="field-label">Type · marks</label><select class="field-select question-type" data-index="${index}"><option ${question.type === "Subjective" ? "selected" : ""}>Subjective</option><option ${question.type === "MCQ" ? "selected" : ""}>MCQ</option></select><input class="field-input question-marks" data-index="${index}" style="margin-top:7px" type="number" value="${question.marks}" min="1" aria-label="Marks"></div></div><div style="margin-top:10px"><label class="field-label">${question.type === "MCQ" ? "Correct answer" : "Expected answer / marking guidance"}</label><textarea class="field-textarea question-answer" data-index="${index}" style="min-height:54px">${escapeHtml(question.answer)}</textarea></div>${question.type === "MCQ" ? `<div class="mcq-option"><input type="radio" name="correct-${index}" checked><input class="field-input" value="In-order traversal" aria-label="Option A"><span class="small-label">A</span></div><div class="mcq-option"><input type="radio" name="correct-${index}"><input class="field-input" value="Pre-order traversal" aria-label="Option B"><span class="small-label">B</span></div>` : ""}</article>`).join("");
  }
  function submissionsPage() {
    const items = getVisibleSubmissions();
    return `${heading("Submissions", "A considered review queue. Late work always gets a human decision.", button("Export submissions", "export-submissions", "secondary", "download"))}
      <div class="submission-summary">${[["18","Pending review","clock"],["3","OCR needs a check","ocr"],["4","Late · decision needed","alert"],["36","Published this week","checkCircle"]].map(([n,label,ico]) => `<div class="card summary-chip"><span class="stat-icon">${icon(ico,15)}</span><span><strong>${n}</strong><span>${label}</span></span></div>`).join("")}</div>
      <div class="late-note">${icon("alert",15)}<span><strong>Late submissions are held for your review.</strong> No automatic zero is applied; accept or reject each submission based on your course policy.</span></div>
      <div class="toolbar"><div class="toolbar-left"><div class="segmented">${["All","Pending","Reviewed","Late","Needs OCR Review","Published"].map((item) => `<button class="segment ${state.filter === item ? "active" : ""}" data-filter="${item}">${item}</button>`).join("")}</div></div><div class="toolbar-right"><label class="inline-search">${icon("search")}<input id="submission-search" type="search" value="${escapeHtml(state.search)}" placeholder="Find a student..." aria-label="Find a student"></label><select class="filter-select"><option>All courses</option><option>Data Structures</option><option>Operating Systems</option></select></div></div>
      <div class="card table-card" id="submission-table">${items.length ? recentTable(items) : `<div class="empty-state">No submissions match this view.</div>`}</div>`;
  }
  function gradingPage() {
    const current = state.submissions.find((item) => item.status === "Pending") || state.submissions[0];
    return `${heading("AI grading review", "A second set of eyes. The final grade is always your call.", `<span class="review-nav"><button class="icon-button" data-action="previous-review" aria-label="Previous submission">${icon("chevron",14)}</button><span class="review-count">1 of 24 awaiting review</span><button class="icon-button" data-action="next-review" aria-label="Next submission">${icon("chevron",14)}</button></span>`)}
      <div class="review-topline"><span>Data Structures</span>${icon("chevron",12)}<span>Assignment 03</span>${icon("chevron",12)}<span style="color:var(--ink);font-weight:600">${current.student}</span></div>
      <div class="review-workspace"><div class="review-left"><article class="card review-panel"><div class="review-panel-head"><div class="submission-person">${avatar(current.student)}<span><strong>${current.student}</strong><small>Submitted today at 9:18 AM · On time</small></span></div><button class="button button-secondary button-sm" data-action="download-pdf">${icon("download")}Original PDF</button></div>
        <div class="document-preview"><div class="document-meta"><span>assignment_03_submission.pdf</span><span>Page 1 of 4</span></div><h3>Question 1 · Binary Search Trees <span style="float:right;color:#999a92;font:500 9px var(--font)">10 marks</span></h3><p>Explain how a balanced binary search tree maintains O(log n) time complexity for insertion and search operations. Include one example of a balancing operation.</p><p style="margin-top:18px;color:#9b9c95;font-size:8px">STUDENT RESPONSE · OCR TRANSCRIPTION</p><p>A balanced binary search tree maintains its height by ensuring the difference between the heights of its left and right subtrees stays within a small bound. When an insertion makes the tree unbalanced, a <span class="ocr-highlight">rotation</span> is performed to restore balance.</p><p>For example, an AVL tree uses single or double rotations after insertions. This keeps the height at O(log n), so searching and inserting remain efficient even in the worst case.</p><p style="color:#a2a39b;font-style:italic">[Diagram detected in source · open original PDF to inspect]</p></div>
        <div class="ocr-banner"><span class="ocr-banner-text">${icon("alert",15)}<span><strong>Check highlighted OCR</strong><br>One word has lower recognition confidence.</span></span><button class="button button-secondary button-sm" data-action="ocr-confirm">Verify text</button></div>
      </article><article class="card review-panel"><div class="review-panel-head"><div><h2>Question 2 · BST traversal</h2><span style="color:#93948c;font-size:9px">5 marks · Multiple choice</span></div><span class="status status-ready">OCR verified</span></div><div class="document-preview" style="min-height:0;padding:13px 15px"><p style="margin:0">Which traversal visits nodes in ascending order in a binary search tree?</p><p style="margin:9px 0 0;color:#526952;font-weight:650">Selected answer: In-order traversal</p></div></article></div>
      <aside class="review-right"><article class="card review-panel"><div class="review-panel-head"><h2>AI suggested grade</h2><span class="status status-reviewed">For your review</span></div><div class="confidence-row"><span class="confidence-copy"><strong>AI confidence</strong><small>Based on your rubric and course materials</small></span><strong class="confidence-value">91%</strong></div><div class="confidence-bar"><span></span></div><div style="margin:14px 0 8px;color:#84867e;font-size:9px;font-weight:650">RUBRIC BREAKDOWN</div>
        ${[["Conceptual understanding","Clearly explains balance and complexity.",7,8],["Example & application","Identifies rotations; example could be more specific.",4,5],["Clarity & terminology","Accurate terms and easy to follow.",4,5]].map(([title,desc,score,max]) => `<div class="rubric-row"><span><strong>${title}</strong><small>${desc}</small></span><input class="rubric-score score-input" type="number" min="0" max="${max}" value="${score}" aria-label="${title} score"><span class="rubric-max">/ ${max} pts</span></div>`).join("")}
        <div class="grade-total"><span>Suggested total</span><strong id="grade-total">15 / 18</strong></div></article>
        <article class="card review-panel"><div class="review-panel-head"><h2>Feedback suggestion</h2><button class="icon-button" data-action="edit-feedback" aria-label="Edit feedback">${icon("edit",14)}</button></div><div class="ai-feedback" id="feedback-text"><strong>A good foundation</strong>You correctly explain why balancing keeps operations efficient and identify rotations as the key mechanism. For a stronger answer, include a specific example of a left or right rotation and explain when it applies.</div><div class="field-block" style="margin-top:12px;margin-bottom:0"><label class="field-label" for="teacher-note">Note to student (optional)</label><textarea id="teacher-note" class="field-textarea" style="min-height:55px" placeholder="Add a personal note..."></textarea></div></article>
        <article class="card review-panel"><div class="review-actions">${button("Return for review", "return-submission", "secondary", "edit")}${button("Approve & publish", "approve-grade", "primary", "check")}</div><p style="margin:9px 0 0;color:#999a92;font-size:8px;text-align:center">You can edit this grade and feedback before publishing.</p></article></aside></div>`;
  }
  function assignmentsPage() {
    const list = [
      ["Data Structures — Assignment 03", "CS 204 · 96 students · Due Oct 31", "Published", "72 / 96 reviewed"],
      ["Operating Systems — Assignment 02", "CS 301 · 38 students · Due Nov 01", "Published", "31 / 38 reviewed"],
      ["Database Systems — Project 01", "CS 220 · 46 students · Due Nov 03", "Published", "12 / 46 reviewed"],
      ["Computer Networks — Quiz 04", "CS 315 · 31 students · Due Nov 07", "Draft", "Not yet published"],
    ];
    return `${heading("Assignments", "Thoughtfully set up, clearly tracked, and always teacher-led.", button("Create assignment", "create-assignment", "primary", "plus"))}
      <div class="toolbar"><div class="toolbar-left"><label class="inline-search">${icon("search")}<input placeholder="Search assignments..." aria-label="Search assignments"></label><select class="filter-select"><option>All courses</option><option>Data Structures</option></select><div class="segmented">${["All","Published","Draft"].map((item,i) => `<button class="segment ${i===0?"active":""}" data-filter="${item}">${item}</button>`).join("")}</div></div><div class="toolbar-right"><button class="button button-secondary button-sm" data-action="sort-assignments">${icon("filter")}Sort by due date</button></div></div>
      <div class="card table-card"><div class="table-wrap"><table class="data-table"><thead><tr><th>Assignment</th><th>Course</th><th>Due date</th><th>Submissions</th><th>State</th><th>Grading progress</th><th></th></tr></thead><tbody>${list.map((row) => `<tr><td><span class="student-cell">${icon("assignments",15)}${row[0]}</span></td><td>${row[1].split(" · ")[0]}</td><td>${row[1].split(" · ")[2]}</td><td>${row[1].split(" · ")[1].split(" ")[0]}</td><td>${badge(row[2])}</td><td>${row[3]}</td><td>${rowAction("Open", "open-review")}</td></tr>`).join("")}</tbody></table></div></div>`;
  }
  function ocrPage() {
    const flagged = state.submissions.filter((item) => item.ocr === "Needs review" || item.status === "Needs OCR Review");
    return `${heading("OCR review", "Verify uncertain text before it reaches the grading workflow.", button("How OCR works", "ocr-info", "secondary", "alert"))}
      <div class="late-note">${icon("alert",15)}<span>OCR is a reading aid, not a source of truth. Confirm the original student submission whenever text is uncertain.</span></div>
      <div class="card table-card">${recentTable(flagged.length ? flagged : [state.submissions[2], state.submissions[5]], true)}</div>`;
  }
  function resultsPage() {
    return `${heading("Results & performance", "A thoughtful picture of learning across your courses.", button("Export results", "export-submissions", "secondary", "download"))}
      <div class="metric-strip">${[["Class average","84.6","↑ 3.2% this term"],["Submissions graded","86%","207 of 240 submitted"],["Feedback published","164","↑ 18 this week"],["At-risk students","6","Across 3 courses"]].map(([name,value,note]) => `<article class="card result-card"><span>${name}</span><strong>${value}</strong><small>${note}</small></article>`).join("")}</div>
      <div class="analytics-grid"><article class="card chart-card"><div class="chart-head"><div><h2>Performance trend</h2><p>Average marks across all courses</p><div class="chart-total">84.6 <span>↑ 3.2% this term</span></div></div><select class="chart-select"><option>Last 8 weeks</option><option>This term</option></select></div>${trendChart()}</article><article class="card chart-card"><div class="chart-head"><div><h2>Grade distribution</h2><p>248 students · all active courses</p></div></div><div class="distribution">${[12,20,30,23,15].map((width) => `<span class="distribution-segment" style="flex:${width}"></span>`).join("")}</div><div class="distribution-legend">${[["A", "38", ""], ["B", "61", "k2"], ["C", "74", "k3"], ["D", "51", "k4"], ["F", "24", "k5"]].map(([g,n,k]) => `<div class="distribution-item"><span class="distribution-key ${k}"></span><span>${g}<strong>${n}</strong></span></div>`).join("")}</div></article></div>
      <article class="card recent-card">${sectionHeader("Course performance", "Averages and review progress by course")}<div class="table-wrap"><table class="data-table"><thead><tr><th>Course</th><th>Students</th><th>Average</th><th>Change</th><th>Graded</th><th>Students to check in</th></tr></thead><tbody>${courses.slice(0,5).map((course,index) => `<tr><td><span class="student-cell"><span class="course-icon small">${icon("courses",14)}</span>${course[0]}</span></td><td>${course[3]}</td><td class="grade">${[86.2,82.7,88.4,79.8,85.1][index]}</td><td style="color:var(--sage-dark)">↑ ${(index+2)*.7}%</td><td>${[82,74,91,68,88][index]}%</td><td>${index===2?2:index===4?1:0}</td></tr>`).join("")}</tbody></table></div></article>`;
  }
  function leaderboardPage() {
    const ranks = [["Maya Chen","CS 204 · Data Structures",96, "gold"],["Ethan Brooks","CS 204 · Data Structures",94,"silver"],["Sofia Patel","CS 204 · Data Structures",92,"bronze"],["Amara Okafor","CS 204 · Data Structures",90,""],["Noah Williams","CS 204 · Data Structures",88,""],["Leo Fischer","CS 204 · Data Structures",85,""]];
    return `${heading("Leaderboard", "Celebrate steady effort and progress across the class.", `<select class="filter-select"><option>Data Structures · CS 204</option><option>All courses</option></select>`)}
      <div class="late-note">${icon("award",15)}<span>Leaderboards are a snapshot of published grades and participation. They’re here to encourage progress, not define it.</span></div>
      <div class="card table-card"><div class="table-wrap"><table class="data-table"><thead><tr><th>Rank</th><th>Student</th><th>Course</th><th>Average</th><th>Assignments</th><th>Trend</th></tr></thead><tbody>${ranks.map(([name,course,score,rank],index) => `<tr><td><span class="leaderboard-rank ${rank}">${index+1}</span></td><td><span class="student-cell">${avatar(name)}${name}${name==="Maya Chen" ? `<span class="status status-ready" style="margin-left:3px">You</span>` : ""}</span></td><td>${course.split(" · ")[0]}</td><td class="grade">${score}%</td><td>${12-index%3} / 15</td><td style="color:var(--sage-dark)">↗ Improving</td></tr>`).join("")}</tbody></table></div></div>`;
  }
  function settingsPage() {
    return `${heading("Settings", "Make TrustGrade work the way your classroom works.", "")}<div class="settings-layout"><nav class="card settings-nav">${["Profile","Notifications","Grading preferences","Accessibility","Security"].map((item,index) => `<button class="settings-link ${index===0?"active":""}" data-settings="${item}">${item}</button>`).join("")}</nav><article class="card settings-content"><h2>Profile &amp; workspace</h2><p>Manage your personal information and workspace defaults.</p><div class="settings-row"><span><strong>Display name</strong><small>Shown to students and collaborators</small></span><input class="field-input" style="max-width:230px" value="Alex Morgan"></div><div class="settings-row"><span><strong>Email address</strong><small>Used for account notifications</small></span><input class="field-input" style="max-width:230px" value="alex.morgan@university.edu"></div><div class="settings-row"><span><strong>Default workspace</strong><small>Open this workspace when you sign in</small></span><select class="field-select" style="max-width:230px"><option>Faculty workspace</option><option>Student preview</option></select></div><div class="settings-row"><span><strong>Review notifications</strong><small>Get a note when submissions need attention</small></span><button class="switch on" data-action="toggle-switch" role="switch" aria-checked="true" aria-label="Review notifications"></button></div><div style="display:flex;justify-content:flex-end;margin-top:15px">${button("Save changes", "save-settings", "primary", "check")}</div></article></div>`;
  }
  function renderPage() {
    switch (state.page) {
      case "Overview": return dashboard();
      case "Courses": return coursesPage();
      case "Course Materials": return materialsPage();
      case "Assignments": return assignmentsPage();
      case "Create Assignment": return assignmentPage();
      case "Submissions": return submissionsPage();
      case "AI Grading": return gradingPage();
      case "OCR Review": return ocrPage();
      case "Results": return resultsPage();
      case "Leaderboard": return leaderboardPage();
      case "Settings": return settingsPage();
      default: return dashboard();
    }
  }
  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
  }
  function render() {
    renderShell();
    wireDropzone();
  }
  function toast(message) {
    document.querySelector(".toast")?.remove();
    const node = document.createElement("div");
    node.className = "toast";
    node.setAttribute("role", "status");
    node.innerHTML = `${icon("checkCircle", 15)}<span>${escapeHtml(message)}</span>`;
    document.body.appendChild(node);
    window.setTimeout(() => node.remove(), 3000);
  }
  function openModal(title, body, submitLabel, onSubmit) {
    const backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop";
    backdrop.innerHTML = `<section class="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title"><div class="modal-head"><h2 id="modal-title">${title}</h2><button class="icon-button" data-modal-close aria-label="Close">${icon("close")}</button></div><div class="modal-body">${body}</div><div style="display:flex;justify-content:flex-end;gap:8px;margin-top:15px"><button class="button button-secondary" data-modal-close>Cancel</button><button class="button button-primary" data-modal-submit>${submitLabel}</button></div></section>`;
    document.body.appendChild(backdrop);
    backdrop.addEventListener("click", (event) => {
      if (event.target === backdrop || event.target.closest("[data-modal-close]")) backdrop.remove();
      if (event.target.closest("[data-modal-submit]")) {
        const values = Object.fromEntries([...backdrop.querySelectorAll("[data-modal-field]")].map((field) => [field.dataset.modalField, field.value.trim()]));
        if (onSubmit(values) !== false) backdrop.remove();
      }
    });
    backdrop.querySelector("input,select,textarea")?.focus();
  }
  function navigate(page) {
    state.page = page;
    state.notificationsOpen = false;
    if (page !== "Submissions") state.search = "";
    render();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
  function addQuestion(question = { title: "", type: "Subjective", marks: 5, answer: "" }) {
    state.questions.push(question);
    render();
    document.querySelector(".question-card:last-child .question-title")?.focus();
  }
  function calculateGrade() {
    const inputs = [...document.querySelectorAll(".score-input")];
    if (!inputs.length) return;
    const score = inputs.reduce((total, input) => total + (Number(input.value) || 0), 0);
    const maximum = inputs.reduce((total, input) => total + (Number(input.max) || 0), 0);
    document.getElementById("grade-total").textContent = `${score} / ${maximum}`;
  }
  function handleUpload(files) {
    [...files].forEach((file) => {
      const extension = file.name.split(".").pop()?.toLowerCase() || "";
      const category = extension === "ppt" || extension === "pptx" ? "Lecture slides" : extension === "doc" || extension === "docx" ? "Notes" : "Reference";
      state.materials.unshift({ name: file.name, type: category, size: file.size > 1048576 ? `${(file.size / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(file.size / 1024))} KB`, date: "Just now", status: "Uploading", index: "Not started" });
    });
    render();
    toast(`${files.length} file${files.length === 1 ? "" : "s"} added to the demo materials list.`);
  }
  function wireDropzone() {
    const zone = document.getElementById("drop-zone");
    const input = document.getElementById("file-input");
    if (!zone || !input) return;
    input.addEventListener("change", () => { if (input.files?.length) handleUpload(input.files); });
    ["dragenter", "dragover"].forEach((event) => zone.addEventListener(event, (e) => { e.preventDefault(); zone.classList.add("dragover"); }));
    ["dragleave", "drop"].forEach((event) => zone.addEventListener(event, (e) => { e.preventDefault(); zone.classList.remove("dragover"); }));
    zone.addEventListener("drop", (e) => { if (e.dataTransfer?.files?.length) handleUpload(e.dataTransfer.files); });
  }
  function exportRows() {
    const rows = [["Student", "Assignment", "Submitted", "OCR", "Grade", "Status"], ...state.submissions.map((item) => [item.student, item.assignment, item.submitted, item.ocr, item.grade, item.status])];
    const csv = rows.map((row) => row.map((field) => `"${String(field).replaceAll('"', '""')}"`).join(",")).join("\r\n");
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    link.download = "trustgrade-submissions.csv";
    link.click();
    URL.revokeObjectURL(link.href);
    toast("Submission report exported.");
  }
  function handleAction(action, target) {
    const index = Number(target.dataset.index);
    if (action === "create-assignment") navigate("Create Assignment");
    else if (action === "open-review") navigate("AI Grading");
    else if (action === "switch-role") {
      state.role = state.role === "teacher" ? "student" : "teacher";
      state.page = "Overview";
      render();
      toast(`Switched to ${state.role} workspace preview.`);
    }
    else if (action === "notifications") { state.notificationsOpen = !state.notificationsOpen; render(); }
    else if (action === "create-course") openModal("Create a course", `<div class="field-block"><label class="field-label">Course name</label><input class="field-input" data-modal-field="name" placeholder="e.g. Applied Computing"></div><div class="field-block"><label class="field-label">Course code</label><input class="field-input" data-modal-field="code" placeholder="e.g. CS 240"></div>`, "Create course", ({ name, code }) => { if (!name || !code) { toast("Add a course name and code first."); return false; } courses.unshift([name, code, "Dr. Alex Morgan", 0, 0, 0]); render(); toast(`${name} added to this prototype.`); });
    else if (action === "join-course") openModal("Join a course", `<p style="color:#7d7f77;font-size:10px">Enter the invite code your instructor shared.</p><div class="field-block"><label class="field-label">Course invite code</label><input class="field-input" data-modal-field="code" placeholder="e.g. DS-204-AB7"></div>`, "Request to join", ({ code }) => { if (!code) { toast("Enter a course invite code."); return false; } toast("Join request saved in this prototype."); });
    else if (action === "upload-trigger") document.getElementById("file-input")?.click();
    else if (action === "save-draft") toast("Assignment saved as a draft in this prototype.");
    else if (action === "publish-assignment") {
      const title = document.getElementById("assignment-title")?.value.trim();
      if (!title) { document.getElementById("assignment-title")?.focus(); toast("Add an assignment title before publishing."); return; }
      toast("Assignment published in the prototype. Connect a backend to notify students.");
    }
    else if (action === "add-question") addQuestion();
    else if (action === "generate-questions") {
      const buttonNode = target;
      buttonNode.disabled = true;
      buttonNode.innerHTML = `${icon("refresh")}Drafting suggestions...`;
      const cards = document.getElementById("question-list");
      cards?.classList.add("question-generating");
      window.setTimeout(() => {
        state.questions.push({ title: "Compare the time complexity of breadth-first and depth-first traversal. When would you choose one over the other?", type: "Subjective", marks: 8, answer: "BFS explores level by level; DFS explores each branch deeply. Discuss use cases such as shortest paths or cycle detection." });
        render();
        toast("A draft question was added. Review and edit it before publishing.");
      }, 850);
    }
    else if (action === "delete-question") {
      if (state.questions.length <= 1) { toast("An assignment needs at least one question."); return; }
      state.questions.splice(index, 1); render(); toast("Question removed.");
    }
    else if (action === "duplicate-question") { state.questions.splice(index + 1, 0, { ...state.questions[index] }); render(); toast("Question duplicated."); }
    else if (action === "move-question-up") { if (index > 0) { [state.questions[index - 1], state.questions[index]] = [state.questions[index], state.questions[index - 1]]; render(); } }
    else if (action === "reorder-questions") toast("Use the arrow control on a question to move it up.");
    else if (action === "approve-grade") {
      const score = document.getElementById("grade-total")?.textContent || "15 / 18";
      const person = document.querySelector(".submission-person strong")?.textContent;
      const submission = state.submissions.find((item) => item.student === person && item.status !== "Published");
      if (submission) { submission.grade = score; submission.status = "Published"; }
      toast("Grade approved and feedback published in the prototype.");
      navigate("Submissions");
    }
    else if (action === "return-submission") toast("Submission returned to your review queue.");
    else if (action === "ocr-confirm") toast("OCR text marked as verified for this review.");
    else if (action === "edit-feedback") {
      const feedback = document.getElementById("feedback-text");
      if (feedback && !feedback.isContentEditable) { feedback.contentEditable = "true"; feedback.focus(); feedback.style.outline = "1px solid #cbd4c6"; feedback.style.outlineOffset = "3px"; toast("Edit the feedback suggestion directly."); }
      else if (feedback) { feedback.contentEditable = "false"; feedback.style.outline = ""; toast("Feedback suggestion saved locally."); }
    }
    else if (action === "previous-review" || action === "next-review") toast("You’re viewing the current prototype submission.");
    else if (action === "download-pdf") toast("Original PDF preview is mock data in this prototype.");
    else if (action === "export-submissions") exportRows();
    else if (action === "save-settings") toast("Your preferences have been saved in this prototype.");
    else if (action === "toggle-switch") { target.classList.toggle("on"); target.setAttribute("aria-checked", String(target.classList.contains("on"))); }
    else if (action === "open-course") toast(`Opening ${target.dataset.course} course overview.`);
    else if (action === "student-action") toast("Assignment details are available in this prototype.");
    else if (action === "student-feedback") toast("Published feedback opened in this prototype.");
    else if (action === "manage-visibility") toast("Visibility settings are managed per course in this prototype.");
    else if (action === "material-menu") {
      const file = state.materials[index];
      openModal("Material options", `<p style="color:#777970;font-size:10px">${escapeHtml(file?.name || "Selected file")}</p><label class="field-label">Category</label><select class="field-select" data-modal-field="type"><option>Syllabus</option><option>Rubric</option><option>Lecture slides</option><option>Notes</option><option>Reference</option><option>Rulebook</option></select>`, "Save category", ({ type }) => { if (file) file.type = type; render(); toast("Material details updated."); });
    }
    else if (action === "course-filter") toast("Showing all active courses.");
    else if (action === "sort-assignments") toast("Assignments are sorted by upcoming due date.");
    else if (action === "ocr-info") toast("OCR transcription is a review aid; always check the original document.");
    else if (action === "more-options" || action === "profile-menu" || action === "menu") toast("More options are available as this prototype grows.");
  }
  app.addEventListener("click", (event) => {
    const pageButton = event.target.closest("[data-page]");
    if (pageButton) { event.preventDefault(); navigate(pageButton.dataset.page); return; }
    const filterButton = event.target.closest("[data-filter]");
    if (filterButton) { state.filter = filterButton.dataset.filter; render(); return; }
    const difficultyButton = event.target.closest("[data-difficulty]");
    if (difficultyButton) { state.difficulty = difficultyButton.dataset.difficulty; render(); return; }
    const materialFilter = event.target.closest("[data-material-filter]");
    if (materialFilter) {
      materialFilter.parentElement.querySelectorAll(".segment").forEach((element) => element.classList.remove("active"));
      materialFilter.classList.add("active");
      const term = materialFilter.dataset.materialFilter;
      document.querySelectorAll(".file-row").forEach((row) => { row.classList.toggle("hidden", term === "Course docs" ? !/Syllabus|Rulebook|Rubric/.test(row.textContent) : term === "Reference" ? !/Notes|Reference/.test(row.textContent) : false); });
      return;
    }
    const action = event.target.closest("[data-action]");
    if (action) handleAction(action.dataset.action, action);
  });
  app.addEventListener("input", (event) => {
    if (event.target.id === "course-search") { state.courseQuery = event.target.value; const cursor = event.target.selectionStart; render(); const next = document.getElementById("course-search"); next?.focus(); next?.setSelectionRange(cursor,cursor); }
    if (event.target.id === "submission-search") { state.search = event.target.value; const cursor = event.target.selectionStart; render(); const next = document.getElementById("submission-search"); next?.focus(); next?.setSelectionRange(cursor,cursor); }
    if (event.target.classList.contains("score-input")) calculateGrade();
    const index = Number(event.target.dataset.index);
    if (event.target.classList.contains("question-title") && state.questions[index]) state.questions[index].title = event.target.value;
    if (event.target.classList.contains("question-answer") && state.questions[index]) state.questions[index].answer = event.target.value;
    if (event.target.classList.contains("question-marks") && state.questions[index]) state.questions[index].marks = Number(event.target.value);
  });
  app.addEventListener("change", (event) => {
    const index = Number(event.target.dataset.index);
    if (event.target.classList.contains("question-type") && state.questions[index]) {
      state.questions[index].type = event.target.value;
      render();
    }
  });
  document.addEventListener("click", (event) => {
    if (state.notificationsOpen && !event.target.closest(".notification-wrap")) { state.notificationsOpen = false; render(); }
  });
  document.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); document.getElementById("global-search")?.focus(); }
    if (event.key === "Escape") { document.querySelector(".modal-backdrop")?.remove(); }
  });
  render();
})();
