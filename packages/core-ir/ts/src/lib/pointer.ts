/** RFC 6901 JSON Pointer helpers. */

export function escapePointerToken(token: string): string {
  return token.replace(/~/g, "~0").replace(/\//g, "~1");
}

export function unescapePointerToken(token: string): string {
  return token.replace(/~1/g, "/").replace(/~0/g, "~");
}

/** Split a JSON Pointer into unescaped reference tokens. `""` is the root. */
export function parsePointer(pointer: string): string[] {
  if (pointer === "") return [];
  if (!pointer.startsWith("/")) {
    throw new Error(`Invalid JSON Pointer (must start with "/"): ${pointer}`);
  }
  return pointer
    .slice(1)
    .split("/")
    .map((token) => unescapePointerToken(token));
}

/** Join a base pointer with relative tokens, escaping each token. */
export function joinPointer(base: string, ...tokens: string[]): string {
  let out = base;
  for (const token of tokens) {
    out += `/${escapePointerToken(token)}`;
  }
  return out;
}

/**
 * Resolve `pointer` against a document. Returns `undefined` when the path does not
 * exist. The generic `T` is a convenience for callers who know the shape at a path.
 */
export function getAt<T = unknown>(root: unknown, pointer: string): T | undefined {
  const tokens = parsePointer(pointer);
  let current: unknown = root;
  for (const token of tokens) {
    if (current === null || typeof current !== "object") return undefined;
    if (Array.isArray(current)) {
      const index = token === "-" ? current.length : Number(token);
      if (!Number.isInteger(index) || index < 0 || index >= current.length) return undefined;
      current = current[index];
    } else {
      current = (current as Record<string, unknown>)[token];
    }
  }
  return current as T | undefined;
}
