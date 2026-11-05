/**
 * atomc-pad project configuration (WP-1.6 seed).
 *
 * Plain object stub consumed by the CLI/daemon once they land (Phase 3). Budget
 * gates are expressed in USD minor units (cents) per board at the configured
 * build quantity, excluding switches and keycaps.
 */
const config = {
  project: "atomc-pad",
  ir: "system_ir.json",
  daemon: { host: "127.0.0.1", port: 7437 },
  plugins: ["atopile", "qmk", "renode", "cad-jig", "sourcing"],
  sourcing: {
    build_qty: 5,
    currency: "USD",
    exclude_from_budget: ["switches", "keycaps"],
  },
  gates: {
    "bom.cost_under_budget": { per_unit_minor: 1500, total_minor: 7500 },
  },
} as const;

export default config;
