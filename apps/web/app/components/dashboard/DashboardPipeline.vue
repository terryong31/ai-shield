<script setup lang="ts">
const layers = [{
  title: 'Stage 1: Quick screen',
  icon: 'i-lucide-gauge',
  status: 'LOCAL MODEL',
  description: 'Local TF-IDF and linear model. Scores each message in a few milliseconds at zero cost.'
}, {
  title: 'Stage 2: Safety check',
  icon: 'i-lucide-shield-half',
  status: 'GUARD MODEL',
  description: 'Secondary safety classifier that flags roleplay framing and harmful topics.'
}, {
  title: 'Stage 3: Agent review',
  icon: 'i-lucide-scale',
  status: 'DUAL REVIEW',
  description: 'Analyst and Warden review unclear messages and decide which tools the assistant may use.'
}]
</script>

<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <h2 class="text-sm font-semibold text-highlighted">
        How the check stages work (reference)
      </h2>
      <UBadge
        label="STATIC DOCUMENTATION"
        color="neutral"
        variant="outline"
        size="xs"
      />
    </div>

    <UPageGrid class="lg:grid-cols-3 gap-4">
      <UPageCard
        v-for="layer in layers"
        :key="layer.title"
        :icon="layer.icon"
        :title="layer.title"
        :description="layer.description"
        variant="outline"
        :ui="{
          title: 'text-sm font-medium',
          description: 'text-xs leading-relaxed text-muted'
        }"
      >
        <template #footer>
          <UBadge
            color="neutral"
            variant="outline"
            size="sm"
            :label="layer.status"
          />
        </template>
      </UPageCard>
    </UPageGrid>
  </div>
</template>
