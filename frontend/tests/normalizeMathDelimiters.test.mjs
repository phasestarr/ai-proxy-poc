import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkMath from "remark-math";

import { normalizeMathDelimiters } from "../src/utils/normalizeMathDelimiters.ts";

test("normalizes inline and display LaTeX delimiters", () => {
  const markdown = String.raw`Inline \(x^2\).

\[
\frac{a}{b}
\]`;

  assert.equal(
    normalizeMathDelimiters(markdown),
    `Inline $x^2$.

$$
\\frac{a}{b}
$$`,
  );
});

test("leaves existing dollar math and ordinary parentheses unchanged", () => {
  const markdown = "Keep $x$ and $$y$$, plus (ordinary text).";
  assert.equal(normalizeMathDelimiters(markdown), markdown);
});

test("does not normalize delimiters in inline code", () => {
  const markdown = "Use \\(x\\), but show `\\(literal\\)` and ``a \\(literal\\) b``.";
  assert.equal(
    normalizeMathDelimiters(markdown),
    "Use $x$, but show `\\(literal\\)` and ``a \\(literal\\) b``.",
  );
});

test("does not normalize delimiters in backtick or tilde fences", () => {
  const markdown = [
    String.raw`Before \(x\).`,
    "",
    "```text",
    String.raw`\(literal\)`,
    "```",
    "",
    "~~~text",
    String.raw`\[literal\]`,
    "~~~",
    "",
    String.raw`After \(y\).`,
  ].join("\n");

  const expected = [
    "Before $x$.",
    "",
    "```text",
    String.raw`\(literal\)`,
    "```",
    "",
    "~~~text",
    String.raw`\[literal\]`,
    "~~~",
    "",
    "After $y$.",
  ].join("\n");

  assert.equal(normalizeMathDelimiters(markdown), expected);
});

test("does not reinterpret escaped delimiter examples", () => {
  const markdown = String.raw`Literal \\(x\\), math \(y\).`;
  assert.equal(
    normalizeMathDelimiters(markdown),
    String.raw`Literal \\(x\\), math $y$.`,
  );
});

test("an unmatched backtick does not suppress later math", () => {
  const markdown = "Unmatched ` then \\(x\\).";
  assert.equal(normalizeMathDelimiters(markdown), "Unmatched ` then $x$.");
});

test("OpenAI-style delimiters reach KaTeX through the Markdown pipeline", () => {
  const markdown = [
    String.raw`Let \(r=\|\mathbf r\|\).`,
    "",
    String.raw`\[`,
    String.raw`\boxed{\ddot{\mathbf r}=-\frac{\mu}{r^3}\mathbf r.}`,
    String.raw`\]`,
    "",
    "`\\(literal example\\)`",
  ].join("\n");

  const html = renderToStaticMarkup(
    React.createElement(
      ReactMarkdown,
      { remarkPlugins: [remarkMath], rehypePlugins: [rehypeKatex] },
      normalizeMathDelimiters(markdown),
    ),
  );

  assert.match(html, /class="katex"/);
  assert.match(html, /class="katex-display"/);
  assert.match(html, /<code>\\\(literal example\\\)<\/code>/);
});
