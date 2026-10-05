"use client";

import { useMemo } from "react";
import katex from "katex";
import "katex/dist/katex.min.css";

interface LaTeXProps {
  children: string;
  inline?: boolean;
}

export function LaTeX({ children, inline = false }: LaTeXProps) {
  const html = useMemo(() => {
    try {
      return katex.renderToString(children, {
        displayMode: !inline,
        throwOnError: false,
      });
    } catch {
      return children;
    }
  }, [children, inline]);

  if (inline) {
    return <span dangerouslySetInnerHTML={{ __html: html }} />;
  }

  return (
    <div
      className="my-6 overflow-x-auto"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
