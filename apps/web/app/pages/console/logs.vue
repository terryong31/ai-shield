<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'
import type { AuditRecord } from '~/types/api'
import { applyReview, filterAuditRecords } from '~/utils/audit'
import { formatConfidence } from '~/utils/format'
import { resolveConsoleAccess } from '~/utils/gameBoard'

definePageMeta({
  path: '/_console/logs',
  layout: 'dashboard'
})

const { status, openModal } = usePassphrase()
const { listRequests, sendFeedback } = useShieldApi()
const toast = useToast()

const access = computed(() => resolveConsoleAccess(status.value))

const logs = ref<AuditRecord[]>([])
const loading = ref(true)
const searchText = ref('')
const actionFilter = ref<'all' | 'ALLOWED' | 'BLOCKED'>('all')
const reviewFilter = ref<'all' | 'reviewed' | 'unreviewed'>('all')

const filteredLogs = computed(() =>
  filterAuditRecords(logs.value, {
    action: actionFilter.value,
    review: reviewFilter.value,
    text: searchText.value
  })
)

const columns: TableColumn<AuditRecord>[] = [
  { accessorKey: 'created_at', header: 'Time' },
  { accessorKey: 'query', header: 'Message' },
  { accessorKey: 'action', header: 'Decision' },
  { accessorKey: 'layer', header: 'Stage' },
  { id: 'confidence', header: 'Risk score' },
  { id: 'review', header: 'Human review' }
]

const fetchLogs = async () => {
  loading.value = true
  try {
    logs.value = await listRequests(50)
  } catch (err) {
    console.error('Error fetching logs:', err)
    toast.add({
      title: 'Audit log unavailable',
      description: 'Cannot reach the server. Check that the API is running.',
      icon: 'i-lucide-triangle-alert',
      color: 'neutral'
    })
  } finally {
    loading.value = false
  }
}

const submitReview = async (log: AuditRecord, label: 0 | 1) => {
  try {
    await sendFeedback({ request_id: log.id, prompt: log.query, human_label: label })
    logs.value = logs.value.map(item => (item.id === log.id ? applyReview(item, label) : item))

    toast.add({
      title: 'Review recorded',
      description: `Message marked as ${label === 0 ? 'safe' : 'harmful'}.`,
      icon: 'i-lucide-check',
      color: 'neutral'
    })
  } catch (err) {
    console.error('Error sending review:', err)
    toast.add({
      title: 'Review failed',
      description: 'The feedback endpoint could not be reached.',
      icon: 'i-lucide-triangle-alert',
      color: 'neutral'
    })
  }
}

onMounted(fetchLogs)
</script>

<template>
  <UDashboardPanel id="console-logs">
    <template #header>
      <UDashboardNavbar title="Audit logs">
        <template #leading>
          <UDashboardSidebarCollapse />
        </template>

        <template #right>
          <UButton
            v-if="access.allowed"
            label="Refresh"
            icon="i-lucide-refresh-cw"
            color="neutral"
            variant="subtle"
            :loading="loading"
            @click="fetchLogs"
          />
        </template>
      </UDashboardNavbar>

      <UDashboardToolbar v-if="access.allowed">
        <template #left>
          <div class="flex flex-wrap items-center gap-2">
            <UInput
              v-model="searchText"
              icon="i-lucide-search"
              placeholder="Search messages, reasons, or stages..."
              size="sm"
              class="w-64"
            />
            <USelect
              v-model="actionFilter"
              :items="[
                { label: 'All decisions', value: 'all' },
                { label: 'Allowed', value: 'ALLOWED' },
                { label: 'Blocked', value: 'BLOCKED' }
              ]"
              size="sm"
              class="w-36"
            />
            <USelect
              v-model="reviewFilter"
              :items="[
                { label: 'All review states', value: 'all' },
                { label: 'Reviewed', value: 'reviewed' },
                { label: 'Unreviewed', value: 'unreviewed' }
              ]"
              size="sm"
              class="w-40"
            />
          </div>
        </template>
      </UDashboardToolbar>
    </template>

    <template #body>
      <div
        v-if="!access.allowed"
        class="py-16"
      >
        <UEmpty
          icon="i-lucide-lock"
          title="Site admin access required"
          description="Enter the admin passphrase to inspect audit logs and submit reviewer labels."
        >
          <template #actions>
            <UButton
              label="Enter admin passphrase"
              icon="i-lucide-key-round"
              color="neutral"
              variant="solid"
              @click="openModal"
            />
          </template>
        </UEmpty>
      </div>

      <UTable
        v-else-if="filteredLogs.length > 0"
        :data="filteredLogs"
        :columns="columns"
        :loading="loading"
        class="shrink-0"
        :ui="{
          base: 'table-fixed border-separate border-spacing-0',
          thead: '[&>tr]:bg-elevated/50 [&>tr]:after:content-none',
          tbody: '[&>tr]:last:[&>td]:border-b-0',
          th: 'py-2 first:rounded-l-lg last:rounded-r-lg border-y border-default first:border-l last:border-r',
          td: 'border-b border-default'
        }"
      >
        <template #created_at-cell="{ row }">
          <span class="text-sm text-muted whitespace-nowrap tabular-nums">
            {{ new Date(row.original.created_at).toLocaleString() }}
          </span>
        </template>

        <template #query-cell="{ row }">
          <div class="max-w-md">
            <p class="text-base font-medium text-highlighted truncate">
              {{ row.original.query }}
            </p>
            <p
              v-if="row.original.reason"
              class="text-sm text-muted truncate mt-0.5"
            >
              {{ row.original.reason }}
            </p>
          </div>
        </template>

        <template #action-cell="{ row }">
          <UBadge
            :variant="row.original.action === 'BLOCKED' ? 'solid' : 'outline'"
            color="neutral"
            size="md"
            :label="row.original.action"
          />
        </template>

        <template #layer-cell="{ row }">
          <UBadge
            color="neutral"
            variant="outline"
            size="md"
            :label="row.original.layer || 'N/A'"
          />
        </template>

        <template #confidence-cell="{ row }">
          <span class="text-sm text-muted tabular-nums">
            {{ formatConfidence(row.original.metadata?.mlConfidence) }}
          </span>
        </template>

        <template #review-cell="{ row }">
          <UBadge
            v-if="row.original.reviewed"
            color="neutral"
            variant="outline"
            size="md"
            icon="i-lucide-check"
            :label="`Reviewed (${row.original.human_label === 1 ? 'Harmful' : 'Safe'})`"
          />
          <div
            v-else
            class="flex items-center gap-1.5"
          >
            <UButton
              label="Mark as safe"
              icon="i-lucide-check"
              size="sm"
              color="neutral"
              variant="outline"
              @click="submitReview(row.original, 0)"
            />
            <UButton
              label="Mark as harmful"
              icon="i-lucide-shield-x"
              size="sm"
              color="neutral"
              variant="outline"
              @click="submitReview(row.original, 1)"
            />
          </div>
        </template>
      </UTable>

      <div
        v-else
        class="py-12"
      >
        <UEmpty
          icon="i-lucide-scroll-text"
          title="No matching audit records"
          description="Send a message or change your search filters to see audit records."
        />
      </div>
    </template>
  </UDashboardPanel>
</template>
