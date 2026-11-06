/**
 * atomc-cannode project configuration.
 *
 * Plain object stub consumed by the CLI/daemon. Budget gates are expressed in
 * USD minor units (cents) per board at the configured build quantity.
 */
const config = {
  project: "atomc-cannode",
  ir: "system_ir.json",
  daemon: { host: "127.0.0.1", port: 7438 },
  plugins: ["atopile", "sourcing"],
  sourcing: {
    build_qty: 5,
    currency: "USD",
    exclude_from_budget: [],
  },
  gates: {
    "bom.cost_under_budget": { per_unit_minor: 1500, total_minor: 7500 },
  },
} as const;

export default config;
