<script setup lang="ts">
import {
  checkPasswordStrength,
  passwordStrengthColor,
  passwordStrengthScore,
  passwordStrengthText
} from '~/utils/playerAuth'

const props = withDefaults(defineProps<{
  id?: string
  placeholder?: string
  autocomplete?: string
}>(), {
  id: 'password',
  placeholder: 'Password',
  autocomplete: 'new-password'
})

const password = defineModel<string>({ default: '' })
const show = ref(false)

const strength = computed(() => checkPasswordStrength(password.value))
const score = computed(() => passwordStrengthScore(password.value))
const color = computed(() => passwordStrengthColor(score.value))
const text = computed(() => passwordStrengthText(score.value))
</script>

<template>
  <div class="space-y-2">
    <UInput
      :id="props.id"
      v-model="password"
      :placeholder="props.placeholder"
      :autocomplete="props.autocomplete"
      :color="color"
      :type="show ? 'text' : 'password'"
      :aria-invalid="score < 4"
      aria-describedby="password-strength"
      :ui="{ trailing: 'pe-1' }"
      class="w-full"
    >
      <template #trailing>
        <UButton
          color="neutral"
          variant="link"
          size="sm"
          :icon="show ? 'i-lucide-eye-off' : 'i-lucide-eye'"
          :aria-label="show ? 'Hide password' : 'Show password'"
          :aria-pressed="show"
          :aria-controls="props.id"
          @click="show = !show"
        />
      </template>
    </UInput>

    <UProgress
      :color="color"
      :indicator="text"
      :model-value="score"
      :max="4"
      size="sm"
    />

    <p
      id="password-strength"
      class="text-sm font-medium"
    >
      {{ text }}. Must contain:
    </p>

    <ul
      class="space-y-1"
      aria-label="Password requirements"
    >
      <li
        v-for="(req, index) in strength"
        :key="index"
        class="flex items-center gap-0.5"
        :class="req.met ? 'text-success' : 'text-muted'"
      >
        <UIcon
          :name="req.met ? 'i-lucide-circle-check' : 'i-lucide-circle-x'"
          class="size-4 shrink-0"
        />

        <span class="text-xs font-light">
          {{ req.text }}
          <span class="sr-only">
            {{ req.met ? ' - Requirement met' : ' - Requirement not met' }}
          </span>
        </span>
      </li>
    </ul>
  </div>
</template>
