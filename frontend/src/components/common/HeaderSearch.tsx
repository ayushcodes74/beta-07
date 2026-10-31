import { BookOpen, FileText, Search, UserRound, X } from "lucide-react";
import { useId, useMemo, useState, type KeyboardEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAppState } from "../../App";
import { useStudentNames } from "../../lib/useStudentNames";
import { cn } from "../../lib/utils";

interface Result {
  key: string;
  kind: "Course" | "Assignment" | "Student";
  label: string;
  detail: string;
  to: string;
}

const MAX_RESULTS = 8;
const icons = { Course: BookOpen, Assignment: FileText, Student: UserRound };

/**
 * Header search over the signed-in workspace: courses, assignments and (for teachers) students.
 * Results appear as you type; Enter opens the highlighted one.
 */
export function HeaderSearch({ className, autoFocus, onClose }: { className?: string; autoFocus?: boolean; onClose?: () => void }) {
  const { user, courses, assignments, submissions } = useAppState();
  const navigate = useNavigate();
  const listId = useId();
  const isStudent = user?.role === "student";
  const names = useStudentNames(courses, !isStudent);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);

  const results = useMemo<Result[]>(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    const matches = (...fields: (string | undefined | null)[]) => fields.some((field) => field?.toLowerCase().includes(q));
    const courseById = new Map(courses.map((course) => [course.id, course]));
    const found: Result[] = [];

    for (const course of courses) {
      if (!matches(course.name, course.code)) continue;
      found.push({
        key: `c-${course.id}`,
        kind: "Course",
        label: course.name,
        detail: course.code,
        to: isStudent ? "/app/student/assignments" : `/app/courses/${course.id}`,
      });
    }
    for (const assignment of assignments) {
      if (!matches(assignment.title)) continue;
      found.push({
        key: `a-${assignment.id}`,
        kind: "Assignment",
        label: assignment.title,
        detail: courseById.get(assignment.courseId)?.name ?? "Assignment",
        to: isStudent
          ? assignment.submissionType === "MCQ"
            ? `/app/student/assessment/${assignment.id}`
            : `/app/student/submit/${assignment.id}`
          : `/app/assignment/${assignment.id}/edit`,
      });
    }
    if (!isStudent) {
      // A student opens their most recent submission (the place a teacher acts on their work).
      for (const [studentId, identity] of Object.entries(names)) {
        if (!matches(identity.name, identity.email)) continue;
        const latest = submissions
          .filter((item) => item.studentId === studentId)
          .sort((a, b) => Date.parse(b.submittedAt) - Date.parse(a.submittedAt))[0];
        if (!latest) continue;
        const title = assignments.find((a) => a.id === latest.assignmentId)?.title ?? "submission";
        found.push({
          key: `s-${studentId}`,
          kind: "Student",
          label: identity.name,
          detail: `Latest: ${title}`,
          to: `/app/grading/${latest.id}`,
        });
      }
    }
    return found.slice(0, MAX_RESULTS);
  }, [query, courses, assignments, submissions, names, isStudent]);

  const go = (result: Result | undefined) => {
    if (!result) return;
    navigate(result.to);
    setQuery("");
    setOpen(false);
    onClose?.();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown") setHighlight((i) => Math.min(results.length - 1, i + 1));
    else if (event.key === "ArrowUp") setHighlight((i) => Math.max(0, i - 1));
    else if (event.key === "Escape") {
      setOpen(false);
      onClose?.();
    } else return;
    event.preventDefault();
  };

  const showList = open && query.trim().length > 0;

  return (
    <form
      className={cn("search-box header-search", className)}
      role="search"
      onSubmit={(event) => {
        event.preventDefault();
        go(results[highlight]);
      }}
    >
      <Search size={15} aria-hidden="true" />
      <input
        autoFocus={autoFocus}
        value={query}
        onChange={(event) => {
          setQuery(event.target.value);
          setHighlight(0);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 120)} // let a click on a result land first
        onKeyDown={onKeyDown}
        placeholder={isStudent ? "Search courses, assignments..." : "Search courses, assignments, students..."}
        aria-label="Search"
        role="combobox"
        aria-expanded={showList}
        aria-controls={listId}
        aria-activedescendant={showList && results[highlight] ? `${listId}-${highlight}` : undefined}
        autoComplete="off"
      />
      {onClose && (
        <button className="icon-button" type="button" onClick={onClose} aria-label="Close search">
          <X size={14} />
        </button>
      )}
      {showList && (
        <ul className="header-search-results" id={listId} role="listbox">
          {results.length ? (
            results.map((result, index) => {
              const Icon = icons[result.kind];
              return (
                <li
                  key={result.key}
                  id={`${listId}-${index}`}
                  role="option"
                  aria-selected={index === highlight}
                  className={cn(index === highlight && "active")}
                  onMouseEnter={() => setHighlight(index)}
                  onMouseDown={(event) => {
                    event.preventDefault(); // keep focus in the input until we navigate
                    go(result);
                  }}
                >
                  <Icon size={14} aria-hidden="true" />
                  <span>
                    <strong>{result.label}</strong>
                    <small>{result.kind} · {result.detail}</small>
                  </span>
                </li>
              );
            })
          ) : (
            <li className="header-search-empty" role="option" aria-selected={false}>
              No matches for “{query.trim()}”
            </li>
          )}
        </ul>
      )}
    </form>
  );
}
