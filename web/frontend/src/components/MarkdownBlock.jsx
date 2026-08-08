import ReactMarkdown from "react-markdown";

export default function MarkdownBlock({ text }) {
  if (!text) return null;
  return (
    <div className="markdown-body">
      <ReactMarkdown>{text}</ReactMarkdown>
    </div>
  );
}
