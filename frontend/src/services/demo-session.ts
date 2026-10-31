import type {
  Assignment,
  Course,
  CourseMaterial,
  Submission,
  User,
} from "../types/models";

export const isDemoMode = (): boolean => {
  return import.meta.env.VITE_DEMO_MODE === "true";
};

export const DEMO_TEACHER: User = {
  id: "demo-teacher-01",
  name: "Professor Demo",
  role: "teacher",
  email: "faculty.demo@trustgrade.local",
  initials: "PD",
};

export const DEMO_STUDENT: User = {
  id: "demo-student-01",
  name: "Student Demo",
  role: "student",
  email: "student.demo@trustgrade.local",
  initials: "SD",
};

export const getStoredDemoSession = (): User | null => {
  if (!isDemoMode()) return null;
  const role = sessionStorage.getItem("tg_demo_role");
  if (role === "teacher") return DEMO_TEACHER;
  if (role === "student") return DEMO_STUDENT;
  return null;
};

export const setDemoSession = (role: "teacher" | "student"): User => {
  sessionStorage.setItem("tg_demo_role", role);
  return role === "teacher" ? DEMO_TEACHER : DEMO_STUDENT;
};

export const clearDemoSession = (): void => {
  sessionStorage.removeItem("tg_demo_role");
};

export const DEMO_PEOPLE: User[] = [
  DEMO_TEACHER,
  DEMO_STUDENT,
  { id: "student-maya", name: "Maya Chen", email: "maya.chen@university.edu", role: "student", initials: "MC" },
  { id: "student-ethan", name: "Ethan Brooks", email: "ethan.brooks@university.edu", role: "student", initials: "EB" },
  { id: "student-sofia", name: "Sofia Patel", email: "sofia.patel@university.edu", role: "student", initials: "SP" },
  { id: "student-noah", name: "Noah Williams", email: "noah.williams@university.edu", role: "student", initials: "NW" },
];

export const DEMO_COURSES: Course[] = [
  {
    id: "demo-cs204",
    name: "Data Structures & Algorithms",
    code: "CS 204",
    instructor: "Professor Demo",
    students: 42,
    assignments: 4,
    activity: 88,
    average: 87.4,
  },
  {
    id: "demo-cs301",
    name: "Operating Systems Architecture",
    code: "CS 301",
    instructor: "Professor Demo",
    students: 38,
    assignments: 3,
    activity: 76,
    average: 83.2,
  },
  {
    id: "demo-cs220",
    name: "Database Systems & Storage",
    code: "CS 220",
    instructor: "Professor Demo",
    students: 46,
    assignments: 5,
    activity: 92,
    average: 89.1,
  },
  {
    id: "demo-cs315",
    name: "Computer Networks & Protocols",
    code: "CS 315",
    instructor: "Professor Demo",
    students: 31,
    assignments: 2,
    activity: 64,
    average: 81.0,
  },
];

export const DEMO_ASSIGNMENTS: Assignment[] = [
  {
    id: "demo-ds-a03",
    courseId: "demo-cs204",
    title: "Balanced Search Trees & Complexity",
    description: "Analyze AVL rotations, red-black tree invariants, and logarithmic operation bounds.",
    dueAt: "2026-11-15T23:59:00",
    totalMarks: 20,
    state: "Published",
    submissionType: "Mixed",
    rubricId: "rubric-bst",
    questions: [
      {
        id: "q-bst-1",
        prompt: "Explain how single and double rotations restore balance in an AVL tree after an insertion.",
        type: "Subjective",
        marks: 10,
        expectedAnswer: "AVL trees detect imbalance when the balance factor exceeds ±1. A single rotation fixes LL or RR cases; a double rotation fixes LR or RL cases.",
      },
      {
        id: "q-bst-2",
        prompt: "Which traversal visits binary search tree nodes in strictly ascending sorted order?",
        type: "MCQ",
        marks: 5,
        expectedAnswer: "In-order traversal",
        options: ["Pre-order", "In-order", "Post-order", "Breadth-first"],
        correctOption: 1,
      },
      {
        id: "q-bst-3",
        prompt: "What is the worst-case search complexity of an unbalanced binary search tree?",
        type: "MCQ",
        marks: 5,
        expectedAnswer: "O(n)",
        options: ["O(1)", "O(log n)", "O(n)", "O(n log n)"],
        correctOption: 2,
      },
    ],
  },
  {
    id: "demo-os-a02",
    courseId: "demo-cs301",
    title: "Process Scheduling & Concurrency",
    description: "Compare preemptive vs non-preemptive schedulers and resolve dining philosophers concurrency.",
    dueAt: "2026-11-18T23:59:00",
    totalMarks: 25,
    state: "Published",
    submissionType: "PDF",
    rubricId: "rubric-bst",
    questions: [
      {
        id: "q-os-1",
        prompt: "Compare round-robin scheduling with shortest-job-first in terms of turnaround time and starvation.",
        type: "Subjective",
        marks: 15,
        expectedAnswer: "Round robin guarantees responsiveness via time quanta; SJF minimizes average turnaround time but may starve CPU-intensive threads.",
      },
    ],
  },
  {
    id: "demo-ds-q03",
    courseId: "demo-cs204",
    title: "Graph Traversal & MST Quiz",
    description: "Quick concept evaluation on Dijkstra and Kruskal algorithms.",
    dueAt: "2026-11-12T17:00:00",
    totalMarks: 20,
    state: "Published",
    submissionType: "MCQ",
    rubricId: "rubric-bst",
    questions: [
      {
        id: "q-quiz-1",
        prompt: "Which algorithm finds the single-source shortest path on graphs with non-negative edge weights?",
        type: "MCQ",
        marks: 10,
        expectedAnswer: "Dijkstra's Algorithm",
        options: ["Dijkstra's Algorithm", "Bellman-Ford", "Floyd-Warshall", "Breadth-first Search"],
        correctOption: 0,
      },
      {
        id: "q-quiz-2",
        prompt: "What is the optimal greedy choice in Kruskal's minimum spanning tree algorithm?",
        type: "MCQ",
        marks: 10,
        expectedAnswer: "Add the lowest-weight edge that does not form a cycle",
        options: [
          "Always branch from the source node",
          "Add the lowest-weight edge that does not form a cycle",
          "Traverse vertices in topological order",
          "Select the maximum degree vertex",
        ],
        correctOption: 1,
      },
    ],
  },
  {
    id: "demo-db-p01",
    courseId: "demo-cs220",
    title: "Relational Schema Normalization",
    description: "Design 3NF and BCNF schemas with functional dependency proofs.",
    dueAt: "2026-11-20T23:59:00",
    totalMarks: 30,
    state: "Published",
    submissionType: "PDF",
    rubricId: "rubric-bst",
    questions: [
      {
        id: "q-db-1",
        prompt: "Decompose a relation with transitive dependencies into Boyce-Codd Normal Form.",
        type: "Subjective",
        marks: 20,
        expectedAnswer: "Demonstrate loss-free join decomposition and dependency preservation.",
      },
    ],
  },
];

export const DEMO_SUBMISSIONS: Submission[] = [
  {
    id: "demo-sub-student-ds",
    studentId: "demo-student-01",
    assignmentId: "demo-ds-a03",
    submittedAt: "2026-10-30T14:22:00",
    deadline: "2026-11-15T23:59:00",
    state: "Published",
    fileName: "student_demo_balanced_trees.pdf",
    answer: "An AVL tree maintains height by executing rotations whenever balance factor exceeds ±1.",
    ocr: {
      confidence: 0.99,
      state: "Verified",
      extractedText: "An AVL tree maintains height balance O(log n) through deterministic single and double rotations. When an insertion causes the height difference between left and right subtrees to exceed 1, a left or right rotation is performed. For LR cases, a left-right double rotation restores invariants.",
      warnings: [],
      expressions: ["h ≤ 1.44 log₂(n + 2) - 0.328", "O(log n)"],
    },
    grading: {
      suggestedScore: 19,
      confidence: 0.98,
      reasoning: "Exceptional mastery of tree rotation mechanics. Formulas and asymptotic bounds are mathematically sound.",
      rubric: [
        { id: "c1", name: "Concept Understanding", description: "Rotations & height balance", score: 10, maximum: 10 },
        { id: "c2", name: "Methodology & Proof", description: "Asymptotic complexity", score: 9, maximum: 10 },
      ],
      feedback: {
        id: "fb-demo-01",
        comment: "Outstanding work on the rotation invariants. Clear, well-structured mathematical explanations.",
        deductions: [],
        courseReferences: ["Lecture 04 — Trees & Rotations"],
      },
      teacherApproved: true,
    },
  },
  {
    id: "demo-sub-student-os",
    studentId: "demo-student-01",
    assignmentId: "demo-os-a02",
    submittedAt: "2026-10-31T11:15:00",
    deadline: "2026-11-18T23:59:00",
    state: "Under Review",
    fileName: "student_demo_scheduling_analysis.pdf",
    answer: "Preemptive schedulers allocate fixed time quanta to prevent CPU starvation.",
    ocr: {
      confidence: 0.97,
      state: "High confidence",
      extractedText: "Preemptive schedulers allocate fixed time quanta to prevent CPU monopolization. Round Robin guarantees responsiveness by rotating processes through the ready queue, whereas SJF minimizes average waiting time but risks starvation for long compute jobs.",
      warnings: [],
      expressions: ["Turnaround = Completion - Arrival"],
    },
    grading: {
      suggestedScore: 23,
      confidence: 0.96,
      reasoning: "Accurate contrast between preemption strategies with sound analysis of thread responsiveness.",
      rubric: [
        { id: "c1", name: "Scheduler Comparison", description: "Trade-offs", score: 12, maximum: 12 },
        { id: "c2", name: "Starvation Mitigations", description: "Aging mechanism", score: 11, maximum: 13 },
      ],
      feedback: {
        id: "fb-demo-02",
        comment: "Great comparison between RR and SJF. Consider adding discussion of priority aging techniques.",
        deductions: [],
        courseReferences: ["Lecture 07 — Process Management"],
      },
      teacherApproved: false,
    },
  },
  {
    id: "demo-sub-maya-ds",
    studentId: "student-maya",
    assignmentId: "demo-ds-a03",
    submittedAt: "2026-10-31T09:42:00",
    deadline: "2026-11-15T23:59:00",
    state: "Under Review",
    fileName: "maya_chen_assignment_03.pdf",
    answer: "A balanced binary search tree maintains logarithmic height through rotations.",
    ocr: {
      confidence: 0.94,
      state: "High confidence",
      extractedText: "A balanced binary search tree keeps height proportional to log n. Red-black trees enforce coloring constraints to ensure the longest path never exceeds twice the shortest path.",
      warnings: ["Minor glare on header line."],
      expressions: ["O(log n)"],
    },
    grading: {
      suggestedScore: 18,
      confidence: 0.94,
      reasoning: "Correct understanding of path invariants and balance maintenance.",
      rubric: [
        { id: "c1", name: "Concept Understanding", description: "Coloring constraints", score: 9, maximum: 10 },
        { id: "c2", name: "Methodology", description: "Path bound proof", score: 9, maximum: 10 },
      ],
      feedback: {
        id: "fb-maya",
        comment: "Strong understanding of red-black tree coloring constraints.",
        deductions: [],
        courseReferences: ["Lecture 05 — Advanced Trees"],
      },
      teacherApproved: false,
    },
  },
  {
    id: "demo-sub-ethan-ds",
    studentId: "student-ethan",
    assignmentId: "demo-ds-a03",
    submittedAt: "2026-10-31T10:05:00",
    deadline: "2026-11-15T23:59:00",
    state: "Submitted",
    fileName: "ethan_brooks_problem_set.pdf",
    answer: "Tree balance is restored via single and double rotations.",
    ocr: {
      confidence: 0.98,
      state: "High confidence",
      extractedText: "Tree balance is maintained through local tree rotations around the unbalanced node.",
      warnings: [],
      expressions: ["O(log n)"],
    },
  },
  {
    id: "demo-sub-sofia-os",
    studentId: "student-sofia",
    assignmentId: "demo-os-a02",
    submittedAt: "2026-10-30T16:20:00",
    deadline: "2026-11-18T23:59:00",
    state: "Published",
    fileName: "sofia_patel_cpu_scheduling.pdf",
    answer: "Round-robin scheduling provides fair CPU share.",
    ocr: {
      confidence: 0.95,
      state: "Verified",
      extractedText: "Round robin scheduling ensures fair CPU share by cycling processes every fixed time quantum.",
      warnings: [],
      expressions: [],
    },
    grading: {
      suggestedScore: 24,
      confidence: 0.97,
      reasoning: "Excellent turnaround analysis and Gantt chart visualization.",
      rubric: [
        { id: "c1", name: "Fair Share Analysis", description: "Time slicing", score: 12, maximum: 12 },
        { id: "c2", name: "Gantt Derivation", description: "Wait times", score: 12, maximum: 13 },
      ],
      feedback: {
        id: "fb-sofia",
        comment: "Excellent turnaround time analysis with well-constructed Gantt charts.",
        deductions: [],
        courseReferences: ["Lecture 07 — Scheduling"],
      },
      teacherApproved: true,
    },
  },
];

export const DEMO_MATERIALS: CourseMaterial[] = [
  {
    id: "demo-mat-01",
    name: "CS204_Syllabus_Spring_2026.pdf",
    category: "Syllabus",
    size: "1.4 MB",
    uploadedAt: "2026-10-15",
    state: "Ready",
    indexing: "Ready",
  },
  {
    id: "demo-mat-02",
    name: "Lecture_04_Balanced_Trees.pdf",
    category: "Lecture slides",
    size: "3.8 MB",
    uploadedAt: "2026-10-22",
    state: "Ready",
    indexing: "Ready",
  },
  {
    id: "demo-mat-03",
    name: "Assignment_03_Rubric_Guide.pdf",
    category: "Rubric",
    size: "540 KB",
    uploadedAt: "2026-10-28",
    state: "Ready",
    indexing: "Ready",
  },
  {
    id: "demo-mat-04",
    name: "OS_Scheduling_Algorithms_Notes.pdf",
    category: "Notes",
    size: "1.1 MB",
    uploadedAt: "2026-10-20",
    state: "Ready",
    indexing: "Ready",
  },
];
