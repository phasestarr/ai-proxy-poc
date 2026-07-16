type Fence = {
  character: "`" | "~";
  length: number;
};

const OPENING_FENCE = /^ {0,3}(`{3,}|~{3,})(.*)$/;

function getLine(markdown: string, start: number) {
  const newline = markdown.indexOf("\n", start);
  const end = newline === -1 ? markdown.length : newline + 1;
  const contentEnd = newline === -1 ? end : newline;
  const content = markdown.slice(start, contentEnd).replace(/\r$/, "");

  return { content, end };
}

function getOpeningFence(line: string): Fence | null {
  const match = OPENING_FENCE.exec(line);
  if (!match) {
    return null;
  }

  const marker = match[1];
  const character = marker[0] as Fence["character"];
  const info = match[2];

  // CommonMark does not allow backticks in a backtick fence's info string.
  if (character === "`" && info.includes("`")) {
    return null;
  }

  return { character, length: marker.length };
}

function isClosingFence(line: string, fence: Fence) {
  const trimmed = line.startsWith("   ")
    ? line.slice(3)
    : line.startsWith("  ")
      ? line.slice(2)
      : line.startsWith(" ")
        ? line.slice(1)
        : line;

  let markerLength = 0;
  while (trimmed[markerLength] === fence.character) {
    markerLength += 1;
  }

  return (
    markerLength >= fence.length &&
    /^[\t ]*$/.test(trimmed.slice(markerLength))
  );
}

function countRun(markdown: string, start: number, character: string) {
  let end = start;
  while (markdown[end] === character) {
    end += 1;
  }
  return end - start;
}

function hasClosingBacktickRun(markdown: string, start: number, length: number) {
  let cursor = start;
  while (cursor < markdown.length) {
    const next = markdown.indexOf("`", cursor);
    if (next === -1) {
      return false;
    }

    const runLength = countRun(markdown, next, "`");
    if (runLength === length) {
      return true;
    }
    cursor = next + runLength;
  }

  return false;
}

function isEscapedBackslash(markdown: string, index: number) {
  let precedingBackslashes = 0;
  for (let cursor = index - 1; cursor >= 0 && markdown[cursor] === "\\"; cursor -= 1) {
    precedingBackslashes += 1;
  }
  return precedingBackslashes % 2 === 1;
}

/**
 * Converts LaTeX-style math delimiters emitted by some LLMs into the dollar
 * delimiters understood by remark-math. Markdown code spans and fences are
 * deliberately preserved as literal examples.
 */
export function normalizeMathDelimiters(markdown: string) {
  let normalized = "";
  let cursor = 0;
  let lineStart = true;
  let fence: Fence | null = null;
  let inlineCodeTicks = 0;

  while (cursor < markdown.length) {
    if (lineStart && inlineCodeTicks === 0) {
      const line = getLine(markdown, cursor);

      if (fence) {
        normalized += markdown.slice(cursor, line.end);
        if (isClosingFence(line.content, fence)) {
          fence = null;
        }
        cursor = line.end;
        lineStart = true;
        continue;
      }

      const openingFence = getOpeningFence(line.content);
      if (openingFence) {
        fence = openingFence;
        normalized += markdown.slice(cursor, line.end);
        cursor = line.end;
        lineStart = true;
        continue;
      }
    }

    const character = markdown[cursor];

    if (character === "\n") {
      normalized += character;
      cursor += 1;
      lineStart = true;
      continue;
    }

    lineStart = false;

    if (character === "`") {
      const runLength = countRun(markdown, cursor, "`");
      normalized += markdown.slice(cursor, cursor + runLength);

      if (inlineCodeTicks === runLength) {
        inlineCodeTicks = 0;
      } else if (
        inlineCodeTicks === 0 &&
        hasClosingBacktickRun(markdown, cursor + runLength, runLength)
      ) {
        inlineCodeTicks = runLength;
      }

      cursor += runLength;
      continue;
    }

    if (
      inlineCodeTicks === 0 &&
      character === "\\" &&
      !isEscapedBackslash(markdown, cursor)
    ) {
      const delimiter = markdown[cursor + 1];
      if (delimiter === "(" || delimiter === ")") {
        normalized += "$";
        cursor += 2;
        continue;
      }
      if (delimiter === "[" || delimiter === "]") {
        normalized += "$$";
        cursor += 2;
        continue;
      }
    }

    normalized += character;
    cursor += 1;
  }

  return normalized;
}
