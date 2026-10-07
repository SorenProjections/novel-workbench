export type RunPayload = Record<string, unknown>;

export function isTerminalEvent(name: string): boolean {
  return name === 'result' || name === 'error' || name === 'cancelled';
}

export function attachRunEvents(
  stream: EventSource, names: readonly string[],
  onEvent: (name: string, payload: RunPayload) => void,
  onDisconnect: () => void,
): void {
  let cursor = 0;
  for (const name of names) {
    stream.addEventListener(name, (raw) => {
      // A network error has no server payload. EventSource will reconnect itself.
      if (!(raw instanceof MessageEvent)) return;
      let data: RunPayload;
      try {
        const parsed: unknown = JSON.parse(String(raw.data));
        data = parsed && typeof parsed === 'object' ? parsed as RunPayload : { message: raw.data };
      } catch { data = { message: raw.data }; }
      const sequence = Number(data.sequence || 0);
      if (sequence && sequence <= cursor) return;
      cursor = Math.max(cursor, sequence);
      onEvent(name, data);
    });
  }
  stream.onerror = onDisconnect;
}
