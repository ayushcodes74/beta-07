import { Award, ExternalLink, Lightbulb } from "lucide-react";
import { Badge } from "../ui";
import type { BackendAlternativeMethod } from "../../services/api";
import { formatMarks } from "../../lib/grades";

/** A bonus the teacher is about to award on one question (null = none). */
export interface BonusDraft {
  marks: number;
  reason: string;
}

const SEARCH_NOTE: Record<BackendAlternativeMethod["search_status"], string | null> = {
  found: null,
  no_results: "No web sources were found for this method. Check the working yourself.",
  unavailable: "The web search was unavailable, so no sources are shown. Check the working yourself.",
  not_configured: "The web check is off (no TinyFish API key on the server), so no sources are shown.",
  not_searched: null,
};

export const defaultBonusReason = (method: BackendAlternativeMethod) =>
  `Correct answer using ${method.method_name || "a method"}, beyond what the course taught.`;

/**
 * Teacher-only card on a question the student answered with a method the course did not teach.
 * Shows the AI's step check, web sources for the method (TinyFish), and lets the teacher award
 * bonus marks on this question. Nothing is applied until the grade is published.
 */
export function AlternativeMethodCard({
  method,
  bonus,
  onBonusChange,
  disabled = false,
}: {
  method: BackendAlternativeMethod;
  bonus: BonusDraft | null;
  onBonusChange: (bonus: BonusDraft | null) => void;
  disabled?: boolean;
}) {
  const valid = method.approach === "alternative_valid";
  const cap = method.max_bonus;
  const bonusInvalid = bonus !== null && (!(bonus.marks > 0) || bonus.marks > cap + 1e-9);
  const note = SEARCH_NOTE[method.search_status];

  return (
    <div
      className="alt-method-card"
      style={{
        marginTop: 10,
        padding: "12px 14px",
        borderRadius: 12,
        border: `1px solid ${valid ? "#BFD8C3" : "var(--line)"}`,
        background: valid ? "#F3F8F1" : "var(--surface-soft)",
        display: "grid",
        gap: 8,
        fontSize: 12.5,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <Lightbulb size={15} aria-hidden="true" style={{ color: valid ? "#2E7D4F" : "var(--muted)" }} />
        <strong style={{ color: "var(--ink)" }}>
          {valid
            ? "Correct, using a method not taught in this course"
            : method.approach === "alternative_invalid"
              ? "A different method, but the working has errors"
              : "Possibly a different method (not enough working to tell)"}
        </strong>
        <Badge tone={valid ? "sage" : method.approach === "alternative_invalid" ? "rose" : "gold"}>
          {valid ? "Valid alternative" : method.approach === "alternative_invalid" ? "Invalid" : "Unclear"}
        </Badge>
      </div>

      {(method.method_name || method.taught_method) && (
        <p style={{ margin: 0, color: "var(--muted)" }}>
          {method.method_name && <>Student used <b style={{ color: "var(--ink)" }}>{method.method_name}</b></>}
          {method.method_name && method.taught_method && "; "}
          {method.taught_method && <>the course taught <b style={{ color: "var(--ink)" }}>{method.taught_method}</b></>}.
        </p>
      )}
      {method.explanation && <p style={{ margin: 0, color: "var(--ink)" }}>{method.explanation}</p>}

      {valid && (
        <div>
          <span style={{ fontSize: 11.5, fontWeight: 600, color: "var(--muted)" }}>Web sources for this method</span>
          {method.sources.length > 0 ? (
            <ul style={{ margin: "4px 0 0", paddingLeft: 0, listStyle: "none", display: "grid", gap: 6 }}>
              {method.sources.map((source) => (
                <li key={source.url}>
                  <a href={source.url} target="_blank" rel="noopener noreferrer nofollow" style={{ display: "inline-flex", gap: 5, alignItems: "center", fontWeight: 600, color: "var(--forest)" }}>
                    {source.title}
                    <ExternalLink size={12} aria-hidden="true" />
                  </a>
                  {source.site_name && <small style={{ color: "var(--faint)" }}> · {source.site_name}</small>}
                  {source.snippet && <div style={{ color: "var(--muted)", marginTop: 1 }}>{source.snippet}</div>}
                </li>
              ))}
            </ul>
          ) : (
            note && <p style={{ margin: "4px 0 0", color: "var(--muted)" }}>{note}</p>
          )}
          <small style={{ display: "block", marginTop: 6, color: "var(--faint)" }}>
            Sources show the method is a recognised one; correctness comes from checking the student&apos;s steps. If the
            answer matches a source word for word, check the integrity review before rewarding it.
          </small>
        </div>
      )}

      {valid && (
        <div style={{ display: "grid", gap: 6, paddingTop: 8, borderTop: "1px dashed var(--line)" }}>
          <label style={{ display: "inline-flex", alignItems: "center", gap: 8, fontWeight: 600, color: "var(--ink)" }}>
            <input
              type="checkbox"
              checked={bonus !== null}
              disabled={disabled || cap <= 0}
              onChange={(event) =>
                onBonusChange(
                  event.target.checked
                    ? { marks: method.suggested_bonus > 0 ? method.suggested_bonus : Math.min(0.5, cap), reason: defaultBonusReason(method) }
                    : null,
                )
              }
            />
            <Award size={14} aria-hidden="true" />
            Award bonus marks on this question
            {method.suggested_bonus > 0 && (
              <small style={{ fontWeight: 500, color: "var(--muted)" }}>(suggested +{formatMarks(method.suggested_bonus)})</small>
            )}
          </label>
          {bonus !== null && (
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                +
                <input
                  className="field-input"
                  type="number"
                  min={0.5}
                  max={cap}
                  step={0.5}
                  value={Number.isFinite(bonus.marks) ? bonus.marks : ""}
                  disabled={disabled}
                  aria-label="Bonus marks"
                  aria-invalid={bonusInvalid}
                  onChange={(event) => onBonusChange({ ...bonus, marks: Number.parseFloat(event.target.value) })}
                  style={{ width: 72 }}
                />
                <small style={{ color: "var(--muted)" }}>max {formatMarks(cap)}</small>
              </span>
              <input
                className="field-input"
                value={bonus.reason}
                maxLength={500}
                disabled={disabled}
                aria-label="Reason shown to the student"
                placeholder="Reason shown to the student"
                onChange={(event) => onBonusChange({ ...bonus, reason: event.target.value })}
                style={{ flex: "1 1 220px", minWidth: 0 }}
              />
            </div>
          )}
          {bonusInvalid && (
            <small role="alert" style={{ color: "#B42318" }}>Bonus must be more than 0 and at most {formatMarks(cap)} marks.</small>
          )}
        </div>
      )}
    </div>
  );
}
