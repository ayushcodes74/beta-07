import type {
  Assignment,
  Course,
  CourseMaterial,
  Feedback,
  LeaderboardEntry,
  PublishedResult,
  Rubric,
  Submission,
  User,
} from "../types/models";

export const users: User[] = [
  { id: "teacher-alex", name: "Alex Morgan", email: "alex.morgan@university.edu", role: "teacher", initials: "AM" },
  { id: "student-maya", name: "Maya Chen", email: "maya.chen@university.edu", role: "student", initials: "MC" },
  { id: "student-ethan", name: "Ethan Brooks", email: "ethan.brooks@university.edu", role: "student", initials: "EB" },
  { id: "student-sofia", name: "Sofia Patel", email: "sofia.patel@university.edu", role: "student", initials: "SP" },
  { id: "student-noah", name: "Noah Williams", email: "noah.williams@university.edu", role: "student", initials: "NW" },
  { id: "student-amara", name: "Amara Okafor", email: "amara.okafor@university.edu", role: "student", initials: "AO" },
  { id: "student-leo", name: "Leo Fischer", email: "leo.fischer@university.edu", role: "student", initials: "LF" },
];

export const courses: Course[] = [
  { id: "cs204", name: "Data Structures", code: "CS 204", instructor: "Dr. Alex Morgan", students: 42, assignments: 6, activity: 74, average: 86.2 },
  { id: "cs301", name: "Operating Systems", code: "CS 301", instructor: "Dr. Alex Morgan", students: 38, assignments: 5, activity: 62, average: 82.7 },
  { id: "cs220", name: "Database Systems", code: "CS 220", instructor: "Dr. Alex Morgan", students: 46, assignments: 7, activity: 86, average: 88.4 },
  { id: "cs315", name: "Computer Networks", code: "CS 315", instructor: "Dr. Alex Morgan", students: 31, assignments: 4, activity: 54, average: 79.8 },
  { id: "cs410", name: "Software Engineering", code: "CS 410", instructor: "Dr. Alex Morgan", students: 29, assignments: 3, activity: 68, average: 85.1 },
  { id: "math210", name: "Discrete Mathematics", code: "MATH 210", instructor: "Dr. Alex Morgan", students: 32, assignments: 4, activity: 79, average: 83.3 },
];

export const rubrics: Rubric[] = [{
  id: "rubric-bst",
  name: "Data Structures — Standard rubric",
  criteria: [
    { id: "accuracy", name: "Concept accuracy", description: "Core concept is correct and complete.", score: 7, maximum: 8 },
    { id: "method", name: "Method & application", description: "Method is applied appropriately.", score: 4, maximum: 5 },
    { id: "explanation", name: "Explanation", description: "Reasoning is clear and supported.", score: 4, maximum: 5 },
    { id: "presentation", name: "Presentation", description: "Terminology and organization.", score: 2, maximum: 2 },
  ],
}];

export const assignments: Assignment[] = [
  {
    id: "ds-a03",
    courseId: "cs204",
    title: "Data Structures — Assignment 03",
    description: "Explore balanced search trees, traversal strategies, and efficient data structures.",
    dueAt: "2026-10-31T23:59:00",
    totalMarks: 20,
    state: "Published",
    submissionType: "Mixed",
    rubricId: "rubric-bst",
    questions: [
      { id: "q-bst", prompt: "Explain how a balanced binary search tree maintains O(log n) operations. Include one example of a balancing operation.", type: "Subjective", marks: 10, expectedAnswer: "A balanced tree keeps height proportional to log n. AVL or red-black trees use single or double rotations to restore balance after updates." },
      { id: "q-traversal", prompt: "Which traversal visits nodes in ascending order in a binary search tree?", type: "MCQ", marks: 5, expectedAnswer: "In-order traversal", options: ["Pre-order", "In-order", "Post-order", "Level-order"], correctOption: 1 },
      { id: "q-complexity", prompt: "What is the worst-case search complexity of an unbalanced binary search tree?", type: "MCQ", marks: 5, expectedAnswer: "O(n)", options: ["O(1)", "O(log n)", "O(n)", "O(n log n)"], correctOption: 2 },
    ],
  },
  {
    id: "os-a02",
    courseId: "cs301",
    title: "Operating Systems — Assignment 02",
    description: "Reason about process scheduling and concurrency.",
    dueAt: "2026-11-01T23:59:00",
    totalMarks: 25,
    state: "Published",
    submissionType: "PDF",
    rubricId: "rubric-bst",
    questions: [{ id: "q-os", prompt: "Compare preemptive and non-preemptive scheduling.", type: "Subjective", marks: 10, expectedAnswer: "Explain scheduler control, responsiveness, and trade-offs." }],
  },
  {
    id: "ds-q03",
    courseId: "cs204",
    title: "Binary Search Trees — Quiz 03",
    description: "A short check-in on binary search tree properties and traversals.",
    dueAt: "2026-10-28T17:00:00",
    totalMarks: 20,
    state: "Published",
    submissionType: "MCQ",
    rubricId: "rubric-bst",
    questions: [
      { id: "q-quiz-bst", prompt: "Which statement correctly describes the ordering property of a binary search tree?", type: "MCQ", marks: 8, expectedAnswer: "Values in the left subtree are less than the node; values in the right subtree are greater.", options: ["All values are greater than the root", "Left subtree values are smaller; right subtree values are greater", "Every node has exactly two children", "The tree is always complete"], correctOption: 1 },
      { id: "q-quiz-traversal", prompt: "Which traversal visits BST keys in ascending order?", type: "MCQ", marks: 7, expectedAnswer: "In-order traversal", options: ["Pre-order", "In-order", "Post-order", "Level-order"], correctOption: 1 },
      { id: "q-quiz-complexity", prompt: "What is the worst-case search complexity of a degenerate BST with n nodes?", type: "MCQ", marks: 5, expectedAnswer: "O(n)", options: ["O(1)", "O(log n)", "O(n)", "O(n log n)"], correctOption: 2 },
    ],
  },
  {
    id: "db-p01",
    courseId: "cs220",
    title: "Database Systems — Project 01",
    description: "Build and explain a normalized relational schema.",
    dueAt: "2026-11-03T23:59:00",
    totalMarks: 30,
    state: "Published",
    submissionType: "PDF",
    rubricId: "rubric-bst",
    questions: [{ id: "q-db", prompt: "Describe the normalization choices in your schema.", type: "Subjective", marks: 20, expectedAnswer: "Discuss normal forms and relevant dependency constraints." }],
  },
];

const feedback: Feedback = {
  id: "feedback-maya",
  comment: "You explain the balance condition clearly and identify rotations as the key mechanism. A concrete left- or right-rotation example would make the application even stronger.",
  deductions: [{ criterion: "Method & application", reason: "The answer names rotations but does not show a concrete case.", marks: 1 }],
  courseReferences: ["Lecture 04 — Trees", "Course Notes — Binary Search Trees"],
};

const grading = {
  suggestedScore: 15,
  confidence: 0.91,
  reasoning: "The response correctly describes height balance and relates it to logarithmic operations. It identifies rotations as the repair mechanism; the example could be more specific. The proposed deduction follows the rubric's application criterion.",
  rubric: rubrics[0].criteria,
  feedback,
  teacherApproved: false,
};

export const submissions: Submission[] = [
  { id: "sub-maya-quiz-03", studentId: "student-maya", assignmentId: "ds-q03", submittedAt: "2026-10-28T14:18:00", deadline: "2026-10-28T17:00:00", state: "Published", ocr: { confidence: 1, state: "Verified", extractedText: "MCQ responses submitted.", warnings: [], expressions: [] }, grading: { suggestedScore: 18, confidence: 1, reasoning: "Automatically scored against the teacher-approved answer key.", rubric: [], feedback: { ...feedback, id: "feedback-maya-quiz" }, teacherApproved: true }, answer: "MCQ responses submitted." },
  { id: "sub-maya-ds", studentId: "student-maya", assignmentId: "ds-a03", submittedAt: "2026-10-31T09:42:00", deadline: "2026-10-31T23:59:00", state: "Under Review", ocr: { confidence: 0.91, state: "Needs review", extractedText: "A balanced binary search tree maintains its height by ensuring the difference between the heights of its left and right subtrees stays within a small bound. When an insertion makes the tree unbalanced, a rotation is performed to restore balance.", warnings: ["One handwritten word has low recognition confidence."], expressions: ["O(log n)"] }, grading: { ...grading }, answer: "A balanced binary search tree maintains its height by ensuring the difference between the heights of its left and right subtrees stays within a small bound. When an insertion makes the tree unbalanced, a rotation is performed to restore balance.", fileName: "maya_chen_assignment_03.pdf" },
  { id: "sub-ethan-ds", studentId: "student-ethan", assignmentId: "ds-a03", submittedAt: "2026-10-31T09:18:00", deadline: "2026-10-31T23:59:00", state: "Under Review", ocr: { confidence: 0.98, state: "High confidence", extractedText: "Balanced search trees maintain logarithmic height through rotations.", warnings: [], expressions: ["O(log n)"] }, grading: { ...grading, suggestedScore: 17, confidence: 0.96, feedback: { ...feedback, id: "feedback-ethan" } }, answer: "Balanced search trees maintain logarithmic height through rotations.", fileName: "ethan_brooks_assignment_03.pdf" },
  { id: "sub-sofia-os", studentId: "student-sofia", assignmentId: "os-a02", submittedAt: "2026-11-02T00:12:00", deadline: "2026-11-01T23:59:00", state: "Late Submission", ocr: { confidence: 0.68, state: "Low confidence", extractedText: "A preemptive scheduler can interrupt a running process...", warnings: ["Handwritten lines overlap near the bottom of page 2."], expressions: ["T = 2 × quantum"] }, answer: "A preemptive scheduler can interrupt a running process...", fileName: "sofia_patell_os02.pdf" },
  { id: "sub-noah-db", studentId: "student-noah", assignmentId: "db-p01", submittedAt: "2026-10-30T16:27:00", deadline: "2026-11-03T23:59:00", state: "Submitted", ocr: { confidence: 0.99, state: "High confidence", extractedText: "The schema separates enrollment from student records.", warnings: [], expressions: [] }, answer: "The schema separates enrollment from student records.", fileName: "noah_williams_project_01.pdf" },
  { id: "sub-amara-ds", studentId: "student-amara", assignmentId: "ds-a03", submittedAt: "2026-10-30T14:10:00", deadline: "2026-10-31T23:59:00", state: "Published", ocr: { confidence: 0.99, state: "Verified", extractedText: "An AVL tree rebalances with rotations.", warnings: [], expressions: ["O(log n)"] }, grading: { ...grading, suggestedScore: 16, teacherApproved: true }, answer: "An AVL tree rebalances with rotations.", fileName: "amara_okafor_a03.pdf" },
  { id: "sub-leo-cn", studentId: "student-leo", assignmentId: "ds-a03", submittedAt: "2026-10-26T10:34:00", deadline: "2026-10-27T23:59:00", state: "Submitted", ocr: { confidence: 0.73, state: "Needs review", extractedText: "The tree height affects... [uncertain]", warnings: ["Page 3 appears rotated."], expressions: [] }, answer: "The tree height affects...", fileName: "leo_fischer_quiz_04.pdf" },
];

export const materials: CourseMaterial[] = [
  { id: "mat-syllabus", name: "CS204_Course_Syllabus_2026.pdf", category: "Syllabus", size: "1.8 MB", uploadedAt: "2026-10-18", state: "Ready", indexing: "Ready" },
  { id: "mat-rubric", name: "Assignment_03_Grading_Rubric.pdf", category: "Rubric", size: "624 KB", uploadedAt: "2026-10-24", state: "Ready", indexing: "Ready" },
  { id: "mat-slides", name: "Week_07_Trees_and_Graphs.pptx", category: "Lecture slides", size: "4.2 MB", uploadedAt: "2026-10-22", state: "Processing", indexing: "Processing" },
  { id: "mat-notes", name: "Reference_Notes_Binary_Trees.pdf", category: "Notes", size: "982 KB", uploadedAt: "2026-10-19", state: "Needs Review", indexing: "Needs Review" },
  { id: "mat-rulebook", name: "Course_Rulebook.pdf", category: "Rulebook", size: "746 KB", uploadedAt: "2026-10-16", state: "Ready", indexing: "Ready" },
];

export const publishedResults: PublishedResult[] = [{
  id: "result-maya-quiz",
  submissionId: "sub-maya-quiz-03",
  publishedAt: "2026-10-28",
  score: 18,
  maximum: 20,
  feedback,
  questionBreakdown: [
    { question: "Explain a binary search tree.", earned: 8, maximum: 8, reason: "Accurate definition with clear ordering properties." },
    { question: "Describe an in-order traversal.", earned: 5, maximum: 5, reason: "All nodes are visited in the correct order." },
    { question: "Give a balancing example.", earned: 5, maximum: 7, reason: "Correctly names rotations; a concrete case would strengthen the example." },
  ],
}];

export const leaderboard: LeaderboardEntry[] = [
  { rank: 1, studentId: "student-maya", score: 96, assignmentsCompleted: 12, trend: "Improving" },
  { rank: 2, studentId: "student-ethan", score: 94, assignmentsCompleted: 12, trend: "Steady" },
  { rank: 3, studentId: "student-sofia", score: 92, assignmentsCompleted: 11, trend: "Improving" },
  { rank: 4, studentId: "student-amara", score: 90, assignmentsCompleted: 11, trend: "Steady" },
  { rank: 5, studentId: "student-noah", score: 88, assignmentsCompleted: 10, trend: "Improving" },
  { rank: 6, studentId: "student-leo", score: 85, assignmentsCompleted: 9, trend: "Needs support" },
];
