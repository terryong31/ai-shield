export interface ChangelogEntry {
  version: string
  date: string
  badge: string
  title: { en: string, ms: string }
  description: { en: string, ms: string }
}

export const CHANGELOG_ENTRIES: ChangelogEntry[] = [
  {
    version: 'v1.2.0',
    date: '2026-11-28',
    badge: 'Launch',
    title: {
      en: 'Custom domain launch, bilingual legal hub, and isolated admin console',
      ms: 'Pelancaran domain tersuai, hab perundangan dwibahasa, dan konsol admin terasing'
    },
    description: {
      en: 'ai-shield now runs on ai-shield.my and play.ai-shield.my with bilingual English and Bahasa Malaysia privacy, terms, and refund pages plus a dedicated client changelog.',
      ms: 'ai-shield kini beroperasi di ai-shield.my dan play.ai-shield.my dengan halaman privasi, terma, dan bayaran balik dwibahasa serta log perubahan pemain.'
    }
  },
  {
    version: 'v1.1.0',
    date: '2026-11-27',
    badge: 'Privacy',
    title: {
      en: 'Self-service account data export and privacy controls',
      ms: 'Eksport data akaun layan diri dan kawalan privasi'
    },
    description: {
      en: 'Signed-in players can download their account profile, saved boards, best scores, and purchase records as JSON directly from Settings.',
      ms: 'Pemain berdaftar boleh memuat turun profil akaun, papan tersimpan, skor terbaik, dan rekod pembelian sebagai JSON terus daripada Tetapan.'
    }
  },
  {
    version: 'v1.0.0',
    date: '2026-11-20',
    badge: 'Campaign',
    title: {
      en: '19-level prompt-injection campaign and Custom Sandbox',
      ms: 'Kempen suntikan prom 19 tahap dan Kotak Pasir Tersuai'
    },
    description: {
      en: 'Play across Easy, Medium, and Hard tiers with 9 defence tools including ML Filter, Safety Check, LLM Review, Tool Filter, and Jev.',
      ms: 'Main merentasi tahap Mudah, Sederhana, dan Sukar dengan 9 alat pertahanan termasuk Penapis ML, Semakan Keselamatan, Semakan LLM, Penapis Alat, dan Jev.'
    }
  }
]
