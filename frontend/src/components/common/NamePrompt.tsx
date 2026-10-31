import { useState, type FormEvent } from "react";
import { UserRound } from "lucide-react";
import { Button } from "../ui";
import { updateDisplayName } from "../../services/auth";
import { extractErrorMessage } from "../../services/api";

/** Asks a signed-in user without a saved name for one (shown on rosters and the course leaderboard). */
export function NamePrompt({ suggestion, onSaved }: { suggestion: string; onSaved: () => Promise<unknown> }) {
  const [name, setName] = useState(suggestion);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    setError("");
    try {
      await updateDisplayName(name);
      await onSaved();
    } catch (reason) {
      setError(extractErrorMessage(reason, "Could not save your name."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <form className="name-prompt" onSubmit={(event) => void save(event)}>
      <UserRound size={16} aria-hidden="true" />
      <label htmlFor="name-prompt-input">
        <strong>Add your name.</strong> Teachers and the course leaderboard show it instead of “Student”.
      </label>
      <input
        id="name-prompt-input"
        value={name}
        maxLength={100}
        onChange={(event) => setName(event.target.value)}
        placeholder="Your full name"
      />
      <Button size="sm" type="submit" disabled={saving || !name.trim()}>
        {saving ? "Saving…" : "Save name"}
      </Button>
      {error && <span className="name-prompt-error" role="alert">{error}</span>}
    </form>
  );
}
