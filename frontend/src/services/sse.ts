export type SseMessage = {
  event: string;
  data: string;
};

export async function readSseStream(
  stream: ReadableStream<Uint8Array>,
  onMessage: (message: SseMessage) => void | Promise<void>,
): Promise<void> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
      buffer = normalizeLineEndings(buffer);

      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";

      for (const frame of frames) {
        const message = parseSseFrame(frame);
        if (message) {
          await onMessage(message);
        }
      }

      if (done) {
        const flushed = decoder.decode();
        if (flushed) {
          buffer += normalizeLineEndings(flushed);
        }

        if (buffer.trim().length > 0) {
          const message = parseSseFrame(buffer);
          if (message) {
            await onMessage(message);
          }
        }
        return;
      }
    }
  } finally {
    reader.releaseLock();
  }
}

function parseSseFrame(frame: string): SseMessage | null {
  let eventName = "message";
  const dataLines: string[] = [];

  for (const line of frame.split("\n")) {
    if (!line || line.startsWith(":")) {
      continue;
    }

    if (line.startsWith("event:")) {
      eventName = line.slice("event:".length).trim();
      continue;
    }

    if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trimStart());
    }
  }

  if (dataLines.length === 0) {
    return null;
  }

  return {
    event: eventName,
    data: dataLines.join("\n"),
  };
}

function normalizeLineEndings(value: string): string {
  return value.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
}
