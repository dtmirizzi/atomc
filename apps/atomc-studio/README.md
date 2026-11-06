# Atomc Studio

Atomc Studio is the local-first engineering dashboard for hardware projects: project health, DAG build status, gate results, specialist runs and build artifacts.

## Run

```bash
pnpm install
pnpm --filter @atomc/studio dev
```

By default Studio opens in **Preview workspace** with clearly labeled fixture data. Preview actions do not call the daemon or claim that a build ran.

For an embedded desktop host, set `window.atomcStudioHost` before the app loads. The browser API intentionally accepts loopback daemon endpoints only; a production desktop host is responsible for bearer-token storage and auth headers.

```ts
interface StudioHostBridge {
  connectDaemon({ url }: { url: string }): Promise<StudioRpcClient>;
}
```

Then open Studio with `?demo=false&project=atomc-keeb&path=/path/to/project`. The trusted host bridge returns a browser-safe RPC facade. Studio never reads bearer tokens from URLs, query strings, local storage, or frontend configuration. A plain browser deployment without a host bridge fails closed with a connection error. `StudioRpcClient` needs the typed `getIR`, `dagStatus`, `listGates`, and `runDAG` methods from `@atomc/daemon-client`.

## Views

- **Overview:** IR revision, gate health, build status and recent activity. Agent panels carry a data-source notice; spend is never inferred from gate ownership.
- **Build graph:** DAG node states from the snapshot. The daemon RPC returns no dependency edges, so nodes are rendered without connectors; the status badge derives from actual node states.
- **Gate results:** filter PASS/FAIL/SKIP/ERROR and inspect owner/revision/details.
- **Gate board:** every gate grouped by owning specialist domain (ee/fw/mech/ops), with severity and result filter chips, per-domain pass-rate bars and an expandable drill-in that renders the real `GateResult` fields (evidence, suggestions, duration, IR revision, evaluation time). Gates with no `owner_agent` are grouped under **Unowned** with a coordinator-review note rather than being dropped.
- **BOM & orders:** BOM lines, fabrication quotes and orders read from the IR `/sourcing`, `/fabrication` and `/orders` nodes. When a project carries none of this data (the normal case today, since no sourcing/fabrication/orders plugin exists), the view states that plainly — it never invents rows, totals or order actions. Preview mode labels its sample rows as simulated.
- **Agent team:** specialist cards. In preview mode they are simulated (labeled); in daemon mode sessions and spend are reported as unavailable rather than invented.
- **Artifacts:** output groups. Preview data is fixture-only; daemon-mode stays empty until the RPC reports per-node artifacts.
- **3D viewer:** board outline extrusion with switch cutouts and test-pad markers derived from `/layout`, `/keyboard` and `/mechanical`. Preview mode is labelled simulated; a snapshot without usable IR shows an explicit unavailable notice rather than a placeholder board. Rendering uses `@react-three/fiber` + `three` (pnpm catalog) and falls back to the textual geometry summary when WebGL is unavailable.
- **Telemetry:** a WaveDrom-style matrix-scan timing diagram (hand-rolled SVG with a text-alternative event table) and an append-only Renode/QMK console stream with source badges. Preview mode is a labeled fixture capture; daemon mode reports matrix-scan and console telemetry as unavailable rather than faking a stream. The console keeps a bounded 500-line buffer (rendering the latest 200) and its Pause/Clear controls are keyboard operable.

Every snapshot carries a `dataMode` ("demo" | "daemon") and a telemetry notice so the UI cannot pass simulated or placeholder values off as live data. Last-build state is "Unknown" in daemon mode — the RPC has no build-history method — rather than a fabricated timestamp.

Keyboard users can operate every control, dismiss dialogs with Escape, and use the responsive navigation on narrow screens. The demo snapshot makes no claims of real hardware execution; Renode is not represented as USB-HID proof.

## Quality checks

```bash
pnpm --filter @atomc/studio test
pnpm --filter @atomc/studio test:coverage
pnpm --filter @atomc/studio typecheck
pnpm --filter @atomc/studio lint
pnpm --filter @atomc/studio build
pnpm --filter @atomc/studio e2e:install
pnpm --filter @atomc/studio e2e
```

Unit tests use a fake `StudioApi`, never sockets. Playwright runs the built site in Chromium, checks mobile overflow/navigation and runs axe WCAG 2.1 A/AA checks.

## Current scope

The Studio shell and the overview, pipeline, gate, agent, artifact, 3D viewer and telemetry views are implemented. RPC-backed snapshots/build requests are available through an injected trusted host bridge. Studio does not yet bundle an Electron/Tauri host, agent wake runtime, live telemetry streaming from the daemon (the telemetry view is fixture-only until an RPC method exists), sourcing/order mutation UI, or persistence for local preferences. Those remain separate follow-ups; disabled/unavailable controls do not report false success.

The 3D viewer derives geometry from the snapshot's system IR. Daemon mode renders that IR when it is present and says so honestly when it is not; the demo snapshot carries a fixture IR (mirroring `examples/atomc-pad/system_ir.json`) and is labelled simulated.
