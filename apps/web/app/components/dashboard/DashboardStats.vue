<script setup lang="ts">
import type { Stats } from '~/types/api'

const { getStats } = useShieldApi()
const toast = useToast()

const metrics = ref<Stats>({ total: 0, blocked: 0, allowed: 0, block_rate: 0 })
const loading = ref(true)

const fetchMetrics = async () => {
  loading.value = true
  try {
    metrics.value = await getStats()
  } catch (err) {
    console.error('Failed to fetch metrics:', err)
    toast.add({
      title: 'Stats unavailable',
      description: 'Cannot reach the server. Check that the API is running.',
      icon: 'i-lucide-triangle-alert',
      color: 'neutral'
    })
  } finally {
    loading.value = false
  }
}

const stats = computed(() => [{
  key: 'total',
  title: 'Messages checked',
  value: String(metrics.value.total),
  description: 'Total messages evaluated by the gateway'
}, {
  key: 'blocked',
  title: 'Blocked',
  value: String(metrics.value.blocked),
  description: 'Harmful messages stopped before reaching the assistant'
}, {
  key: 'safe',
  title: 'Allowed',
  value: String(metrics.value.allowed),
  description: 'Normal messages answered by the assistant'
}, {
  key: 'rate',
  title: 'Block rate',
  value: `${metrics.value.block_rate}%`,
  description: 'Share of messages blocked'
}])

onMounted(fetchMetrics)

defineExpose({ refresh: fetchMetrics })
</script>

<template>
  <UPageGrid class="lg:grid-cols-4 gap-4">
    <UPageCard
      v-for="stat in stats"
      :key="stat.key"
      :title="stat.title"
      variant="outline"
      :ui="{
        container: 'gap-y-1.5',
        wrapper: 'items-start',
        title: 'text-muted text-xs uppercase tracking-wider'
      }"
    >
      <USkeleton
        v-if="loading"
        class="h-8 w-20"
      />
      <span
        v-else
        class="text-2xl font-semibold tabular-nums text-highlighted"
      >
        {{ stat.value }}
      </span>

      <p class="text-xs text-muted">
        {{ stat.description }}
      </p>
    </UPageCard>
  </UPageGrid>
</template>
