/**
 * Deterministic change matcher for the DAG.
 *
 * The daemon owns scheduling, debounce timers, and content hashing; this module only
 * answers "does this IR change / file change invalidate this watch?" so the same
 * semantics can be tested and shared by the Python SDK.
 */

import { matchesAnyGlob, normalizeProjectPath } from "./glob.js";
import type { AtomcWatch } from "./manifest.js";
import { pointerMatchesPattern } from "./pointer.js";

/** A batch of IR pointer and/or file changes reported by the daemon. */
export interface ChangeSet {
  /** Concrete changed IR pointers (RFC 6901). */
  readonly ir?: readonly string[];
  /** Concrete changed project-relative file paths. */
  readonly files?: readonly string[];
}

/** True when any changed pointer matches any watch pointer (subtree semantics). */
export function watchMatchesIr(
  watch: Pick<AtomcWatch, "ir">,
  changedPointers: readonly string[],
): boolean {
  return watch.ir.some((pattern) =>
    changedPointers.some((pointer) => pointerMatchesPattern(pattern, pointer)),
  );
}

/** True when any changed file matches any watch glob. */
export function watchMatchesFiles(
  watch: Pick<AtomcWatch, "files">,
  changedFiles: readonly string[],
): boolean {
  return changedFiles.some((file) => matchesAnyGlob(watch.files, file));
}

/** True when a change set invalidates the watch via IR pointers or file globs. */
export function watchMatches(watch: AtomcWatch, changes: ChangeSet): boolean {
  const irChanged = changes.ir !== undefined && watchMatchesIr(watch, changes.ir);
  const filesChanged = changes.files !== undefined && watchMatchesFiles(watch, changes.files);
  return irChanged || filesChanged;
}

/** Normalize a project-relative file path for matching (re-exported convenience). */
export const normalizeWatchPath = normalizeProjectPath;
