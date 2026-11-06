/**
 * Structural subsets of the IR supply-chain nodes Studio reads.
 *
 * Mirrors `docs/architecture/contracts/ir-schema.md` §4.7–4.9. These are read-only
 * shapes: no sourcing, fabrication or orders plugin writes them yet, so most
 * projects simply have no data here and Studio must say so honestly.
 */

export interface PriceBreak {
  qty: number;
  unit_price_minor: number;
}

export interface SourcingOffer {
  id: string;
  vendor: string;
  sku: string;
  stock?: number;
  lead_time_days?: number;
  moq?: number;
  price_breaks?: PriceBreak[];
  currency?: string;
  fetched_at?: string;
  url?: string;
}

export interface SourcingAlternate {
  mpn: string;
  lcsc?: string;
  reason?: string;
}

export interface SourcingBomLine {
  id: string;
  component_refs?: string[];
  mpn?: string;
  lcsc?: string;
  qty_per_unit?: number;
  offers?: SourcingOffer[];
  chosen_offer_ref?: string;
  alternates?: SourcingAlternate[];
}

/** IR `/sourcing` subtree (contract §4.7). */
export interface SourcingSubtree {
  currency?: string;
  build_qty?: number;
  budget?: { per_unit_minor: number; total_minor?: number };
  bom?: SourcingBomLine[];
}

export interface FabPcbSpec {
  layers?: number;
  width_mm?: number;
  height_mm?: number;
  thickness_mm?: number;
  finish?: string;
  color?: string;
  qty?: number;
}

export interface FabQuote {
  id: string;
  fab?: string;
  total_minor?: number;
  currency?: string;
  lead_time_days?: number;
  fetched_at?: string;
  url?: string;
  breakdown?: Record<string, number>;
}

/** IR `/fabrication` subtree (contract §4.8). */
export interface FabricationSubtree {
  pcb?: FabPcbSpec;
  assembly?: { side?: string; parts_count?: number };
  quotes?: FabQuote[];
}

export interface OrderLine {
  sku: string;
  qty: number;
  unit_price_minor: number;
}

export interface OrderRecord {
  id: string;
  vendor?: string;
  kind?: string;
  status?: string;
  lines?: OrderLine[];
  total_minor?: number;
  currency?: string;
  external_id?: string;
  tracking?: Array<{ carrier: string; number: string; url?: string }>;
  history?: Array<{ at: string; status: string; note?: string }>;
}

/** IR `/orders` subtree (contract §4.9). */
export interface OrdersSubtree {
  orders?: OrderRecord[];
}

/** Minimal `/electrical/components` projection used to resolve a BOM line's footprint. */
export interface ComponentSummary {
  id: string;
  designator?: string;
  mpn?: string;
  footprint?: string;
}
