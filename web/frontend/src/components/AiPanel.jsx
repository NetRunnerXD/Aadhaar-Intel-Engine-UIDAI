import { useState } from "react";
import { Brain, Loader2, Sparkles } from "lucide-react";
import MarkdownBlock from "./MarkdownBlock";

/**
 * Shared AI analysis panel.
 * @param {object} props
 * @param {string} props.text
 * @param {() => void | Promise<void>} props.onGenerate
 * @param {boolean} [props.compact]
 * @param {string} [props.className]
 * @param {string} [props.emptyText]
 */
export default function AiPanel({
  text = "",
  onGenerate,
  compact = false,
  className = "",
  emptyText = "Generate an insight for the current view.",
}) {
  const [busy, setBusy] = useState(false);
  const analyzing = busy || text === "Analyzing..." || text === "Analyzing…";
  const hasContent = Boolean(text) && !analyzing;

  const run = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await onGenerate?.();
    } finally {
      setBusy(false);
    }
  };

  return (
    <article className={`ai-panel ${compact ? "ai-panel--compact" : ""} ${className}`.trim()}>
      <div className="ai-panel__head">
        <div className="ai-panel__brand">
          <span className="ai-panel__icon" aria-hidden>
            <Sparkles size={16} />
          </span>
          <h3>AI analysis</h3>
        </div>
        <button type="button" className="btn btn-primary btn-sm" onClick={run} disabled={analyzing}>
          {analyzing ? <Loader2 size={14} className="spin" /> : <Brain size={14} />}
          {analyzing ? "Analyzing…" : hasContent ? "Regenerate" : "Generate"}
        </button>
      </div>

      <div className={`ai-panel__body ${hasContent ? "has-content" : ""} ${analyzing ? "is-loading" : ""}`}>
        {analyzing ? (
          <div className="ai-panel__loading">
            <div className="ai-panel__pulse" />
            <span>Analyzing current data…</span>
          </div>
        ) : hasContent ? (
          <div className="ai-panel__scroll">
            <MarkdownBlock text={text} />
          </div>
        ) : (
          <div className="ai-panel__empty">
            <Brain size={26} strokeWidth={1.4} />
            <p>{emptyText}</p>
            <button type="button" className="btn btn-ghost btn-sm" onClick={run}>
              Generate
            </button>
          </div>
        )}
      </div>
    </article>
  );
}
