import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

type MarkdownMessageProps = {
  content: string;
  className?: string;
  enableMarkdown?: boolean;
  enableLatex?: boolean;
};

export default function MarkdownMessage({
  content,
  className,
  enableMarkdown = true,
  enableLatex = true,
}: MarkdownMessageProps) {
  if (!enableMarkdown) {
    return (
      <div className={className}>
        <p className="chat-plain-text">{content}</p>
      </div>
    );
  }

  const remarkPlugins = enableLatex
    ? [remarkGfm, remarkBreaks, remarkMath]
    : [remarkGfm, remarkBreaks];

  return (
    <div className={className}>
      <ReactMarkdown
        components={{
          a({ children, href, ...props }) {
            return (
              <a {...props} href={href} rel="noreferrer" target="_blank">
                {children}
              </a>
            );
          },
        }}
        rehypePlugins={enableLatex ? [rehypeKatex] : undefined}
        remarkPlugins={remarkPlugins}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
