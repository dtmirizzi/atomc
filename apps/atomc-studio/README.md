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

- **Overview:** IR revision, gate health, build status, spend-limited agents and recent activity.
- **Build graph:** ordered DAG nodes and live status.
- **Gate results:** filter PASS/FAIL/SKIP/ERROR and inspect owner/revision/details.
- **Agent team:** specialist scope, current work, status and budget progress.
- **Artifacts:** output groups from the selected build snapshot.

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
