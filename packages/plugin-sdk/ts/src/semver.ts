/**
 * Minimal SemVer / SemVer-range syntax validators.
 *
 * The manifest contract requires `version` to be SemVer and `atomc` to be a SemVer
 * range, but PLAN §2 does not include a `semver` dependency. Rather than add a
 * catalog entry we validate syntax with regexes covering the npm range grammar that
 * plugin authors use (comparators, `||` unions, hyphen ranges, `x`/`*` wildcards).
 *
 * The pattern *strings* are exported so the manifest Zod schema can attach them as
 * JSON Schema `pattern`s, keeping the TS and Python validators aligned on paper.
 * This validates *syntax only*; it intentionally does not implement range satisfaction.
 */

const NUMERIC = "0|[1-9]\\d*";
const NUM = `(?:${NUMERIC})`;
const PRERELEASE =
  "(?:-(?:\\d+|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)(?:\\.(?:\\d+|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*))*)?";
const BUILD = "(?:\\+[0-9A-Za-z-]+(?:\\.[0-9A-Za-z-]+)*)?";

const PARTIAL = `v?(?:${NUMERIC}|[xX*])(?:\\.(?:${NUMERIC}|[xX*]))?(?:\\.(?:${NUMERIC}|[xX*]))?${PRERELEASE}${BUILD}`;
const COMPARATOR = `(?:>=|<=|>|<|=|~|\\^)?\\s*${PARTIAL}`;
const HYPHEN = `${PARTIAL}\\s+-\\s+${PARTIAL}`;
const COMPARATOR_SET = `(?:${HYPHEN}|${COMPARATOR}(?:\\s+${COMPARATOR})*)`;

/** Anchored regex source matching an exact SemVer version. */
export const SEMVER_PATTERN = `^${NUM}\\.${NUM}\\.${NUM}${PRERELEASE}${BUILD}$`;
/** Anchored regex source matching a SemVer range (`>=0.0.1 <0.2.0`, `^1.2 || ~2.0`). */
export const SEMVER_RANGE_PATTERN = `^(?:${COMPARATOR_SET})(?:\\s*\\|\\|\\s*${COMPARATOR_SET})*$`;

export const SEMVER_RE = new RegExp(SEMVER_PATTERN);
export const SEMVER_RANGE_RE = new RegExp(SEMVER_RANGE_PATTERN);

/** True when `value` is an exact SemVer version (e.g. `1.2.3-rc.1+build.5`). */
export function isSemver(value: string): boolean {
  return SEMVER_RE.test(value);
}

/** True when `value` is a valid SemVer range (e.g. `>=0.0.1 <0.2.0`, `^1.2 || ~2.0`). */
export function isSemverRange(value: string): boolean {
  return value.trim() !== "" && SEMVER_RANGE_RE.test(value);
}
