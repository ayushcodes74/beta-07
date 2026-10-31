import { useEffect, useState } from "react";
import { courseService } from "../services/api";
import type { Course } from "../types/models";

export interface StudentIdentity {
  name: string;
  email: string | null;
}

type NameMap = Record<string, StudentIdentity>;

// One roster lookup per set of courses, shared by every page that shows student names (Overview,
// Submissions, grading, Review queue...), so moving between them doesn't refetch the rosters.
const cache = new Map<string, { names: NameMap | null; promise: Promise<NameMap> }>();

function loadNames(courseKey: string): Promise<NameMap> {
  const hit = cache.get(courseKey);
  if (hit) return hit.promise;
  const promise = Promise.all(courseKey.split(",").map((id) => courseService.getStudents(id).catch(() => []))).then(
    (rosters) => {
      const map: NameMap = {};
      rosters.flat().forEach((student) => {
        map[student.student_id] = { name: student.name || student.email || "Student", email: student.email };
      });
      const entry = cache.get(courseKey);
      if (entry) entry.names = map;
      return map;
    },
  );
  cache.set(courseKey, { names: null, promise });
  return promise;
}

/**
 * Teacher views: student id -> name/email, built from the rosters of the given courses.
 * Submissions only carry student ids, and the app does not load student profiles otherwise.
 * Pass `enabled = false` (e.g. for students) to skip the roster requests.
 */
export function useStudentNames(courses: Course[], enabled = true): NameMap {
  const courseKey = courses.map((course) => course.id).join(",");
  const [names, setNames] = useState<NameMap>(() => (enabled && cache.get(courseKey)?.names) || {});

  useEffect(() => {
    if (!enabled || !courseKey) return;
    let active = true;
    void loadNames(courseKey).then((map) => active && setNames(map));
    return () => {
      active = false;
    };
  }, [courseKey, enabled]);

  return names;
}

/** Forget cached rosters (e.g. after enrolling or removing a student) so names reload next time. */
export function clearStudentNameCache() {
  cache.clear();
}
