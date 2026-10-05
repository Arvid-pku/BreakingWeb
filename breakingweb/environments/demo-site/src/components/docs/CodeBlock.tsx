"use client";

import { useEffect, useState, useCallback } from "react";
import { codeToHtml } from "shiki";
import { useTheme } from "@/components/ui/ThemeProvider";

interface CodeBlockProps {
  code: string;
  language?: string;
  filename?: string;
}

export function CodeBlock({ code, language = "bash", filename }: CodeBlockProps) {
  const { theme } = useTheme();
  const [html, setHtml] = useState<string>("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    codeToHtml(code.trim(), {
      lang: language,
      theme: theme === "dark" ? "github-dark-default" : "github-light-default",
    }).then(setHtml);
  }, [code, language, theme]);

  const copy = useCallback(() => {
    navigator.clipboard.writeText(code.trim());
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }, [code]);

  return (
    <div className="border border-[var(--border)] rounded-xl overflow-hidden mb-6 relative group">
      {filename && (
        <div className="px-4 py-2.5 bg-[var(--surface-raised)] border-b border-[var(--border)] text-[12px] font-mono text-[var(--text-tertiary)]">
          {filename}
        </div>
      )}
      <div className="relative">
        <button
          onClick={copy}
          className="absolute top-3 right-3 z-10 px-2 py-1 rounded-md text-[11px] font-mono bg-[var(--surface)] border border-[var(--border)] text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] opacity-0 group-hover:opacity-100 transition-opacity duration-150"
        >
          {copied ? "Copied!" : "Copy"}
        </button>
        {html ? (
          <div
            className="overflow-x-auto text-[13px] leading-[1.7] [&_pre]:!bg-transparent [&_pre]:p-5 [&_pre]:m-0 [&_code]:!bg-transparent bg-[var(--surface-raised)]"
            dangerouslySetInnerHTML={{ __html: html }}
          />
        ) : (
          <pre className="p-5 text-[13px] leading-[1.7] text-[var(--text-secondary)] overflow-x-auto bg-[var(--surface-raised)]">
            <code>{code.trim()}</code>
          </pre>
        )}
      </div>
    </div>
  );
}
