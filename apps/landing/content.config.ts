import { defineCollection, defineContentConfig, z } from '@nuxt/content'

// One collection per locale (Nuxt Content i18n pattern). Each legal page is a Markdown
// file with a layered summary in its front matter; the page shows the summary first.
const legalSchema = z.object({
  version: z.string(),
  effective: z.date(),
  summary: z.array(z.object({
    title: z.string(),
    description: z.string(),
    icon: z.string(),
    to: z.string()
  }))
})

export default defineContentConfig({
  collections: {
    legal_en: defineCollection({
      type: 'page',
      source: { include: 'en/**/*.md', prefix: '' },
      schema: legalSchema
    }),
    legal_ms: defineCollection({
      type: 'page',
      source: { include: 'ms/**/*.md', prefix: '' },
      schema: legalSchema
    })
  }
})
