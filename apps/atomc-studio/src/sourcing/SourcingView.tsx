import { CircleHelp, Clock3, HardDrive, PackageCheck } from "lucide-react";
import { useId, useMemo } from "react";
import type { DataMode } from "../model.js";
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
  sourcingAvailability,
  stockLabel,
} from "./derive.js";
import type {
  ComponentSummary,
  FabricationSubtree,
  OrdersSubtree,
  SourcingSubtree,
} from "./types.js";
import "./sourcing.css";

export interface SourcingViewProps {
  sourcing?: SourcingSubtree | null | undefined;
  fabrication?: FabricationSubtree | null | undefined;
  orders?: OrdersSubtree | null | undefined;
  components?: ComponentSummary[] | undefined;
  dataMode: DataMode;
}

function LeadTime({ days }: { days: number | null }) {
  if (days === null) return <span className="srctable__muted">—</span>;
  return (
    <span className="srctable__lead">
      <Clock3 size={12} aria-hidden="true" />
      {days} day{days === 1 ? "" : "s"}
    </span>
  );
}

export function SourcingView({
  sourcing,
  fabrication,
  orders,
  components = [],
  dataMode,
}: SourcingViewProps) {
  const baseId = useId();
  const bomRows = useMemo(() => deriveBomRows(sourcing, components), [sourcing, components]);
  const quoteRows = useMemo(() => deriveQuoteRows(fabrication), [fabrication]);
  const orderRows = useMemo(() => deriveOrderRows(orders), [orders]);
  const availability = useMemo(
    () => sourcingAvailability(sourcing, fabrication, orders),
    [sourcing, fabrication, orders],
  );
  const quantity = buildQty(sourcing);
  const currency = sourcing?.currency ?? "USD";

  return (
    <div className="view-stack">
      <div className="view-intro">
        <div>
          <span className="eyebrow">SUPPLY CHAIN</span>
          <h2>BOM &amp; orders</h2>
          <p>
            Bill of materials, fabrication quotes and placed orders, read from the IR
            <code> /sourcing</code>, <code>/fabrication</code> and <code>/orders</code> nodes.
          </p>
        </div>
        <span className="badge badge--neutral">
          <PackageCheck size={13} aria-hidden="true" />
          {bomRows.length} BOM lines
        </span>
      </div>

      {!availability.any ? (
        <div className="info-banner">
          <CircleHelp size={16} aria-hidden="true" />
          <span>{SOURCING_UNAVAILABLE_NOTICE}</span>
        </div>
      ) : (
        <>
          {dataMode === "demo" && (
            <div className="info-banner">
              <CircleHelp size={16} aria-hidden="true" />
              <span>{SOURCING_SIMULATED_NOTICE}</span>
            </div>
          )}

          <section className="panel srctable" aria-labelledby={`${baseId}-bom`}>
            <div className="panel__heading">
              <div>
                <div className="panel__eyebrow">BILL OF MATERIALS</div>
                <h3 id={`${baseId}-bom`}>
                  BOM lines <span className="heading-count">{bomRows.length}</span>
                </h3>
                <p className="srctable__note">
                  Quantities are for {quantity} assembled board{quantity === 1 ? "" : "s"}; costs in{" "}
                  {currency}.
                </p>
              </div>
            </div>
            {availability.bom ? (
              <table className="srctable__table">
                <caption className="visually-hidden">Bill of materials lines</caption>
                <thead>
                  <tr>
                    <th scope="col">MPN</th>
                    <th scope="col">FOOTPRINT</th>
                    <th scope="col">QTY</th>
                    <th scope="col">STOCK</th>
                    <th scope="col">UNIT COST</th>
                    <th scope="col">EXTENDED</th>
                  </tr>
                </thead>
                <tbody>
                  {bomRows.map((row) => (
                    <tr key={row.id}>
                      <th scope="row" className="srctable__part">
                        <strong>{row.mpn}</strong>
                        {row.sku !== null && (
                          <code>
                            {row.vendor} · {row.sku}
                          </code>
                        )}
                      </th>
                      <td>{row.footprint ?? <span className="srctable__muted">Not in IR</span>}</td>
                      <td>{row.quantity}</td>
                      <td>
                        <span className={`srctable__stock srctable__stock--${row.stockStatus}`}>
                          {stockLabel(row.stockStatus)}
                        </span>
                        {row.stock !== null && (
                          <span className="srctable__muted"> {row.stock} on hand</span>
                        )}
                      </td>
                      <td>
                        <span className="srctable__cost">
                          {formatMoney(row.unitCents, row.currency)}
                        </span>
                        <LeadTime days={row.leadTimeDays} />
                      </td>
                      <td className="srctable__cost">
                        {formatMoney(row.extendedCents, row.currency)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="srctable__notice">{BOM_UNAVAILABLE_NOTICE}</p>
            )}
          </section>

          <section className="panel srctable" aria-labelledby={`${baseId}-quotes`}>
            <div className="panel__heading">
              <div>
                <div className="panel__eyebrow">FABRICATION QUOTES</div>
                <h3 id={`${baseId}-quotes`}>
                  PCB &amp; assembly quotes{" "}
                  <span className="heading-count">{quoteRows.length}</span>
                </h3>
                <p className="srctable__note">
                  Vendor quotations, not placed orders. Placing an order is not available.
                </p>
              </div>
            </div>
            {availability.quotes ? (
              <table className="srctable__table">
                <caption className="visually-hidden">Fabrication quotes</caption>
                <thead>
                  <tr>
                    <th scope="col">VENDOR</th>
                    <th scope="col">QTY</th>
                    <th scope="col">UNIT COST</th>
                    <th scope="col">LEAD TIME</th>
                    <th scope="col">STATUS</th>
                  </tr>
                </thead>
                <tbody>
                  {quoteRows.map((row) => (
                    <tr key={row.id}>
                      <th scope="row" className="srctable__part">
                        <strong>{row.vendor}</strong>
                        <code>{row.id}</code>
                      </th>
                      <td>{row.quantity ?? <span className="srctable__muted">—</span>}</td>
                      <td className="srctable__cost">{formatMoney(row.unitCents, row.currency)}</td>
                      <td>
                        <LeadTime days={row.leadTimeDays} />
                      </td>
                      <td>
                        <span className="srctable__status">{row.status}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="srctable__notice">{QUOTES_UNAVAILABLE_NOTICE}</p>
            )}
          </section>

          <section className="panel srctable" aria-labelledby={`${baseId}-orders`}>
            <div className="panel__heading">
              <div>
                <div className="panel__eyebrow">ORDERS</div>
                <h3 id={`${baseId}-orders`}>
                  Placed orders <span className="heading-count">{orderRows.length}</span>
                </h3>
                <p className="srctable__note">
                  Order records are read-only; payment and placement are out of scope for v0.
                </p>
              </div>
            </div>
            {availability.orders ? (
              <table className="srctable__table">
                <caption className="visually-hidden">Placed orders</caption>
                <thead>
                  <tr>
                    <th scope="col">VENDOR</th>
                    <th scope="col">QTY</th>
                    <th scope="col">UNIT COST</th>
                    <th scope="col">STATUS</th>
                  </tr>
                </thead>
                <tbody>
                  {orderRows.map((row) => (
                    <tr key={row.id}>
                      <th scope="row" className="srctable__part">
                        <strong>{row.vendor}</strong>
                        <code>{row.id}</code>
                      </th>
                      <td>{row.quantity ?? <span className="srctable__muted">—</span>}</td>
                      <td className="srctable__cost">{formatMoney(row.unitCents, row.currency)}</td>
                      <td>
                        <span className="srctable__status">{row.status}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="srctable__notice">{ORDERS_UNAVAILABLE_NOTICE}</p>
            )}
          </section>

          {dataMode === "daemon" && (
            <div className="info-banner">
              <HardDrive size={16} aria-hidden="true" />
              <span>
                Data reflects the IR revision returned by the daemon. No sourcing, fabrication or
                orders DAG nodes have run in this snapshot beyond what the IR already contains.
              </span>
            </div>
          )}
        </>
      )}
    </div>
  );
}
