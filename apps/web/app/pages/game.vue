<script setup lang="ts">
import { computed } from 'vue'
import { isValidLevelId } from '~/utils/gameBoard'
import { TWITTER_CARD_ALT, TWITTER_CARD_PATH, resolveSiteUrl } from '~/utils/seo'
import { GAME_PAGE, useGamePage } from '~/composables/useGamePage'

const game = useGamePage()
provide(GAME_PAGE, game)
const route = useRoute()

const {
  currentLevel,
  handleReturnClick,
  highScore,
  highStars,
  isBriefingOpen,
  isCustomMode,
  isLoggedIn,
  isPaid,
  isResultsOpen,
  waveScore
} = game

const runtimeConfig = useRuntimeConfig()
const siteUrl = computed(() => resolveSiteUrl(runtimeConfig.public.siteUrl))
const gameSeoDescription = computed(() =>
  currentLevel.value.summary
  || 'Build and test a layered prompt-injection defence workflow with word filters, ML classifiers, safety guardrails, and LLM reviewers on ai-shield.'
)

const gameSeoUrl = computed(() => {
  const q = route.query.level
  if (isValidLevelId(q)) {
    return `${siteUrl.value}/game?level=${q}`
  }
  return `${siteUrl.value}/game`
})

useSeoMeta({
  title: () => currentLevel.value.title,
  description: () => gameSeoDescription.value,
  ogTitle: () => `${currentLevel.value.title} | ai-shield`,
  ogDescription: () => gameSeoDescription.value,
  ogType: 'website',
  ogSiteName: 'ai-shield',
  ogUrl: () => gameSeoUrl.value,
  ogImage: () => `${siteUrl.value}${TWITTER_CARD_PATH}`,
  ogImageAlt: TWITTER_CARD_ALT,
  ogImageWidth: 1200,
  ogImageHeight: 630,
  twitterCard: 'summary_large_image',
  twitterTitle: () => `${currentLevel.value.title} | ai-shield`,
  twitterDescription: () => gameSeoDescription.value,
  twitterImage: () => `${siteUrl.value}${TWITTER_CARD_PATH}`,
  twitterImageAlt: TWITTER_CARD_ALT,
  robots: 'index, follow'
})
</script>

<template>
  <div class="flex h-dvh w-screen flex-col overflow-hidden bg-default text-default">
    <!-- Top Nav 1: Return button + Level Name (left) | Quota + Current Score (right) -->
    <header class="flex h-14 shrink-0 items-center justify-between border-b border-default px-4">
      <div class="flex items-center gap-3 min-w-0">
        <UButton
          label="Return"
          icon="i-lucide-arrow-left"
          color="neutral"
          variant="ghost"
          size="lg"
          @click="handleReturnClick"
        />

        <h1 class="text-base text-md font-bold text-highlighted truncate">
          {{ currentLevel.title }}
        </h1>

        <UButton
          v-if="!isCustomMode"
          icon="i-lucide-circle-question-mark"
          color="neutral"
          variant="ghost"
          size="sm"
          @click="isBriefingOpen = true"
        />
      </div>

      <div class="flex items-center gap-3">
        <UButton
          v-if="isLoggedIn && !isPaid"
          label="Upgrade"
          icon="i-lucide-sparkles"
          color="neutral"
          variant="outline"
          size="md"
          to="/plans"
        />

        <div class="flex items-center gap-3 pl-2">
          <template v-if="waveScore">
            <UButton
              label="Results"
              icon="i-lucide-grid-2x2"
              color="neutral"
              variant="outline"
              size="md"
              @click="isResultsOpen = true"
            />
            <USeparator
              orientation="vertical"
              class="h-5"
            />
          </template>
          <span class="text-md">
            High Score: {{ (highScore ?? 0).toLocaleString() }}
          </span>
          <UInputRating
            :model-value="highStars"
            :length="3"
            readonly
            color="warning"
            :aria-label="`${highStars} of 3 stars`"
          />
        </div>
      </div>
    </header>

    <GameControls />

    <!-- Main Workspace: Collapsible Left Tools Panel + Full Canvas -->
    <div class="relative flex flex-1 min-h-0 overflow-hidden">
      <GameToolsPanel />

      <GameCanvas />
    </div>

    <GameDialogs />
    <GameResultsModals />
    <GameNodeSettingsModal />
    <GameLevelTour />
  </div>
</template>
