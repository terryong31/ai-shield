<script setup lang="ts">
import type { ChatStatus, UIMessage } from 'ai'
import type { ShieldMetadata } from '~/types/workflow'
import { applyChatEvent } from '~/utils/chatStream'

type ShieldMessage = UIMessage<ShieldMetadata>

const { streamChat } = useShieldApi()
const { state: workflowState, resetState } = useShieldWorkflow()
const { mode: securityMode, load: loadMode } = useSecurityMode()

const messages = ref<ShieldMessage[]>([])
const input = ref('')
const status = ref<ChatStatus>('ready')

let controller: AbortController | null = null
let messageCount = 0
const nextId = () => `msg-${Date.now()}-${messageCount++}`

onMounted(loadMode)

const textOf = (message: ShieldMessage) =>
  message.parts
    .filter(part => part.type === 'text')
    .map(part => part.text)
    .join('')

const setText = (message: ShieldMessage, text: string) => {
  message.parts = text ? [{ type: 'text', text }] : []
}

const hasBadges = (message: ShieldMessage) => {
  const meta = message.metadata
  if (!meta) return false
  return meta.mlConfidence != null || meta.dualAgentTriggered || !!meta.toolPolicy || !!meta.blocked
}

const stop = () => controller?.abort()

const sendMessage = async () => {
  const userQuery = input.value.trim()
  if (!userQuery || status.value !== 'ready') return

  input.value = ''
  messages.value.push({ id: nextId(), role: 'user', parts: [{ type: 'text', text: userQuery }] })
  status.value = 'submitted'

  resetState()
  workflowState.value = { ...workflowState.value, query: userQuery, mode: securityMode.value, stage: 'start' }

  controller = new AbortController()
  messages.value.push({ id: nextId(), role: 'assistant', parts: [], metadata: {} })
  const assistantMsg = messages.value[messages.value.length - 1]!

  try {
    let turn = { workflow: workflowState.value, metadata: {}, text: '' }
    const events = streamChat(
      { message: userQuery, mode: securityMode.value },
      controller.signal
    )
    for await (const event of events) {
      status.value = 'streaming'
      turn = applyChatEvent(turn, event)
      workflowState.value = turn.workflow
      assistantMsg.metadata = turn.metadata
      setText(assistantMsg, turn.text)
    }

    if (!assistantMsg.parts.length) {
      setText(assistantMsg, 'Stream ended before a response was produced.')
    }
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      if (!assistantMsg.parts.length) setText(assistantMsg, 'Check stopped.')
    } else {
      const reason = err instanceof Error ? err.message : String(err)
      assistantMsg.metadata = { blocked: true }
      setText(assistantMsg, `Cannot reach the server (${reason}). Check that the API is running, then try again.`)
    }
  } finally {
    controller = null
    status.value = 'ready'
  }
}
</script>

<template>
  <div class="flex h-full w-full min-w-0 flex-col bg-default">
    <div class="chat-scroll relative flex-1 min-h-0 overflow-y-auto">
      <UChatMessages
        :messages="messages"
        :status="status"
        should-auto-scroll
        class="mx-auto max-w-3xl px-4 py-6"
        :user="{ side: 'right', variant: 'soft' }"
        :assistant="{ side: 'left', variant: 'naked' }"
      >
        <template #content="{ message }">
          <div
            v-if="message.role === 'assistant'"
            :class="message.metadata?.blocked ? 'rounded border border-inverted bg-inverted text-inverted px-4 py-3' : ''"
          >
            <p class="whitespace-pre-wrap wrap-break-word">
              {{ textOf(message) }}
            </p>

            <div
              v-if="hasBadges(message)"
              class="mt-3 flex flex-wrap items-center gap-1.5"
            >
              <UBadge
                v-if="message.metadata?.mlConfidence != null"
                color="neutral"
                variant="outline"
                size="sm"
                class="tabular-nums"
                :label="`Risk: ${(message.metadata.mlConfidence * 100).toFixed(0)}%`"
              />
              <UBadge
                v-if="message.metadata?.dualAgentTriggered"
                color="neutral"
                variant="outline"
                size="sm"
                icon="i-lucide-bot"
                label="Agent review"
              />
              <UBadge
                v-if="message.metadata?.toolPolicy"
                color="neutral"
                variant="outline"
                size="sm"
                :label="`Tools: ${message.metadata.toolPolicy}`"
              />
              <UBadge
                v-if="message.metadata?.blocked"
                color="neutral"
                variant="solid"
                size="sm"
                icon="i-lucide-shield-x"
                label="Blocked"
              />
            </div>
          </div>

          <p
            v-else
            class="whitespace-pre-wrap wrap-break-word"
          >
            {{ textOf(message) }}
          </p>
        </template>
      </UChatMessages>
    </div>

    <div class="shrink-0 border-t border-default bg-default px-4 py-3">
      <UChatPrompt
        v-model="input"
        variant="subtle"
        placeholder="Type a message to test the shield..."
        class="mx-auto max-w-3xl"
        @submit="sendMessage"
      >
        <template #footer>
          <span class="text-xs text-dimmed uppercase tracking-wider">
            Mode: {{ securityMode }}
          </span>
          <UChatPromptSubmit
            :status="status"
            color="neutral"
            @stop="stop"
          />
        </template>
      </UChatPrompt>
    </div>
  </div>
</template>
