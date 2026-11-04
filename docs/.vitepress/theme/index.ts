import type { Theme } from "vitepress";
import DefaultTheme from "vitepress/theme";
import GateBadge from "./components/GateBadge.vue";
import ModelViewer from "./components/ModelViewer.vue";
import SchemaBrowser from "./components/SchemaBrowser.vue";
import "./style.css";

export default {
  extends: DefaultTheme,
  enhanceApp({ app }) {
    app.component("SchemaBrowser", SchemaBrowser);
    app.component("ModelViewer", ModelViewer);
    app.component("GateBadge", GateBadge);
  },
} satisfies Theme;
