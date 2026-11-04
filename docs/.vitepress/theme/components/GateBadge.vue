<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    status?: string;
    label?: string;
  }>(),
  { status: "SKIP", label: "" },
);

// biome-ignore lint/correctness/noUnusedVariables: referenced from the template.
const normalized = () => (props.status ?? "SKIP").toUpperCase();
</script>

<template>
  <span class="gate-badge" :class="`gate-badge--${normalized().toLowerCase()}`">
    {{ label || normalized() }}
  </span>
</template>
