import { Fragment, type ReactNode } from "react";

/**
 * AI feedback is written in light markdown ("### Heading", "**bold**", "- item"). Rendered as plain
 * text it showed raw symbols to students, so this renders that small subset as React elements
 * (never as HTML, so nothing in the text can inject markup).
 */

/** Removes the AI summary heading, whose "(Score: 3.0/20 — 15%)" goes stale once the teacher sets a score. */
export function cleanAiFeedback(text: string | null | undefined): string {
  return (text ?? "")
    .replace(/^[ \t]*#{0,6}[ \t]*Overall Assignment Feedback\b[^\n]*\n?/gim, "")
    .trim();
}

function inline(text: string): ReactNode[] {
  // **bold** / __bold__; anything else stays literal text.
  return text.split(/(\*\*[^*]+\*\*|__[^_]+__)/g).map((part, index) =>
    /^(\*\*|__).+\1$/.test(part) ? <strong key={index}>{part.slice(2, -2)}</strong> : <Fragment key={index}>{part}</Fragment>
  );
}

export function FormattedText({ text, className }: { text: string; className?: string }) {
  const blocks: ReactNode[] = [];
  let list: string[] = [];
  const flushList = () => {
    if (list.length) {
      blocks.push(
        <ul key={`list-${blocks.length}`}>
          {list.map((item, index) => <li key={index}>{inline(item)}</li>)}
        </ul>
      );
      list = [];
    }
  };

  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    const bullet = line.match(/^[-*•]\s+(.*)$/);
    if (bullet) {
      list.push(bullet[1]);
      continue;
    }
    flushList();
    if (!line) continue;
    const heading = line.match(/^#{1,6}\s+(.*)$/);
    blocks.push(
      heading ? (
        <p key={blocks.length} className="formatted-text-heading">{inline(heading[1])}</p>
      ) : (
        <p key={blocks.length}>{inline(line)}</p>
      )
    );
  }
  flushList();

  return <div className={["formatted-text", className].filter(Boolean).join(" ")}>{blocks}</div>;
}
