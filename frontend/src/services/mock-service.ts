import type { Assignment, Course, CourseMaterial, Submission } from "../types/models";
import { assignments, courses, materials, submissions } from "../lib/mock-data";

const clone = <T>(value: T): T => structuredClone(value);

export const mockService = {
  async getCourses(): Promise<Course[]> { return clone(courses); },
  async getAssignments(): Promise<Assignment[]> { return clone(assignments); },
  async getSubmissions(): Promise<Submission[]> { return clone(submissions); },
  async getMaterials(): Promise<CourseMaterial[]> { return clone(materials); },
  async generateQuestions(count: number, type: "Subjective" | "MCQ" | "Mixed", difficulty: string = "Mixed"): Promise<Assignment["questions"]> {
    const promptsByDifficulty: Record<string, string[]> = {
      Easy: [
        "State the ordering property of a binary search tree.",
        "Which traversal visits BST keys in ascending order?",
        "What does O(log n) describe in a balanced search tree?",
        "Name one rotation used to rebalance an AVL tree.",
        "What is the worst-case search complexity of a degenerate BST?",
        "Which child subtree contains keys smaller than a node?",
        "What information does a node's balance factor represent?",
        "Define an in-order traversal in one sentence.",
        "How many children can a binary tree node have?",
        "What is the main purpose of balancing a search tree?",
      ],
      Medium: [
        "Describe how an AVL tree restores balance after an insertion.",
        "Compare breadth-first and depth-first traversal and give an appropriate use case.",
        "Explain how tree height affects search complexity.",
        "Describe one trade-off between a hash table and a balanced search tree.",
        "Give an example of a rotation that restores balance in a search tree.",
        "Identify the traversal that visits BST keys in ascending order.",
        "When might breadth-first traversal be preferable?",
        "Explain why balanced tree operations remain logarithmic.",
        "Describe the worst-case behavior of an unbalanced search tree.",
        "How do rotations preserve ordering while restoring balance?",
      ],
      Hard: [
        "Analyze how repeated sorted insertions affect an unbalanced BST, then justify a balancing strategy.",
        "Compare AVL and red-black tree guarantees and explain which workload may favor each.",
        "Prove the relationship between balanced tree height and logarithmic search cost.",
        "Evaluate the impact of a double rotation on both ordering invariants and subtree height.",
        "Design a test case that distinguishes balanced from degenerate BST search behavior.",
        "Defend a choice between an ordered tree and hash table for range-query-heavy workloads.",
        "Explain how a rotation can preserve the in-order sequence while changing tree height.",
        "Trace the balance factors that lead to an AVL left-right rotation.",
        "Assess how insertion order affects runtime without self-balancing.",
        "Propose evidence to verify that a tree rebalancing implementation is correct.",
      ],
    };
    const prompts = promptsByDifficulty[difficulty] ?? promptsByDifficulty.Medium;
    return prompts.slice(0, count).map((prompt, index) => {
      const questionType = type === "Mixed" ? (index % 2 ? "MCQ" : "Subjective") : type;
      return {
        id: `draft-${crypto.randomUUID()}`,
        prompt,
        type: questionType,
        marks: questionType === "MCQ" ? 2 : 5,
        expectedAnswer: "Draft guidance for teacher review. Edit and verify against course materials.",
        ...(questionType === "MCQ" ? { options: ["In-order", "Pre-order", "Post-order", "Level-order"], correctOption: 0 } : {}),
      };
    });
  },
};

export type { Assignment, Course, CourseMaterial, Submission };
