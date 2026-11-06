/**
 * WebGL capability probe.
 *
 * Isolated behind a module so tests can mock it: jsdom has no WebGL
 * implementation, and the viewer must degrade to its accessible summary instead
 * of throwing.
 */
export function supportsWebGL(): boolean {
  if (typeof document === "undefined") return false;
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") ?? canvas.getContext("webgl"));
  } catch {
    return false;
  }
}
