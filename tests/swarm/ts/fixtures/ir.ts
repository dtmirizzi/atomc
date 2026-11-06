/**
 * Canonical IR snippets for the swarm E2E tests (copied from the RPC fixtures;
 * not imported across test suites per the brief).
 */

/** A minimal, valid `/electrical` node with no nets (so the fake gate fails). */
export const EMPTY_ELECTRICAL = {
  _meta: { rev: 0, lock: null },
  source: { kind: "atopile", entry: "main.ato:App" },
  components: [],
  nets: [],
  assertions: [],
  erc: [],
} as const;

/** A minimal valid net appended to `/electrical/nets` by the scripted provider. */
export const FIX_NET = {
  id: "net:N0",
  name: "N0",
  class: "signal",
} as const;
