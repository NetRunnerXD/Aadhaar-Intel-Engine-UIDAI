import ReactMarkdown from "react-markdown";

export default function MarkdownBlock({ text }) {
  if (!text) return <div className="muted">No analysis yet.</div>;
  return (
    <div className="markdown-body">
      <ReactMarkdown>{text}</ReactMarkdown>
    </div>
  );
}
