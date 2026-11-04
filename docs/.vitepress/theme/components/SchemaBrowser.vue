<script setup lang="ts">
import { withBase } from "vitepress";
import { computed, onMounted, ref } from "vue";
import stub from "../placeholder.schema.json";

type JsonSchema = {
  $defs?: Record<string, JsonSchema>;
  type?: string | string[];
  properties?: Record<string, JsonSchema>;
  required?: string[];
  description?: string;
  items?: JsonSchema;
  $ref?: string;
  anyOf?: JsonSchema[];
  oneOf?: JsonSchema[];
  enum?: unknown[];
  format?: string;
  title?: string;
};

// Seed with the placeholder so the tree server-renders before the generated schema is fetched.
const schema = ref<JsonSchema>(stub as JsonSchema);
const source = ref<"live" | "stub">("stub");
const query = ref("");
const open = ref<Record<string, boolean>>({});

onMounted(async () => {
  try {
    const res = await fetch(withBase("/schema/system_ir.schema.json"));
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    schema.value = (await res.json()) as JsonSchema;
    source.value = "live";
  } catch {
    schema.value = stub as JsonSchema;
    source.value = "stub";
  }
});

// biome-ignore lint/correctness/noUnusedVariables: referenced from the template.
const defs = computed(() => {
  const all = schema.value?.$defs ?? {};
  const q = query.value.trim().toLowerCase();
  if (!q) {
    return all;
  }
  const filtered: Record<string, JsonSchema> = {};
  for (const [name, def] of Object.entries(all)) {
    const fields = Object.keys(def.properties ?? {})
      .join(" ")
      .toLowerCase();
    if (name.toLowerCase().includes(q) || fields.includes(q)) {
      filtered[name] = def;
    }
  }
  return filtered;
});

// biome-ignore lint/correctness/noUnusedVariables: referenced from the template.
function typeOf(sub: JsonSchema | undefined): string {
  if (!sub) {
    return "any";
  }
  if (sub.$ref) {
    return sub.$ref.split("/").pop() ?? "ref";
  }
  if (sub.anyOf) {
    return sub.anyOf.map((s) => typeOf(s)).join(" | ");
  }
  if (sub.oneOf) {
    return sub.oneOf.map((s) => typeOf(s)).join(" | ");
  }
  if (sub.enum) {
    return sub.enum.map((e) => JSON.stringify(e)).join(" | ");
  }
  if (sub.type === "array") {
    return `${typeOf(sub.items)}[]`;
  }
  return Array.isArray(sub.type) ? sub.type.join(" | ") : (sub.type ?? "any");
}

// biome-ignore lint/correctness/noUnusedVariables: referenced from the template.
function fieldEntries(def: JsonSchema): [string, JsonSchema][] {
  return Object.entries(def.properties ?? {});
}

// biome-ignore lint/correctness/noUnusedVariables: referenced from the template.
function isRequired(def: JsonSchema, field: string): boolean {
  return (def.required ?? []).includes(field);
}

// biome-ignore lint/correctness/noUnusedVariables: referenced from the template.
function toggle(name: string) {
  open.value[name] = !(open.value[name] ?? false);
}
</script>

<template>
  <div class="schema-browser">
    <p v-if="source === 'stub'" class="schema-browser__empty">
      The generated <code>system_ir.schema.json</code> has not been built yet — showing a
      hand-written placeholder generated from the v0.1 contract. Run
      <code>pnpm --filter @atomc/docs sync</code> after <code>core-ir</code> emits its schema to see
      the real thing.
    </p>
    <input
      v-model="query"
      class="schema-browser__search"
      type="search"
      placeholder="Filter definitions and fields…"
      aria-label="Filter schema definitions and fields"
    />
    <p v-if="query.trim() && Object.keys(defs).length === 0" class="schema-browser__empty">
      No definitions match “{{ query }}”.
    </p>
    <details
      v-for="(def, name) in defs"
      :key="name"
      class="schema-browser__def"
      :open="query.trim().length > 0 || open[name]"
      @toggle="toggle(name)"
    >
      <summary>
        {{ name }}
        <span class="schema-browser__type">{{ typeOf(def) }}</span>
      </summary>
      <div class="schema-browser__fields">
        <div
          v-for="[field, sub] in fieldEntries(def)"
          :key="field"
          class="schema-browser__field"
        >
          <span class="schema-browser__name">{{ field }}</span>
          <span class="schema-browser__type">{{ typeOf(sub) }}</span>
          <span>
            <span v-if="isRequired(def, field)" class="schema-browser__req">required</span>
          </span>
          <span v-if="sub.description" class="schema-browser__desc">{{ sub.description }}</span>
        </div>
        <p v-if="fieldEntries(def).length === 0" class="schema-browser__empty">
          No declared properties (free-form or scalar definition).
        </p>
      </div>
    </details>
  </div>
</template>
