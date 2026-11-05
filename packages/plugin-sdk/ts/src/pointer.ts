/**
 * RFC 6901 JSON Pointer helpers used by the plugin SDK.
 *
 * The SDK must be self-contained (third parties install `@atomc/plugin-sdk` without
 * `@atomc/core-ir`), so the pointer utilities are duplicated here on purpose.
 */

/** Error thrown when a string is not a valid RFC 6901 JSON Pointer. */
export class JsonPointerError extends Error {
  readonly pointer: string;

  constructor(pointer: string) {
    super(`Invalid JSON Pointer: ${JSON.stringify(pointer)}`);
    this.name = "JsonPointerError";
    this.pointer = pointer;
  }
}

const INVALID_ESCAPE = /~(?![01])/;

/**
 * Anchored regex source matching a valid RFC 6901 JSON Pointer (empty, or `/`-separated
 * tokens where `~` only appears as `~0`/`~1`). Exported for the manifest JSON Schema.
 */
export const JSON_POINTER_PATTERN = "^(?:/(?:[^~/]|~[01])*)*$";

/** True when `pointer` is a syntactically valid RFC 6901 JSON Pointer. */
export function isValidPointer(pointer: string): boolean {
  if (pointer === "") return true;
  if (!pointer.startsWith("/")) return false;
  const tokens = pointer.slice(1).split("/");
  return tokens.every((token) => !INVALID_ESCAPE.test(token));
}

/** Escape a single JSON Pointer reference token per RFC 6901 (`~` → `~0`, `/` → `~1`). */
export function escapePointerToken(token: string): string {
  return token.replace(/~/g, "~0").replace(/\//g, "~1");
}

/** Unescape a single JSON Pointer reference token per RFC 6901. */
export function unescapePointerToken(token: string): string {
  return token.replace(/~1/g, "/").replace(/~0/g, "~");
}

/**
 * Parse a JSON Pointer into its decoded reference tokens.
 * The empty pointer (whole document) parses to `[]`.
 */
export function parsePointer(pointer: string): string[] {
  if (!isValidPointer(pointer)) throw new JsonPointerError(pointer);
  if (pointer === "") return [];
  return pointer.slice(1).split("/").map(unescapePointerToken);
}

/** Build a JSON Pointer from decoded reference tokens. */
export function joinPointer(...tokens: Array<string | number>): string {
  if (tokens.length === 0) return "";
  return `/${tokens.map((token) => escapePointerToken(String(token))).join("/")}`;
}

/**
 * Match a *watch pattern* pointer against a concrete *changed* pointer.
 *
 * Matching is symmetric-subtree: it returns true when either pointer is an
 * ancestor-or-equal of the other, so a change to `/electrical` invalidates a watch
 * on `/electrical/components` and vice versa.
 *
 * A reference token equal to `*` in the **pattern** matches exactly one arbitrary
 * token (it does not span `/`; use one `*` per segment). Concrete changed pointers
 * are never interpreted as patterns.
 */
export function pointerMatchesPattern(pattern: string, changed: string): boolean {
  const patternTokens = parsePointer(pattern);
  const changedTokens = parsePointer(changed);
  const shorter = Math.min(patternTokens.length, changedTokens.length);
  for (let i = 0; i < shorter; i++) {
    const patternToken = patternTokens[i];
    const changedToken = changedTokens[i];
    if (patternToken !== "*" && patternToken !== changedToken) return false;
  }
  // Every common segment matched, so one pointer is a prefix of the other.
  return true;
}

/** True when two concrete pointers are equal after RFC 6901 unescaping. */
export function pointersEqual(a: string, b: string): boolean {
  const ta = parsePointer(a);
  const tb = parsePointer(b);
  if (ta.length !== tb.length) return false;
  return ta.every((token, i) => token === tb[i]);
}

/** True when `child` is strictly below `parent` (both concrete pointers). */
export function isPointerDescendant(child: string, parent: string): boolean {
  const parentTokens = parsePointer(parent);
  const childTokens = parsePointer(child);
  if (childTokens.length <= parentTokens.length) return false;
  return parentTokens.every((token, i) => token === childTokens[i]);
}
