/**
 * atomc-drivetrain project configuration (modeled fixture).
 *
 * Plain object stub consumed by the CLI/daemon. Budget gates are expressed in USD
 * minor units (cents) per board at the configured build quantity.
 *
 * This fixture is a *model*, not a buildable design. See README.md.
 */
const config = {
  project: "atomc-drivetrain",
  ir: "system_ir.json",
  daemon: { host: "127.0.0.1", port: 7437 },
  plugins: ["atopile", "qmk", "renode", "cad-jig", "sourcing"],
  sourcing: {
    build_qty: 2,
    currency: "USD",
  },
  gates: {
    "bom.cost_under_budget": { per_unit_minor: 12000, total_minor: 24000 },
  },
} as const;

export default config;
