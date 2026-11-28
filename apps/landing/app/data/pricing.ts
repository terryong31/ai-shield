// Pricing page content in the shape of the Nuxt UI SaaS template (content/2.pricing.yml),
// one copy per locale. Plan features follow the game's plan cards (apps/web planCards).
import type { Locale } from './home'

export interface PricingContent {
  seo: { title: string, description: string }
  title: string
  description: string
  plans: {
    id: 'free' | 'pass'
    title: string
    description: string
    price: string
    billingCycle?: string
    billingPeriod?: string
    highlight?: boolean
    button: string
    features: string[]
  }[]
  logos: { title: string }
  faq: { title: string, description: string, items: { label: string, content: string }[] }
}

export const PROVIDER_ICONS = [
  'i-simple-icons-openai',
  'i-simple-icons-anthropic',
  'i-simple-icons-googlegemini',
  'i-simple-icons-openrouter',
  'i-simple-icons-meta'
]

export const PRICING: Record<Locale, PricingContent> = {
  en: {
    seo: {
      title: 'Pricing',
      description: 'Play ai-shield free, or buy a one-time $5 USD 30-day pass for all 19 levels, 50 daily runs and the Custom Sandbox. It never renews.'
    },
    title: 'Simple pricing that never renews',
    description: 'Start free with no credit card. When you want every level, buy one 30-day pass. There is no subscription to cancel.',
    plans: [
      {
        id: 'free',
        title: 'Free',
        description: 'For players who sign in.',
        price: '$0',
        button: 'Play free now',
        features: ['5 wave runs a day', 'Easy 1 to 3 and Medium 1 to 2', 'AI agent tools', 'Scores on the leaderboard']
      },
      {
        id: 'pass',
        title: '30-Day Pass',
        description: 'For players who defend every day.',
        price: '$5',
        billingCycle: '/30 days',
        billingPeriod: 'USD, one payment',
        highlight: true,
        button: 'Get the 30-day pass',
        features: ['50 wave runs a day', 'All 19 campaign levels', 'Everything in Free', 'Custom Sandbox with your own dataset and model key', 'One payment, does not renew']
      }
    ],
    logos: {
      title: 'Bring your own model provider in the Custom Sandbox'
    },
    faq: {
      title: 'Frequently asked questions',
      description: 'Everything you need to know about plans and payment. Cannot find your answer? Send an email to our support team.',
      items: [
        { label: 'Do I need an account to play?', content: 'No. You can open the board and play at once. Sign in to keep your scores on the leaderboard and to get your daily runs.' },
        { label: 'Does the pass renew?', content: 'No. The 30-day pass is one payment of $5 USD through Stripe. It ends after 30 days and you are not charged again.' },
        { label: 'What happens when the pass ends?', content: 'Your account goes back to the Free plan. Your saved boards and best scores stay.' },
        { label: 'Can I get a refund?', content: 'Yes, when the law gives you that right: for example, if the pass does not activate, if you were charged twice, or if the service has a major defect. Read the Refund Policy for the full rules.' },
        { label: 'Is my model API key safe in the Custom Sandbox?', content: 'The key stays in your browser memory for your session only. We do not store it, and you pay your provider for the use.' },
        { label: 'Is ai-shield a real security product?', content: 'No. ai-shield is an educational game. Your boards and scores teach defence patterns but do not guarantee the security of a production AI system.' }
      ]
    }
  },
  ms: {
    seo: {
      title: 'Harga',
      description: 'Main ai-shield secara percuma, atau beli pas 30 hari sekali bayar $5 USD untuk semua 19 tahap, 50 larian sehari dan Kotak Pasir Tersuai. Ia tidak diperbaharui.'
    },
    title: 'Harga mudah yang tidak diperbaharui',
    description: 'Mula percuma tanpa kad kredit. Apabila anda mahu setiap tahap, beli satu pas 30 hari. Tiada langganan untuk dibatalkan.',
    plans: [
      {
        id: 'free',
        title: 'Percuma',
        description: 'Untuk pemain yang log masuk.',
        price: '$0',
        button: 'Main percuma sekarang',
        features: ['5 larian gelombang sehari', 'Mudah 1 hingga 3 dan Sederhana 1 hingga 2', 'Alat ejen AI', 'Skor pada papan pendahulu']
      },
      {
        id: 'pass',
        title: 'Pas 30 Hari',
        description: 'Untuk pemain yang bertahan setiap hari.',
        price: '$5',
        billingCycle: '/30 hari',
        billingPeriod: 'USD, sekali bayar',
        highlight: true,
        button: 'Dapatkan pas 30 hari',
        features: ['50 larian gelombang sehari', 'Semua 19 tahap kempen', 'Semua dalam Percuma', 'Kotak Pasir Tersuai dengan set data dan kunci model anda sendiri', 'Sekali bayar, tidak diperbaharui']
      }
    ],
    logos: {
      title: 'Bawa penyedia model anda sendiri dalam Kotak Pasir Tersuai'
    },
    faq: {
      title: 'Soalan lazim',
      description: 'Semua yang anda perlu tahu tentang pelan dan bayaran. Tidak menemui jawapan? Hantar e-mel kepada pasukan sokongan kami.',
      items: [
        { label: 'Adakah saya perlu akaun untuk bermain?', content: 'Tidak. Anda boleh membuka papan dan terus bermain. Log masuk untuk menyimpan skor pada papan pendahulu dan mendapat larian harian anda.' },
        { label: 'Adakah pas diperbaharui?', content: 'Tidak. Pas 30 hari ialah satu bayaran $5 USD melalui Stripe. Ia tamat selepas 30 hari dan anda tidak dicaj lagi.' },
        { label: 'Apa berlaku apabila pas tamat?', content: 'Akaun anda kembali ke pelan Percuma. Papan tersimpan dan skor terbaik anda kekal.' },
        { label: 'Bolehkah saya mendapat bayaran balik?', content: 'Ya, apabila undang-undang memberi anda hak itu: contohnya, jika pas tidak diaktifkan, jika anda dicaj dua kali, atau jika perkhidmatan mempunyai kecacatan besar. Baca Dasar Bayaran Balik untuk peraturan penuh.' },
        { label: 'Adakah kunci API model saya selamat dalam Kotak Pasir Tersuai?', content: 'Kunci itu kekal dalam memori pelayar anda untuk sesi anda sahaja. Kami tidak menyimpannya, dan anda membayar penyedia anda untuk penggunaan.' },
        { label: 'Adakah ai-shield produk keselamatan sebenar?', content: 'Tidak. ai-shield ialah permainan pendidikan. Papan dan skor anda mengajar corak pertahanan tetapi tidak menjamin keselamatan sistem AI pengeluaran.' }
      ]
    }
  }
}
