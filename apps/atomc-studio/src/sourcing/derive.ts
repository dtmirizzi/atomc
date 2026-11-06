import type {
  ComponentSummary,
  FabricationSubtree,
  OrdersSubtree,
  PriceBreak,
  SourcingBomLine,
  SourcingOffer,
  SourcingSubtree,
} from "./types.js";

export type StockStatus = "in-stock" | "low-stock" | "out-of-stock" | "unknown";

export interface BomRow {
  id: string;
  mpn: string;
  footprint: string | null;
  /** Pieces needed across the whole build (qty_per_unit × build_qty). */
  quantity: number;
  qtyPerUnit: number;
  stockStatus: StockStatus;
  stock: number | null;
  unitCents: number | null;
  extendedCents: number | null;
  currency: string;
  vendor: string | null;
  sku: string | null;
  leadTimeDays: number | null;
  componentRefs: string[];
  chosenOfferId: string | null;
}

export interface QuoteRow {
  id: string;
  vendor: string;
  quantity: number | null;
  unitCents: number | null;
  totalCents: number | null;
  leadTimeDays: number | null;
  status: string;
  currency: string;
}

export interface OrderRow {
  id: string;
  vendor: string;
  quantity: number | null;
  unitCents: number | null;
  totalCents: number | null;
  leadTimeDays: number | null;
  status: string;
  currency: string;
}

export interface SourcingAvailability {
  bom: boolean;
  quotes: boolean;
  orders: boolean;
  any: boolean;
}

export const DEFAULT_BUILD_QTY = 1;

/** Shown when a project has no supply-chain data at all, the real case today. */
export const SOURCING_UNAVAILABLE_NOTICE =
  "Sourcing and fabrication plugins are not implemented; no BOM, quote or order data exists.";

/** Shown in preview mode so sample rows are never mistaken for real data. */
export const SOURCING_SIMULATED_NOTICE =
  "Sourcing, fabrication and orders plugins are not implemented; the rows below are simulated fixture data, not real BOM, quote or order data.";

export const BOM_UNAVAILABLE_NOTICE =
  "The sourcing plugin is not implemented; no BOM data exists for this project.";

export const QUOTES_UNAVAILABLE_NOTICE =
  "The fabrication plugin is not implemented; no PCB or assembly quote data exists.";

export const ORDERS_UNAVAILABLE_NOTICE =
  "The orders plugin is not implemented; no order data exists.";

export function selectOffer(line: SourcingBomLine): SourcingOffer | null {
  const offers = line.offers ?? [];
  if (offers.length === 0) return null;
  if (line.chosen_offer_ref !== undefined) {
    const chosen = offers.find((offer) => offer.id === line.chosen_offer_ref);
    if (chosen) return chosen;
  }
  return offers[0] ?? null;
}

/** Pick the unit price for the largest price break at or below `quantity`. */
export function unitPriceMinor(offer: SourcingOffer | null, quantity: number): number | null {
  if (offer === null) return null;
  const breaks = [...(offer.price_breaks ?? [])].sort((a, b) => a.qty - b.qty);
  if (breaks.length === 0) return null;
  let selected: PriceBreak | null = null;
  for (const priceBreak of breaks) {
    if (priceBreak.qty <= quantity) selected = priceBreak;
  }
  selected = selected ?? breaks[0] ?? null;
  return selected === null ? null : selected.unit_price_minor;
}

export function stockStatus(stock: number | null, required: number): StockStatus {
  if (stock === null) return "unknown";
  if (stock <= 0) return "out-of-stock";
  if (stock < required) return "low-stock";
  return "in-stock";
}

export function stockLabel(status: StockStatus): string {
  switch (status) {
    case "in-stock":
      return "In stock";
    case "low-stock":
      return "Low stock";
    case "out-of-stock":
      return "Out of stock";
    default:
      return "Unknown";
  }
}

export function formatMoney(cents: number | null, currency = "USD"): string {
  if (cents === null) return "—";
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency,
      minimumFractionDigits: 2,
    }).format(cents / 100);
  } catch {
    return `${(cents / 100).toFixed(2)} ${currency}`;
  }
}

export function buildQty(sourcing: SourcingSubtree | null | undefined): number {
  const value = sourcing?.build_qty ?? DEFAULT_BUILD_QTY;
  return Number.isFinite(value) && value >= 1 ? Math.floor(value) : DEFAULT_BUILD_QTY;
}

export function deriveBomRows(
  sourcing: SourcingSubtree | null | undefined,
  components: ComponentSummary[] = [],
): BomRow[] {
  const bom = sourcing?.bom ?? [];
  if (bom.length === 0) return [];
  const quantityMultiplier = buildQty(sourcing);
  const currency = sourcing?.currency ?? "USD";
  const footprintById = new Map<string, string>();
  for (const component of components) {
    if (component.footprint !== undefined) footprintById.set(component.id, component.footprint);
  }
  return bom.map((line) => {
    const qtyPerUnit = line.qty_per_unit ?? 1;
    const quantity = qtyPerUnit * quantityMultiplier;
    const offer = selectOffer(line);
    const unitCents = unitPriceMinor(offer, quantity);
    const componentRefs = line.component_refs ?? [];
    let footprint: string | null = null;
    for (const ref of componentRefs) {
      const found = footprintById.get(ref);
      if (found !== undefined) {
        footprint = found;
        break;
      }
    }
    const stock = offer?.stock ?? null;
    return {
      id: line.id,
      mpn: line.mpn ?? line.lcsc ?? line.id,
      footprint,
      quantity,
      qtyPerUnit,
      stockStatus: stockStatus(stock, quantity),
      stock,
      unitCents,
      extendedCents: unitCents === null ? null : unitCents * quantity,
      currency: offer?.currency ?? currency,
      vendor: offer?.vendor ?? null,
      sku: offer?.sku ?? null,
      leadTimeDays: offer?.lead_time_days ?? null,
      componentRefs,
      chosenOfferId: offer?.id ?? null,
    };
  });
}

export function deriveQuoteRows(fabrication: FabricationSubtree | null | undefined): QuoteRow[] {
  const quotes = fabrication?.quotes ?? [];
  const quantity = fabrication?.pcb?.qty ?? null;
  return quotes.map((quote) => {
    const totalCents = quote.total_minor ?? null;
    const unitCents =
      totalCents !== null && quantity !== null && quantity > 0
        ? Math.round(totalCents / quantity)
        : null;
    return {
      id: quote.id,
      vendor: quote.fab ?? "unknown",
      quantity,
      unitCents,
      totalCents,
      leadTimeDays: quote.lead_time_days ?? null,
      status: "quoted",
      currency: quote.currency ?? "USD",
    };
  });
}

export function deriveOrderRows(orders: OrdersSubtree | null | undefined): OrderRow[] {
  const records = orders?.orders ?? [];
  return records.map((order) => {
    const lines = order.lines ?? [];
    const quantity = lines.length > 0 ? lines.reduce((sum, line) => sum + line.qty, 0) : null;
    const totalCents = order.total_minor ?? null;
    const unitCents =
      totalCents !== null && quantity !== null && quantity > 0
        ? Math.round(totalCents / quantity)
        : null;
    return {
      id: order.id,
      vendor: order.vendor ?? "unknown",
      quantity,
      unitCents,
      totalCents,
      leadTimeDays: null,
      status: order.status ?? "unknown",
      currency: order.currency ?? "USD",
    };
  });
}

export function sourcingAvailability(
  sourcing: SourcingSubtree | null | undefined,
  fabrication: FabricationSubtree | null | undefined,
  orders: OrdersSubtree | null | undefined,
): SourcingAvailability {
  const bom = (sourcing?.bom?.length ?? 0) > 0;
  const quotes = (fabrication?.quotes?.length ?? 0) > 0;
  const orderRows = (orders?.orders?.length ?? 0) > 0;
  return { bom, quotes, orders: orderRows, any: bom || quotes || orderRows };
}
