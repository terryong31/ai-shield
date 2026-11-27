<!-- Settings of one node, opened by a double click, and the replace-model check (spec 0055). State comes from useGamePage. -->
<script setup lang="ts">
import { CUSTOM_LIMITS, DATASET_EXAMPLE } from '~/utils/customSandbox'
import { AGENT_RULE_LIMIT, AGENT_RULE_MAX_CHARS, DEFAULT_LLM_REVIEW_MODEL, DEFAULT_SAFETY_CHECK_MODEL, canAddAgentRule, formatToolName, nodeSupportsThinking } from '~/utils/gameBoard'
import { ML_TRAINING_NOTICE, REPLACE_MODEL_WARNING, formatRemainingTrainings } from '~/utils/mlTraining'

const {
  addCustomTool,
  addCustomWord,
  addRuleFromDraft,
  addSecretPattern,
  agentRules,
  customAgent,
  customAgentErrors,
  customApiKey,
  customDataset,
  customDatasetText,
  customForm,
  customFormSchemaFor,
  customFormState,
  customModel,
  customProvider,
  customWordDraft,
  customWordsList,
  handleTrainCustomMl,
  hasBlockedToolIndex,
  hasTextTransform,
  isAnonymous,
  isCustomMode,
  isNodeModalOpen,
  isReplaceModelConfirmOpen,
  levelAgent,
  llmReviewModelItems,
  mlAlgorithmItems,
  mlCsvDraft,
  mlTrainStats,
  mlTraining,
  nodeModalDescription,
  numberedAgentTools,
  onCustomDatasetFile,
  onDatasetFileChange,
  providerItems,
  removeAgentRule,
  removeCustomTool,
  removeCustomWord,
  removeSecretPattern,
  ruleDraft,
  safetyCheckModelItems,
  secretPatternDraft,
  secretPatternsList,
  selectedCheck,
  selectedNode,
  session,
  toggleBlockedToolIndex,
  toggleTextTransform,
  updateAgentRule,
  updateNodeConfig
} = useGameContext()
</script>

<template>
  <!-- Double-Click Node Settings Modal -->
  <UModal
    v-model:open="isNodeModalOpen"
    :title="selectedNode?.data?.label || ''"
    :description="nodeModalDescription"
    :ui="{
      content: 'sm:max-w-2xl',
      body: '[scrollbar-gutter:stable] [scrollbar-width:thin] [scrollbar-color:var(--ui-border-accented)_transparent]'
    }"
  >
    <template #body>
      <div
        v-if="selectedNode && selectedNode.data"
        class="space-y-7"
      >
        <!-- Input: what the node does -->
        <section
          v-if="selectedNode.data.kind === 'incoming'"
          class="space-y-2"
        >
          <h3 class="text-sm font-semibold text-highlighted">
            What this node does
          </h3>
          <blockquote class="rounded-md border border-default bg-elevated/50 px-4 py-3 text-sm leading-relaxed text-default">
            Connect the node with a tool and the prompt will flow into the next node.
          </blockquote>
        </section>
        <!-- Help Desk (Easy): no model runs, so there is nothing to configure -->
        <section
          v-else-if="selectedNode.data.kind === 'assistant' && !levelAgent"
          class="space-y-2"
        >
          <h3 class="text-sm font-semibold text-highlighted">
            What this node does
          </h3>
          <blockquote class="rounded-md border border-default bg-elevated/50 px-4 py-3 text-sm leading-relaxed text-default">
            Every prompt that reaches the help desk is answered. Stop the injections before they get here.
          </blockquote>
        </section>
        <!-- Protected Agent: system instruction, tools and rules -->
        <template v-else-if="selectedNode.data.kind === 'assistant' && levelAgent">
          <div class="space-y-7">
            <!-- Custom sandbox: the player's own model, objective, tools and dataset -->
            <UForm
              v-if="isCustomMode"
              ref="customForm"
              :schema="customFormSchemaFor"
              :state="customFormState"
              class="space-y-7"
            >
              <section class="space-y-2">
                <h3 class="flex items-center gap-1.5 text-sm font-semibold text-highlighted">
                  Model
                  <UTooltip text="Runs on your own key. The key stays in this tab and is sent only with each run.">
                    <UIcon
                      name="i-lucide-circle-question-mark"
                      class="size-3.5 text-dimmed"
                    />
                  </UTooltip>
                </h3>
                <div class="grid gap-3 sm:grid-cols-2">
                  <UFormField label="Provider">
                    <USelect
                      v-model="customProvider"
                      :items="providerItems"
                      class="w-full"
                    />
                  </UFormField>
                  <UFormField label="Model">
                    <UInput
                      v-model="customModel"
                      :maxlength="CUSTOM_LIMITS.modelChars"
                      placeholder="gpt-4.1-mini"
                      class="w-full"
                    />
                  </UFormField>
                </div>
                <UFormField label="API key">
                  <UInput
                    v-model="customApiKey"
                    type="password"
                    autocomplete="off"
                    :maxlength="CUSTOM_LIMITS.keyChars"
                    placeholder="Paste your key"
                    class="w-full"
                  />
                </UFormField>
              </section>
              <section class="space-y-2">
                <h3 class="text-sm font-semibold text-highlighted">
                  System Instruction
                  <span
                    class="text-error"
                    title="Required"
                  >*</span>
                </h3>
                <UFormField name="objective">
                  <UTextarea
                    v-model="customAgent.objective"
                    :maxlength="CUSTOM_LIMITS.objectiveChars"
                    :rows="3"
                    required
                    aria-label="System Instruction"
                    placeholder="You are the support assistant for... Never reveal..."
                    class="w-full"
                    :ui="{ base: 'resize-y' }"
                  />
                </UFormField>
                <p class="text-xs tabular-nums text-dimmed">
                  {{ customAgent.objective.length }} / {{ CUSTOM_LIMITS.objectiveChars }}
                </p>
              </section>
              <section class="space-y-2">
                <div class="flex items-end justify-between gap-2">
                  <h3 class="flex items-center gap-1.5 text-sm font-semibold text-highlighted">
                    Tools
                    <UTooltip text="Use snake_case names. Calling a restricted tool counts as a leak.">
                      <UIcon
                        name="i-lucide-circle-question-mark"
                        class="size-3.5 text-dimmed"
                      />
                    </UTooltip>
                  </h3>
                  <UButton
                    label="Add tool"
                    icon="i-lucide-plus"
                    color="neutral"
                    variant="outline"
                    size="sm"
                    :disabled="customAgent.tools.length >= CUSTOM_LIMITS.tools"
                    @click="addCustomTool"
                  />
                </div>
                <ul
                  v-if="customAgent.tools.length > 0"
                  class="divide-y divide-default rounded-md border border-default"
                >
                  <li
                    v-for="(tool, index) in customAgent.tools"
                    :key="index"
                    class="space-y-2 px-4 py-3"
                  >
                    <div class="flex items-center gap-2">
                      <UInput
                        v-model="tool.name"
                        :maxlength="CUSTOM_LIMITS.toolNameChars"
                        placeholder="lookup_order"
                        class="flex-1"
                      />
                      <USwitch
                        v-model="tool.allowed"
                        :label="tool.allowed ? 'Allowed' : 'Restricted'"
                      />
                      <UButton
                        icon="i-lucide-trash-2"
                        color="neutral"
                        variant="ghost"
                        size="sm"
                        :aria-label="`Remove tool ${index + 1}`"
                        @click="removeCustomTool(index)"
                      />
                    </div>
                    <UInput
                      v-model="tool.description"
                      :maxlength="CUSTOM_LIMITS.toolDescriptionChars"
                      placeholder="What the tool does"
                      class="w-full"
                    />
                  </li>
                </ul>
                <UEmpty
                  v-else
                  icon="i-lucide-wrench"
                  title="No tools yet"
                  description="Add the tools your agent can call."
                  size="sm"
                  variant="naked"
                />
                <p
                  v-for="message in customAgentErrors"
                  :key="message"
                  class="text-xs text-muted"
                >
                  {{ message }}
                </p>
              </section>
              <section class="space-y-2">
                <h3 class="flex items-center gap-1.5 text-sm font-semibold text-highlighted">
                  Dataset
                  <UTooltip text="Upload or paste CSV rows of text,label,expected_tool. Label is normal or attack; up to 50 rows.">
                    <UIcon
                      name="i-lucide-circle-question-mark"
                      class="size-3.5 text-dimmed"
                    />
                  </UTooltip>
                </h3>
                <div class="space-y-3 rounded-md border border-default p-3">
                  <UInput
                    type="file"
                    accept=".csv,.txt"
                    size="sm"
                    class="w-full"
                    @change="onCustomDatasetFile"
                  />
                  <UFormField name="dataset">
                    <UTextarea
                      v-model="customDatasetText"
                      :rows="5"
                      variant="none"
                      :placeholder="DATASET_EXAMPLE"
                      class="w-full"
                    />
                  </UFormField>
                  <p class="text-xs tabular-nums text-dimmed">
                    {{ customDataset.summary || 'No valid rows yet' }}
                  </p>
                </div>
              </section>
            </UForm>
            <section
              v-if="!isCustomMode"
              class="space-y-2"
            >
              <h3 class="text-sm font-semibold text-highlighted">
                System Instruction
              </h3>
              <blockquote class="rounded-md border border-default bg-elevated/50 px-4 py-3 text-sm leading-relaxed text-default">
                {{ levelAgent?.objective || 'Loading the level objective...' }}
              </blockquote>
            </section>
            <section
              v-if="!isCustomMode && levelAgent && levelAgent.tools.length > 0"
              class="space-y-2"
            >
              <h3 class="flex items-center gap-1.5 text-sm font-semibold text-highlighted">
                Tools
                <UTooltip text="The agent may call allowed tools. Calling a restricted tool counts as a leak.">
                  <UIcon
                    name="i-lucide-circle-question-mark"
                    class="size-3.5 text-dimmed"
                  />
                </UTooltip>
              </h3>
              <ul class="divide-y divide-default rounded-md border border-default">
                <li
                  v-for="tool in levelAgent.tools"
                  :key="tool.name"
                  class="flex items-start gap-3 px-4 py-3"
                >
                  <UIcon
                    :name="tool.allowed ? 'i-lucide-wrench' : 'i-lucide-ban'"
                    class="mt-0.5 size-4 shrink-0 text-muted"
                  />
                  <div class="min-w-0 flex-1 space-y-0.5">
                    <p class="text-sm font-medium text-highlighted">
                      {{ formatToolName(tool.name) }}
                    </p>
                    <p class="text-sm text-muted">
                      {{ tool.description }}
                    </p>
                  </div>
                  <UBadge
                    :icon="tool.dual_use ? 'i-lucide-triangle-alert' : tool.allowed ? 'i-lucide-check' : 'i-lucide-x'"
                    :label="tool.dual_use ? 'Dual-Use' : tool.allowed ? 'Allowed' : 'Restricted'"
                    :color="tool.dual_use ? 'warning' : 'neutral'"
                    :variant="tool.allowed && !tool.dual_use ? 'outline' : 'subtle'"
                    size="sm"
                    class="shrink-0"
                  />
                </li>
              </ul>
            </section>
            <section class="space-y-3">
              <div class="flex items-start justify-between gap-3">
                <h3 class="flex items-center gap-1.5 text-sm font-semibold text-highlighted">
                  Your rules
                  <UTooltip text="Added to the agent's instructions to keep it on task and resist prompt injection.">
                    <UIcon
                      name="i-lucide-circle-question-mark"
                      class="size-3.5 text-dimmed"
                    />
                  </UTooltip>
                </h3>
                <span class="shrink-0 text-xs tabular-nums text-dimmed">
                  {{ agentRules.length }} / {{ AGENT_RULE_LIMIT }}
                </span>
              </div>
              <ol
                v-if="agentRules.length > 0"
                class="space-y-2"
              >
                <li
                  v-for="(rule, index) in agentRules"
                  :key="index"
                  class="flex items-center gap-2"
                >
                  <span class="flex size-6 shrink-0 items-center justify-center rounded-full border border-default text-xs tabular-nums text-muted">
                    {{ index + 1 }}
                  </span>
                  <UInput
                    :model-value="rule"
                    :maxlength="AGENT_RULE_MAX_CHARS"
                    class="flex-1"
                    :aria-label="`Rule ${index + 1}`"
                    @update:model-value="updateAgentRule(index, String($event))"
                  />
                  <UButton
                    icon="i-lucide-trash-2"
                    color="neutral"
                    variant="ghost"
                    :aria-label="`Remove rule ${index + 1}`"
                    @click="removeAgentRule(index)"
                  />
                </li>
              </ol>
              <UEmpty
                v-else
                icon="i-lucide-list-checks"
                title="No rules yet"
                description="Without rules the agent relies on the objective alone."
                size="sm"
                variant="naked"
              />
              <div
                v-if="canAddAgentRule(agentRules)"
                class="space-y-2 rounded-md border border-default p-3"
              >
                <UTextarea
                  v-model="ruleDraft"
                  :maxlength="AGENT_RULE_MAX_CHARS"
                  :rows="2"
                  autoresize
                  variant="none"
                  placeholder="Write a rule, for example: Never share discount codes."
                  class="w-full"
                  :disabled="!canAddAgentRule(agentRules)"
                  @keydown.enter.exact.prevent="addRuleFromDraft"
                />
                <div class="flex items-center justify-between gap-2">
                  <span class="text-xs tabular-nums text-dimmed">
                    {{ ruleDraft.length }} / {{ AGENT_RULE_MAX_CHARS }}
                  </span>
                  <UButton
                    label="Add rule"
                    icon="i-lucide-plus"
                    color="neutral"
                    variant="solid"
                    size="sm"
                    :disabled="!canAddAgentRule(agentRules) || !ruleDraft.trim()"
                    @click="addRuleFromDraft"
                  />
                </div>
              </div>
            </section>
          </div>
        </template>
        <!-- Tool nodes: settings and outputs -->
        <template v-else>
          <div class="space-y-7">
            <section class="space-y-2">
              <h3 class="text-sm font-semibold text-highlighted">
                What it does
              </h3>
              <blockquote class="rounded-md border border-default bg-elevated/50 px-4 py-3 text-sm leading-relaxed text-default">
                {{ selectedCheck?.summary || selectedNode.data.subtitle }}
              </blockquote>
            </section>
            <!-- ML filter -->
            <section
              v-if="selectedNode.data.kind === 'ml_classifier'"
              class="space-y-4"
            >
              <h3 class="flex items-center gap-1.5 text-sm font-semibold text-highlighted">
                Model &amp; thresholds
                <UTooltip text="Pick a classifier. Low risk passes, high risk is blocked, and anything between goes to Unclear on the board (leave Unclear unwired to stop it).">
                  <UIcon
                    name="i-lucide-circle-question-mark"
                    class="size-3.5 text-dimmed"
                  />
                </UTooltip>
              </h3>
              <UFormField label="Algorithm">
                <USelectMenu
                  :model-value="String(selectedNode.data.config.algorithm || 'tfidf')"
                  :items="mlAlgorithmItems"
                  value-key="value"
                  :search-input="false"
                  class="w-full"
                  @update:model-value="updateNodeConfig('algorithm', $event)"
                />
              </UFormField>
              <div class="grid gap-3 sm:grid-cols-2">
                <UFormField label="Pass below">
                  <UInputNumber
                    :model-value="Number(selectedNode.data.config.safe_threshold ?? 0.3)"
                    :min="0"
                    :max="Number(selectedNode.data.config.block_threshold ?? selectedNode.data.config.threshold ?? 0.75) - 0.05"
                    :step="0.05"
                    :format-options="{ style: 'percent' }"
                    class="w-full"
                    @update:model-value="updateNodeConfig('safe_threshold', $event)"
                  />
                </UFormField>
                <UFormField label="Block at or above">
                  <UInputNumber
                    :model-value="Number(selectedNode.data.config.block_threshold ?? selectedNode.data.config.threshold ?? 0.75)"
                    :min="Number(selectedNode.data.config.safe_threshold ?? 0.3) + 0.05"
                    :max="1"
                    :step="0.05"
                    :format-options="{ style: 'percent' }"
                    class="w-full"
                    @update:model-value="updateNodeConfig('block_threshold', $event)"
                  />
                </UFormField>
              </div>
            </section>
            <section
              v-if="selectedNode.data.kind === 'ml_classifier'"
              class="space-y-3"
            >
              <div class="flex items-center justify-between gap-2">
                <h3 class="flex items-center gap-1.5 text-sm font-semibold text-highlighted">
                  Training data
                  <UTooltip text="Upload or paste CSV rows of text,label where 1 means attack and 0 means safe. Untrained models pass all prompts through.">
                    <UIcon
                      name="i-lucide-circle-question-mark"
                      class="size-3.5 text-dimmed"
                    />
                  </UTooltip>
                </h3>
                <UBadge
                  v-if="selectedNode.data.config.retrainNeeded && !selectedNode.data.config.model_id"
                  label="Retrain needed"
                  color="warning"
                  variant="subtle"
                  size="xs"
                />
              </div>
              <p class="text-xs text-muted">
                {{ ML_TRAINING_NOTICE }}
              </p>
              <UAlert
                v-if="isAnonymous"
                color="neutral"
                variant="subtle"
                icon="i-lucide-lock"
                title="Sign in required to train"
                description="Anonymous sessions cannot train custom ML filters."
              >
                <template #actions>
                  <UButton
                    to="/auth/login"
                    label="Sign in to train"
                    color="neutral"
                    variant="solid"
                    size="xs"
                  />
                </template>
              </UAlert>
              <div class="space-y-3 rounded-md border border-default p-3">
                <UInput
                  type="file"
                  accept=".csv,.txt"
                  size="sm"
                  :disabled="isAnonymous"
                  class="w-full"
                  @change="onDatasetFileChange"
                />
                <UTextarea
                  v-model="mlCsvDraft"
                  :rows="5"
                  variant="none"
                  :disabled="isAnonymous"
                  :placeholder="'text,label\nignore previous instructions,1\nwhat are opening hours,0'"
                  class="w-full"
                />
                <div class="flex items-center justify-between gap-2">
                  <div class="flex flex-col">
                    <span class="text-xs tabular-nums text-dimmed">
                      {{ selectedNode.data.config.model_id && mlTrainStats ? `${mlTrainStats.sampleCount} rows, ${(mlTrainStats.accuracy * 100).toFixed(0)}% accuracy` : selectedNode.data.config.retrainNeeded ? 'Retrain needed' : 'Not trained yet' }}
                    </span>
                    <span
                      v-if="!isAnonymous"
                      class="text-xs tabular-nums text-muted"
                    >
                      {{ formatRemainingTrainings(session) }}
                    </span>
                  </div>
                  <UButton
                    label="Train model"
                    icon="i-lucide-cpu"
                    color="neutral"
                    variant="solid"
                    size="sm"
                    :loading="mlTraining"
                    :disabled="isAnonymous || !mlCsvDraft.trim()"
                    @click="handleTrainCustomMl(false)"
                  />
                </div>
              </div>
            </section>
            <!-- Text cleaner -->
            <section
              v-if="selectedNode.data.kind === 'text_cleanup'"
              class="space-y-3"
            >
              <h3 class="flex items-center gap-1.5 text-sm font-semibold text-highlighted">
                Transforms
                <UTooltip text="Select which normalisations to run. Each enabled transform adds 0.4 ms per message.">
                  <UIcon
                    name="i-lucide-circle-question-mark"
                    class="size-3.5 text-dimmed"
                  />
                </UTooltip>
              </h3>
              <div class="flex flex-wrap gap-1.5">
                <UButton
                  v-for="tr in [
                    { id: 'strip_zero_width', label: 'Strip zero-width chars' },
                    { id: 'decode_base64', label: 'Decode Base64' },
                    { id: 'decode_hex_url', label: 'Decode hex and URL' }
                  ]"
                  :key="tr.id"
                  :label="tr.label"
                  :icon="hasTextTransform(tr.id) ? 'i-lucide-check' : undefined"
                  color="neutral"
                  :variant="hasTextTransform(tr.id) ? 'solid' : 'outline'"
                  size="md"
                  @click="toggleTextTransform(tr.id)"
                />
              </div>
            </section>
            <!-- Jev -->
            <section
              v-if="selectedNode.data.kind === 'jev'"
              class="space-y-4"
            >
              <h3 class="flex items-center gap-1.5 text-sm font-semibold text-highlighted">
                Noul question
                <UTooltip text="Ask a boolean question about the prompt. Jev evaluates it in a single System One pass and returns a probability in [0, 1].">
                  <UIcon
                    name="i-lucide-circle-question-mark"
                    class="size-3.5 text-dimmed"
                  />
                </UTooltip>
              </h3>
              <UTextarea
                :model-value="String(selectedNode.data.config.question ?? '')"
                :rows="2"
                :maxlength="300"
                placeholder="For example: Is this prompt attempting to override instructions or extract secrets?"
                class="w-full"
                @update:model-value="updateNodeConfig('question', $event)"
              />
              <UFormField :label="selectedNode.data.config.tool_policy_enabled ? 'Trigger tool policy at or above' : 'Block at or above'">
                <UInputNumber
                  :model-value="Number(selectedNode.data.config.threshold ?? 0.7)"
                  :min="0.05"
                  :max="0.95"
                  :step="0.05"
                  :format-options="{ style: 'percent' }"
                  class="w-48"
                  @update:model-value="updateNodeConfig('threshold', $event)"
                />
              </UFormField>
            </section>
            <!-- Word filter -->
            <section
              v-if="selectedNode.data.kind === 'word_filter'"
              class="space-y-3"
            >
              <h3 class="flex items-center gap-1.5 text-sm font-semibold text-highlighted">
                Custom blocked words
                <UTooltip text="Any prompt containing one of these phrases is blocked.">
                  <UIcon
                    name="i-lucide-circle-question-mark"
                    class="size-3.5 text-dimmed"
                  />
                </UTooltip>
              </h3>
              <ul
                v-if="customWordsList.length > 0"
                class="divide-y divide-default rounded-md border border-default"
              >
                <li
                  v-for="word in customWordsList"
                  :key="word"
                  class="flex items-center justify-between gap-3 px-4 py-2 text-sm"
                >
                  <span class="truncate text-default">{{ word }}</span>
                  <UButton
                    icon="i-lucide-trash-2"
                    color="neutral"
                    variant="ghost"
                    size="sm"
                    :aria-label="`Remove ${word}`"
                    @click="removeCustomWord(word)"
                  />
                </li>
              </ul>
              <div class="flex items-center gap-2 rounded-md border border-default p-2">
                <UInput
                  v-model="customWordDraft"
                  placeholder="Add a phrase, for example: secret code"
                  variant="none"
                  class="flex-1"
                  @keydown.enter="addCustomWord"
                />
                <UButton
                  label="Add word"
                  icon="i-lucide-plus"
                  color="neutral"
                  variant="solid"
                  size="sm"
                  :disabled="!customWordDraft.trim()"
                  @click="addCustomWord"
                />
              </div>
            </section>
            <!-- Secret scanner -->
            <section
              v-if="selectedNode.data.kind === 'secret_scan'"
              class="space-y-3"
            >
              <h3 class="flex items-center gap-1.5 text-sm font-semibold text-highlighted">
                Regex patterns
                <UTooltip text="Case-insensitive regular expressions to block, such as sk-[a-z0-9]{6,} or password|secret.">
                  <UIcon
                    name="i-lucide-circle-question-mark"
                    class="size-3.5 text-dimmed"
                  />
                </UTooltip>
              </h3>
              <ul
                v-if="secretPatternsList.length > 0"
                class="divide-y divide-default rounded-md border border-default"
              >
                <li
                  v-for="pattern in secretPatternsList"
                  :key="pattern"
                  class="flex items-center justify-between gap-3 px-4 py-2 text-sm"
                >
                  <span class="truncate text-default">{{ pattern }}</span>
                  <UButton
                    icon="i-lucide-trash-2"
                    color="neutral"
                    variant="ghost"
                    size="sm"
                    :aria-label="`Remove ${pattern}`"
                    @click="removeSecretPattern(pattern)"
                  />
                </li>
              </ul>
              <div class="flex items-center gap-2 rounded-md border border-default p-2">
                <UInput
                  v-model="secretPatternDraft"
                  placeholder="Add a regex, for example: password|secret\s+code"
                  variant="none"
                  class="flex-1"
                  @keydown.enter="addSecretPattern"
                />
                <UButton
                  label="Add regex"
                  icon="i-lucide-plus"
                  color="neutral"
                  variant="solid"
                  size="sm"
                  :disabled="!secretPatternDraft.trim()"
                  @click="addSecretPattern"
                />
              </div>
            </section>
            <!-- Length limit -->
            <section
              v-if="selectedNode.data.kind === 'length_limit'"
              class="space-y-3"
            >
              <h3 class="flex items-center gap-1.5 text-sm font-semibold text-highlighted">
                Maximum length
                <UTooltip text="Prompts longer than this are blocked before they can stuff the context.">
                  <UIcon
                    name="i-lucide-circle-question-mark"
                    class="size-3.5 text-dimmed"
                  />
                </UTooltip>
              </h3>
              <UFormField label="Characters">
                <UInputNumber
                  :model-value="Number(selectedNode.data.config.max_chars ?? 240)"
                  :min="20"
                  :max="4000"
                  :step="20"
                  class="w-48"
                  @update:model-value="updateNodeConfig('max_chars', $event)"
                />
              </UFormField>
            </section>
            <!-- Safety check: dedicated safety/guardrail models only -->
            <section
              v-if="selectedNode.data.kind === 'safety_check'"
              class="space-y-3"
            >
              <h3 class="flex items-center gap-1.5 text-sm font-semibold text-highlighted">
                Safety guardrail model
                <UTooltip text="Only safety-specific guardrail models are available for Safety check.">
                  <UIcon
                    name="i-lucide-circle-question-mark"
                    class="size-3.5 text-dimmed"
                  />
                </UTooltip>
              </h3>
              <USelectMenu
                :model-value="String(selectedNode.data.config.model || DEFAULT_SAFETY_CHECK_MODEL)"
                :items="safetyCheckModelItems"
                value-key="value"
                class="w-full"
                @update:model-value="updateNodeConfig('model', $event)"
              />
              <USwitch
                v-if="nodeSupportsThinking(selectedNode.data.kind, String(selectedNode.data.config.model || DEFAULT_SAFETY_CHECK_MODEL))"
                color="neutral"
                :model-value="Boolean(selectedNode.data.config.thinking)"
                label="Thinking"
                description="The model reasons before it answers. It catches more attacks but costs more tokens and time."
                @update:model-value="updateNodeConfig('thinking', Boolean($event))"
              />
            </section>
            <!-- Tool policy extension for Jev and Safety check -->
            <section
              v-if="selectedNode.data.kind === 'jev' || selectedNode.data.kind === 'safety_check'"
              class="space-y-3"
            >
              <h3 class="flex items-center gap-1.5 text-sm font-semibold text-highlighted">
                Tool policy
                <UTooltip text="When enabled, triggering this node switches off the selected tools on the final LangGraph agent and lets the prompt pass.">
                  <UIcon
                    name="i-lucide-circle-question-mark"
                    class="size-3.5 text-dimmed"
                  />
                </UTooltip>
              </h3>
              <div class="space-y-3">
                <USwitch
                  color="neutral"
                  :model-value="Boolean(selectedNode.data.config.tool_policy_enabled)"
                  label="Switch off agent tools instead of blocking prompt"
                  @update:model-value="updateNodeConfig('tool_policy_enabled', Boolean($event))"
                />
                <div
                  v-if="Boolean(selectedNode.data.config.tool_policy_enabled)"
                  class="space-y-2 pt-3"
                >
                  <div
                    v-if="numberedAgentTools.length > 0"
                    class="grid gap-2 sm:grid-cols-2"
                  >
                    <UCheckbox
                      v-for="item in numberedAgentTools"
                      :key="item.index"
                      color="neutral"
                      :model-value="hasBlockedToolIndex(item.index, item.name)"
                      :label="item.label"
                      @update:model-value="toggleBlockedToolIndex(item.index, item.name)"
                    />
                  </div>
                  <p
                    v-else
                    class="text-xs text-muted"
                  >
                    This level has no final agent tools to switch off.
                  </p>
                </div>
              </div>
            </section>
            <!-- LLM review: general LLM + custom review instructions + dynamic tool policy -->
            <section
              v-if="selectedNode.data.kind === 'llm_review'"
              class="space-y-4"
            >
              <div class="space-y-2">
                <h3 class="flex items-center gap-1.5 text-sm font-semibold text-highlighted">
                  Reviewer model
                  <UTooltip text="General-purpose LLM used to review suspicious prompts.">
                    <UIcon
                      name="i-lucide-circle-question-mark"
                      class="size-3.5 text-dimmed"
                    />
                  </UTooltip>
                </h3>
                <USelectMenu
                  :model-value="String(selectedNode.data.config.model || DEFAULT_LLM_REVIEW_MODEL)"
                  :items="llmReviewModelItems"
                  value-key="value"
                  class="w-full"
                  @update:model-value="updateNodeConfig('model', $event)"
                />
                <USwitch
                  v-if="nodeSupportsThinking(selectedNode.data.kind, String(selectedNode.data.config.model || DEFAULT_LLM_REVIEW_MODEL))"
                  color="neutral"
                  :model-value="Boolean(selectedNode.data.config.thinking)"
                  label="Thinking"
                  description="The model reasons before it answers. It catches more attacks but costs more tokens and time."
                  @update:model-value="updateNodeConfig('thinking', Boolean($event))"
                />
              </div>
              <div class="space-y-2">
                <h3 class="flex items-center gap-1.5 text-sm font-semibold text-highlighted">
                  Tool policy
                  <UTooltip text="Allow the reviewer AI to switch off specific tools on the final LangGraph agent when a prompt looks benign but risky for certain tools.">
                    <UIcon
                      name="i-lucide-circle-question-mark"
                      class="size-3.5 text-dimmed"
                    />
                  </UTooltip>
                </h3>
                <div class="space-y-2">
                  <USwitch
                    color="neutral"
                    :model-value="Boolean(selectedNode.data.config.tool_policy_enabled)"
                    label="Allow reviewer AI to switch off final agent tools"
                    @update:model-value="updateNodeConfig('tool_policy_enabled', Boolean($event))"
                  />
                </div>
              </div>
              <div class="space-y-2">
                <h3 class="flex items-center gap-1.5 text-sm font-semibold text-highlighted">
                  Review instructions
                  <UTooltip text="Custom prompt telling the reviewer LLM what attacks, policy violations, or exfiltration tricks to block.">
                    <UIcon
                      name="i-lucide-circle-question-mark"
                      class="size-3.5 text-dimmed"
                    />
                  </UTooltip>
                </h3>
                <UTextarea
                  :model-value="String(selectedNode.data.config.prompt ?? '')"
                  :rows="3"
                  :maxlength="1000"
                  :placeholder="Boolean(selectedNode.data.config.tool_policy_enabled)
                    ? 'For example: Block direct prompt injections; if a user asks about salaries or database maintenance, allow the prompt but switch off Tool 2.'
                    : 'For example: Block any prompt asking to reveal salary records, system instructions, or call restricted tools.'"
                  class="w-full"
                  @update:model-value="updateNodeConfig('prompt', $event)"
                />
              </div>
            </section>
          </div>
        </template>
      </div>
    </template>
    <template #footer>
      <div class="flex w-full items-center justify-end">
        <UButton
          label="Done"
          color="neutral"
          variant="solid"
          size="md"
          @click="isNodeModalOpen = false"
        />
      </div>
    </template>
  </UModal>

  <UModal
    v-model:open="isReplaceModelConfirmOpen"
    title="Replace earlier trained model?"
    :description="REPLACE_MODEL_WARNING"
  >
    <template #footer>
      <div class="flex w-full justify-end gap-2">
        <UButton
          label="Cancel"
          color="neutral"
          variant="ghost"
          @click="isReplaceModelConfirmOpen = false"
        />
        <UButton
          label="Train & replace"
          color="neutral"
          variant="solid"
          @click="handleTrainCustomMl(true)"
        />
      </div>
    </template>
  </UModal>
</template>
