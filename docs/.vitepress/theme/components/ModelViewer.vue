<script setup lang="ts">
import { onMounted, ref } from "vue";

const props = withDefaults(
  defineProps<{
    src?: string;
    alt?: string;
    poster?: string;
    cameraControls?: boolean;
    autoRotate?: boolean;
  }>(),
  {
    src: "",
    alt: "Interactive 3D model",
    poster: "",
    cameraControls: true,
    autoRotate: false,
  },
);

const loaded = ref(false);
const failed = ref(false);

const CDN = "https://unpkg.com/@google/model-viewer@4/dist/model-viewer.min.js";

onMounted(async () => {
  if (!props.src) {
    return;
  }
  if (!customElements.get("model-viewer")) {
    try {
      await new Promise<void>((resolve, reject) => {
        const script = document.createElement("script");
        script.type = "module";
        script.src = CDN;
        script.onload = () => resolve();
        script.onerror = () => reject(new Error("model-viewer failed to load"));
        document.head.appendChild(script);
      });
    } catch {
      failed.value = true;
      return;
    }
  }
  loaded.value = true;
});
</script>

<template>
  <div class="model-viewer-wrap">
    <p v-if="!src" class="model-viewer-placeholder">
      No model supplied. Example artifacts (plate, case, pogo jig <code>.glb</code>) land in Phase 4
      — this viewer will render them here.
    </p>
    <p v-else-if="failed" class="model-viewer-placeholder">
      The <code>model-viewer</code> web component could not be loaded from the CDN.
    </p>
    <model-viewer
      v-else-if="loaded"
      :src="src"
      :alt="alt"
      :poster="poster || undefined"
      :camera-controls="cameraControls"
      :auto-rotate="autoRotate"
      shadow-intensity="1"
      exposure="1"
      interaction-prompt="auto"
    />
  </div>
</template>
