/**
 * Canonical IR snippets shared by the RPC contract tests.
 *
 * These are plain JSON values posted through `ir.transact`; the daemon validates
 * them against the frozen `system_ir.json` schema.
 */

/** A minimal, valid `/electrical` node (mirrors the core-ir `electrical` shape). */
export const EMPTY_ELECTRICAL = {
  _meta: { rev: 0, lock: null },
  source: { kind: "atopile", entry: "main.ato:App" },
  components: [],
  nets: [],
  assertions: [],
  erc: [],
} as const;

/** A component whose pin references a net that does not exist (dangling ref). */
export const DANGLING_COMPONENT = {
  id: "comp:U9",
  designator: "U9",
  pins: [{ number: "1", net_ref: "net:does_not_exist" }],
} as const;

/** A minimal, valid `/keyboard` node watched by the fake plugin's refresh node. */
export const MINIMAL_KEYBOARD = {
  _meta: { rev: 0, lock: null },
  matrix: {
    rows: 1,
    cols: 1,
    diode_direction: "COL2ROW",
    row_pins: ["B12"],
    col_pins: ["B13"],
  },
  keys: [{ id: "key:K0_0", row: 0, col: 0 }],
  usb: { vid: "0xFEED", pid: "0x0001", manufacturer: "atomc", product: "rpc-test" },
  qmk: { keyboard_path: "atomc/rpc-test" },
} as const;
