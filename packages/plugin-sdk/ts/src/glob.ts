/**
 * Tiny, dependency-free glob matcher for project-relative POSIX paths.
 *
 * Semantics (documented and tested):
 * - Paths and patterns are normalized to POSIX (`\` → `/`), stripped of a leading
 *   `./`, and collapsed of duplicate `/`.
 * - Patterns are matched against the whole normalized path (anchored at the project root).
 * - `*` matches any run of characters within one path segment (never `/`).
 * - `?` matches exactly one character within a segment.
 * - `**` as a complete segment matches zero or more segments.
 * - Character classes and braces are **not** supported; `[` etc. are treated literally.
 */

/** Normalize a project-relative path or glob to POSIX form. */
export function normalizeProjectPath(path: string): string {
  let normalized = path.replace(/\\/g, "/");
  normalized = normalized.replace(/^\.\//, "");
  normalized = normalized.replace(/\/{2,}/g, "/");
  if (normalized.length > 1) normalized = normalized.replace(/\/+$/, "");
  return normalized;
}

/** True when `path` is relative and does not escape the package/project root. */
export function isSafeRelativePath(path: string): boolean {
  if (path === "") return false;
  if (/^[A-Za-z]:/.test(path)) return false;
  const normalized = normalizeProjectPath(path);
  if (normalized.startsWith("/")) return false;
  return !normalized.split("/").includes("..");
}

function escapeRegExpChar(char: string): string {
  return /[.*+?^${}()|[\]\\]/.test(char) ? `\\${char}` : char;
}

function segmentToRegExp(segment: string): RegExp {
  let source = "";
  for (const char of segment) {
    if (char === "*") source += ".*";
    else if (char === "?") source += ".";
    else source += escapeRegExpChar(char);
  }
  return new RegExp(`^${source}$`);
}

function matchSegments(pattern: string[], path: string[]): boolean {
  if (pattern.length === 0) return path.length === 0;
  const [head, ...rest] = pattern;
  if (head === "**") {
    // `**` matches zero segments ...
    if (matchSegments(rest, path)) return true;
    // ... or one or more segments.
    if (path.length > 0) return matchSegments(pattern, path.slice(1));
    return false;
  }
  if (path.length === 0) return false;
  const [pathHead, ...pathRest] = path;
  if (!segmentToRegExp(head ?? "").test(pathHead ?? "")) return false;
  return matchSegments(rest, pathRest);
}

/**
 * Match a single glob `pattern` against a project-relative `filePath`.
 * Both are normalized to POSIX before matching.
 */
export function matchesGlob(pattern: string, filePath: string): boolean {
  const normalizedPattern = normalizeProjectPath(pattern);
  const normalizedPath = normalizeProjectPath(filePath);
  if (normalizedPath.startsWith("/")) return false;
  const patternSegments = normalizedPattern === "" ? [""] : normalizedPattern.split("/");
  const pathSegments = normalizedPath === "" ? [""] : normalizedPath.split("/");
  return matchSegments(patternSegments, pathSegments);
}

/** True when `filePath` matches any of the given glob `patterns`. */
export function matchesAnyGlob(patterns: readonly string[], filePath: string): boolean {
  return patterns.some((pattern) => matchesGlob(pattern, filePath));
}
