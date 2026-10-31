import { useEffect, useState } from "react";
import { courseService } from "../services/api";
import type { Course } from "../types/models";

export interface StudentIdentity {
  name: string;
  email: string | null;
}

/**
 * Teacher views: student id -> name/email, built from the rosters of the given courses.
 * Submissions only carry student ids, and the app does not load student profiles otherwise.
 * Pass `enabled = false` (e.g. for students) to skip the roster requests.
 */
export function useStudentNames(courses: Course[], enabled = true): Record<string, StudentIdentity> {
  const [names, setNames] = useState<Record<string, StudentIdentity>>({});
  const courseKey = courses.map((course) => course.id).join(",");

  useEffect(() => {
    if (!enabled || !courseKey) return;
    let active = true;
    Promise.all(courseKey.split(",").map((id) => courseService.getStudents(id).catch(() => []))).then((rosters) => {
      if (!active) return;
      const map: Record<string, StudentIdentity> = {};
      rosters.flat().forEach((student) => {
        map[student.student_id] = { name: student.name || student.email || "Student", email: student.email };
      });
      setNames(map);
    });
    return () => {
      active = false;
    };
  }, [courseKey, enabled]);

  return names;
}
