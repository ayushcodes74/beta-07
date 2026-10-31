import type { User } from "../types/models";

const DEMO_ROLE_KEY = "tg_demo_role";

export function getDemoUser(): User {
  const role = sessionStorage.getItem(DEMO_ROLE_KEY) === "student" ? "student" : "teacher";
  return role === "student"
    ? {
        id: "demo-student",
        name: "Demo Student",
        email: "student.demo@trustgrade.local",
        role,
        initials: "DS",
      }
    : {
        id: "demo-teacher",
        name: "Demo Teacher",
        email: "teacher.demo@trustgrade.local",
        role,
        initials: "DT",
      };
}

export function clearDemoSession(): void {
  sessionStorage.removeItem(DEMO_ROLE_KEY);
}
