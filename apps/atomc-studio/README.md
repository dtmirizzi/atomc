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
- **Agent team:** specialist cards. In preview mode they are simulated (labeled); in daemon mode sessions and spend are reported as unavailable rather than invented.
- **Artifacts:** output groups. Preview data is fixture-only; daemon-mode stays empty until the RPC reports per-node artifacts.

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

The Studio shell and overview, pipeline, gate, agent and artifact views are implemented. RPC-backed snapshots/build requests are available through an injected trusted host bridge. Studio does not yet bundle an Electron/Tauri host, agent wake runtime, 3D/CAD viewer, telemetry stream, sourcing/order mutation UI, or persistence for local preferences. Those remain separate follow-ups; disabled/unavailable controls do not report false success.
