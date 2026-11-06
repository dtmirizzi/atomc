import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { createDemoApi } from "../src/model.js";
import {
  BOM_UNAVAILABLE_NOTICE,
  buildQty,
  deriveBomRows,
  deriveOrderRows,
  deriveQuoteRows,
  formatMoney,
  ORDERS_UNAVAILABLE_NOTICE,
  QUOTES_UNAVAILABLE_NOTICE,
  SOURCING_SIMULATED_NOTICE,
  SOURCING_UNAVAILABLE_NOTICE,
  selectOffer,
  sourcingAvailability,
  stockLabel,
  stockStatus,
  unitPriceMinor,
} from "../src/sourcing/derive.js";
import { SourcingView } from "../src/sourcing/SourcingView.js";
import type {
  FabricationSubtree,
  OrdersSubtree,
  SourcingBomLine,
  SourcingSubtree,
} from "../src/sourcing/types.js";
import { StudioApp } from "../src/studio-app.js";

afterEach(() => {
  cleanup();
});

const line: SourcingBomLine = {
  id: "bom:U1",
  component_refs: ["comp:U1"],
  mpn: "STM32F411CEU6",
  lcsc: "C60442",
  qty_per_unit: 2,
  chosen_offer_ref: "offer:a",
  offers: [
    {
      id: "offer:a",
      vendor: "lcsc",
      sku: "C60442",
      stock: 5,
      lead_time_days: 7,
      price_breaks: [
        { qty: 1, unit_price_minor: 420 },
        { qty: 10, unit_price_minor: 390 },
      ],
      currency: "USD",
    },
    { id: "offer:b", vendor: "mouser", sku: "M1", stock: 900, price_breaks: [] },
  ],
};

const sourcing: SourcingSubtree = {
  currency: "USD",
  build_qty: 5,
  bom: [line],
};

const fabrication: FabricationSubtree = {
  pcb: { qty: 10 },
  quotes: [{ id: "quote:jlc", fab: "jlcpcb", total_minor: 12500, lead_time_days: 6 }],
};

const orders: OrdersSubtree = {
  orders: [
    {
      id: "order:parts",
      vendor: "lcsc",
      status: "placed",
      total_minor: 900,
      lines: [{ sku: "C60442", qty: 3, unit_price_minor: 300 }],
    },
  ],
};

describe("sourcing derivation", () => {
  it("selects the chosen offer, falling back to the first offer", () => {
    expect(selectOffer(line)?.id).toBe("offer:a");
    expect(selectOffer({ id: "bom:x", offers: line.offers ?? [] })?.id).toBe("offer:a");
    expect(
      selectOffer({ id: "bom:x", chosen_offer_ref: "missing", offers: line.offers ?? [] })?.id,
    ).toBe("offer:a");
    expect(selectOffer({ id: "bom:x" })).toBeNull();
    expect(selectOffer({ id: "bom:x", offers: [] })).toBeNull();
  });

  it("chooses the largest price break at or below the quantity", () => {
    const offer = selectOffer(line);
    expect(unitPriceMinor(offer, 1)).toBe(420);
    expect(unitPriceMinor(offer, 5)).toBe(420);
    expect(unitPriceMinor(offer, 10)).toBe(390);
    expect(unitPriceMinor(offer, 100)).toBe(390);
    expect(unitPriceMinor(null, 5)).toBeNull();
    expect(unitPriceMinor({ id: "o", vendor: "x", sku: "x", price_breaks: [] }, 5)).toBeNull();
    expect(
      unitPriceMinor(
        { id: "o", vendor: "x", sku: "x", price_breaks: [{ qty: 10, unit_price_minor: 5 }] },
        1,
      ),
    ).toBe(5);
  });

  it("classifies stock against the required quantity", () => {
    expect(stockStatus(null, 5)).toBe("unknown");
    expect(stockStatus(0, 5)).toBe("out-of-stock");
    expect(stockStatus(3, 5)).toBe("low-stock");
    expect(stockStatus(50, 5)).toBe("in-stock");
    expect(stockLabel("in-stock")).toBe("In stock");
    expect(stockLabel("low-stock")).toBe("Low stock");
    expect(stockLabel("out-of-stock")).toBe("Out of stock");
    expect(stockLabel("unknown")).toBe("Unknown");
  });

  it("formats money and falls back for unknown currencies", () => {
    expect(formatMoney(1234)).toBe("$12.34");
    expect(formatMoney(null)).toBe("—");
    expect(formatMoney(500, "INVALID")).toBe("5.00 INVALID");
  });

  it("normalizes build quantity", () => {
    expect(buildQty(undefined)).toBe(1);
    expect(buildQty({ build_qty: 5 })).toBe(5);
    expect(buildQty({ build_qty: 0 })).toBe(1);
    expect(buildQty({ build_qty: 2.9 })).toBe(2);
  });

  it("derives BOM rows with joins, quantities and costs", () => {
    const rows = deriveBomRows(sourcing, [
      { id: "comp:U1", designator: "U1", footprint: "QFN-48" },
    ]);
    expect(rows).toHaveLength(1);
    const row = rows[0];
    if (!row) throw new Error("row expected");
    expect(row.mpn).toBe("STM32F411CEU6");
    expect(row.footprint).toBe("QFN-48");
    expect(row.quantity).toBe(10);
    expect(row.qtyPerUnit).toBe(2);
    expect(row.stockStatus).toBe("low-stock");
    expect(row.unitCents).toBe(390);
    expect(row.extendedCents).toBe(3900);
    expect(row.vendor).toBe("lcsc");
    expect(row.sku).toBe("C60442");
    expect(row.componentRefs).toEqual(["comp:U1"]);
    expect(row.chosenOfferId).toBe("offer:a");
  });

  it("reports a missing footprint and an unknown offer without inventing values", () => {
    const rows = deriveBomRows({ bom: [{ id: "bom:J1" }] });
    expect(rows[0]?.footprint).toBeNull();
    expect(rows[0]?.unitCents).toBeNull();
    expect(rows[0]?.extendedCents).toBeNull();
    expect(rows[0]?.stockStatus).toBe("unknown");
    expect(rows[0]?.vendor).toBeNull();
    expect(rows[0]?.mpn).toBe("bom:J1");
    expect(deriveBomRows(null)).toEqual([]);
    expect(deriveBomRows({})).toEqual([]);
  });

  it("derives quote rows from fabrication data", () => {
    const rows = deriveQuoteRows(fabrication);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      id: "quote:jlc",
      vendor: "jlcpcb",
      quantity: 10,
      unitCents: 1250,
      totalCents: 12500,
      leadTimeDays: 6,
      status: "quoted",
    });
    expect(deriveQuoteRows({ quotes: [{ id: "q" }] })[0]?.unitCents).toBeNull();
    expect(deriveQuoteRows(null)).toEqual([]);
  });

  it("derives order rows from order data", () => {
    const rows = deriveOrderRows(orders);
    expect(rows[0]).toMatchObject({
      id: "order:parts",
      vendor: "lcsc",
      quantity: 3,
      unitCents: 300,
      totalCents: 900,
      status: "placed",
    });
    expect(deriveOrderRows({ orders: [{ id: "order:x" }] })[0]?.quantity).toBeNull();
    expect(deriveOrderRows(null)).toEqual([]);
  });

  it("reports availability per section", () => {
    expect(sourcingAvailability(sourcing, fabrication, orders)).toEqual({
      bom: true,
      quotes: true,
      orders: true,
      any: true,
    });
    expect(sourcingAvailability(null, null, null)).toEqual({
      bom: false,
      quotes: false,
      orders: false,
      any: false,
    });
  });
});

describe("SourcingView", () => {
  it("shows the exact unavailable notice when no supply-chain data exists", () => {
    render(<SourcingView dataMode="daemon" />);
    expect(screen.getByText(SOURCING_UNAVAILABLE_NOTICE)).toBeInTheDocument();
  });

  it("renders BOM rows and per-section notices without any order actions", () => {
    render(
      <SourcingView
        sourcing={sourcing}
        components={[{ id: "comp:U1", footprint: "QFN-48" }]}
        dataMode="daemon"
      />,
    );
    const table = screen.getByRole("table", { name: "Bill of materials lines" });
    expect(within(table).getByText("STM32F411CEU6")).toBeInTheDocument();
    expect(within(table).getByText("QFN-48")).toBeInTheDocument();
    expect(within(table).getByText("$3.90")).toBeInTheDocument();
    expect(within(table).getByText("$39.00")).toBeInTheDocument();
    expect(screen.getByText(QUOTES_UNAVAILABLE_NOTICE)).toBeInTheDocument();
    expect(screen.getByText(ORDERS_UNAVAILABLE_NOTICE)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("renders quote and order tables when that data is present", () => {
    render(
      <SourcingView sourcing={{}} fabrication={fabrication} orders={orders} dataMode="daemon" />,
    );
    expect(screen.getByText(BOM_UNAVAILABLE_NOTICE)).toBeInTheDocument();
    const quotes = screen.getByRole("table", { name: "Fabrication quotes" });
    expect(within(quotes).getByText("jlcpcb")).toBeInTheDocument();
    expect(within(quotes).getByText("$12.50")).toBeInTheDocument();
    const orderTable = screen.getByRole("table", { name: "Placed orders" });
    expect(within(orderTable).getByText("placed")).toBeInTheDocument();
    expect(within(orderTable).getByText("$3.00")).toBeInTheDocument();
  });

  it("labels simulated rows in preview mode", () => {
    render(<SourcingView sourcing={sourcing} dataMode="demo" />);
    expect(screen.getByText(SOURCING_SIMULATED_NOTICE)).toBeInTheDocument();
  });

  it("notes daemon-sourced data and does not claim plugins ran", () => {
    render(<SourcingView sourcing={sourcing} dataMode="daemon" />);
    expect(
      screen.getByText(/No sourcing, fabrication or orders DAG nodes have run/),
    ).toBeInTheDocument();
  });

  it("is reachable from the Studio shell and shows labeled sample data", async () => {
    render(<StudioApp api={createDemoApi()} demo />);
    await screen.findByRole("heading", { name: /good morning, engineer/i });
    fireEvent.click(screen.getByRole("button", { name: "BOM & orders" }));
    expect(screen.getByRole("heading", { name: /BOM & orders/i })).toBeInTheDocument();
    expect(screen.getByText("STM32F411CEU6")).toBeInTheDocument();
    expect(screen.getByText(SOURCING_SIMULATED_NOTICE)).toBeInTheDocument();
    expect(screen.getByText(QUOTES_UNAVAILABLE_NOTICE)).toBeInTheDocument();
  });
});
