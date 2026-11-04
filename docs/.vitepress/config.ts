import { defineConfig } from "vitepress";

const REPO = "https://github.com/dtmirizzi/atomc";

export default defineConfig({
  title: "atomc",
  description:
    "The Atom Compiler — compile declarative hardware descriptions into verified physical systems: circuits → firmware → enclosure and test jig → supply chain.",
  base: "/atomc/",
  cleanUrls: true,
  lastUpdated: true,
  lang: "en-US",
  head: [
    ["meta", { name: "theme-color", content: "#0f766e" }],
    ["link", { rel: "icon", href: "/atomc/favicon.svg", type: "image/svg+xml" }],
  ],
  themeConfig: {
    siteTitle: "atomc",
    logo: "/favicon.svg",
    outline: { level: [2, 3], label: "On this page" },
    search: { provider: "local" },
    editLink: {
      pattern: `${REPO}/edit/main/docs/:path`,
      text: "Edit this page on GitHub",
    },
    socialLinks: [{ icon: "github", link: REPO }],
    footer: {
      message: "Released under the Apache-2.0 License.",
      copyright: "atomc is pre-alpha — interfaces are frozen but features are still landing.",
    },
    nav: [
      { text: "Guide", link: "/guide/", activeMatch: "/guide/" },
      { text: "Architecture", link: "/architecture/", activeMatch: "/architecture/" },
      { text: "Reference", link: "/reference/", activeMatch: "/reference/" },
      { text: "Plugins", link: "/plugins/", activeMatch: "/plugins/" },
      { text: "Examples", link: "/examples/", activeMatch: "/examples/" },
      { text: "Plan", link: "/plan/", activeMatch: "/plan/" },
      { text: "GitHub", link: REPO },
    ],
    sidebar: {
      "/guide/": [
        {
          text: "Guide",
          items: [
            { text: "What is atomc?", link: "/guide/" },
            { text: "Install", link: "/guide/install" },
            { text: "Your first build", link: "/guide/first-build" },
            { text: "Converge with the swarm", link: "/guide/converge" },
          ],
        },
      ],
      "/architecture/": [
        {
          text: "Architecture",
          items: [
            { text: "Overview", link: "/architecture/" },
            { text: "Unified System IR", link: "/architecture/ir" },
            { text: "DAG & gates", link: "/architecture/dag-gates" },
            { text: "Swarm harness", link: "/architecture/swarm" },
            { text: "Distribution", link: "/architecture/distribution" },
            { text: "Testing model", link: "/architecture/testing" },
          ],
        },
        {
          text: "Contracts (frozen)",
          collapsed: false,
          items: [
            { text: "IR schema v0.1", link: "/architecture/contracts/ir-schema" },
            { text: "RPC v0.1", link: "/architecture/contracts/rpc" },
            { text: "Plugin manifest v0.1", link: "/architecture/contracts/plugin-manifest" },
            { text: "GateResult v0.1", link: "/architecture/contracts/gate-result" },
            { text: "Agent protocol v0.1", link: "/architecture/contracts/agent-protocol" },
          ],
        },
      ],
      "/reference/": [
        {
          text: "Reference",
          items: [
            { text: "Overview", link: "/reference/" },
            { text: "IR schema browser", link: "/reference/ir-schema" },
            { text: "CLI", link: "/reference/cli" },
            { text: "RPC methods", link: "/reference/rpc" },
            { text: "Packages", link: "/reference/packages/" },
          ],
        },
      ],
      "/plugins/": [
        {
          text: "Plugins",
          items: [
            { text: "Overview", link: "/plugins/" },
            { text: "Writing a plugin", link: "/plugins/writing-a-plugin" },
            { text: "Manifest reference", link: "/plugins/manifest" },
            { text: "Conformance", link: "/plugins/conformance" },
          ],
        },
      ],
      "/examples/": [
        {
          text: "Examples",
          items: [
            { text: "Overview", link: "/examples/" },
            { text: "atomc-pad (3×3 macropad)", link: "/examples/atomc-pad" },
            { text: "atomc-keeb (4×12 ortho)", link: "/examples/atomc-keeb" },
          ],
        },
      ],
      "/plan/": [
        {
          text: "Plan",
          items: [
            { text: "Status board", link: "/plan/" },
            { text: "Work packages", link: "/plan/status" },
            { text: "Master plan", link: "/plan/master" },
          ],
        },
        {
          text: "Briefs",
          collapsed: true,
          items: [
            { text: "Common rules", link: "/plan/briefs/_common" },
            { text: "WP-0.1 bootstrap", link: "/plan/briefs/WP-0.1" },
            { text: "WP-1.1 core-ir-py", link: "/plan/briefs/WP-1.1" },
            { text: "WP-1.2 core-ir-ts", link: "/plan/briefs/WP-1.2" },
            { text: "WP-1.4 ci-release", link: "/plan/briefs/WP-1.4" },
            { text: "WP-1.5 docs-site", link: "/plan/briefs/WP-1.5" },
            { text: "WP-1.6 example-seed", link: "/plan/briefs/WP-1.6" },
          ],
        },
      ],
    },
  },
  markdown: {
    theme: { light: "github-light", dark: "github-dark" },
  },
});
