---
title: Dasar Privasi
description: Data yang dikumpul oleh ai-shield, tujuannya, tempoh simpanan, sub-pemproses, dan hak anda di bawah PDPA Malaysia dan GDPR.
version: '2.0'
effective: 2026-11-28
summary:
  - title: Kami kumpul sedikit sahaja
    description: E-mel, nama paparan, papan, skor dan pembelian anda. Kami tidak menyimpan prom yang anda jalankan atau kunci API anda sendiri.
    icon: i-lucide-database
    to: '#data-yang-kami-kumpul'
  - title: Tiada kuki penjejakan
    description: Kami hanya menggunakan kuki yang diperlukan untuk log masuk. Pengukuran laman adalah tanpa kuki.
    icon: i-lucide-cookie
    to: '#kuki-dan-storan-pelayar'
  - title: Penyedia yang dinamakan sahaja
    description: Supabase, Vercel, Upstash, Stripe, Resend, Google, Groq dan TypeSafe memproses data untuk kami. Sesetengahnya di luar Malaysia.
    icon: i-lucide-server
    to: '#sub-pemproses'
  - title: Anda kekal berkuasa
    description: Eksport data anda sebagai JSON, tukar butiran anda, atau padam akaun anda pada bila-bila masa daripada Tetapan.
    icon: i-lucide-user-cog
    to: '#hak-anda'
---

## Siapa kami

::callout{icon="i-lucide-info"}
**Ringkasnya:** seorang individu mengendalikan ai-shield di Malaysia. Tulis kepada support@ai-shield.my untuk sebarang soalan privasi.
::

Terry Ong (pengendali ai-shield di Malaysia) mengawal data peribadi yang dinyatakan di sini. Dasar ini meliputi ai-shield.my, play.ai-shield.my, admin.ai-shield.my, dan api.ai-shield.my. Untuk pertanyaan privasi atau PDPA, hubungi [support@ai-shield.my](mailto:support@ai-shield.my).

## Data yang kami kumpul

::callout{icon="i-lucide-info"}
**Ringkasnya:** kami menyimpan apa yang permainan perlukan untuk log masuk, menyimpan kemajuan dan menjual pas. Prom dan kunci API anda sendiri tidak pernah disimpan.
::

| Kategori | Data | Sebab | Tempoh |
| --- | --- | --- | --- |
| Akaun | E-mel (huruf kecil), nama paparan, pelan (percuma atau berbayar), tarikh tamat pas, tarikh akaun dicipta | Log masuk, had harian pelan anda, dan kedudukan anda pada papan pendahulu | Sehingga anda memadam akaun |
| Kemajuan | Papan tersimpan, skor dan pingat terbaik, baris CSV tersuai yang dimuat naik untuk melatih Penapis ML | Simpan kemajuan merentas peranti, susun papan pendahulu, jalankan Penapis ML anda | Papan dan skor sehingga ditetapkan semula atau akaun dipadam; model ML terlatih kekal dalam memori selama 30 minit tanpa aktiviti |
| Main tanpa log masuk | Skor terbaik sesi tanpa log masuk, dikunci dengan cincangan token sesinya | Pindahkan skor anda ke akaun apabila anda log masuk | 7 hari, atau sehingga anda log masuk |
| Prom dan kunci BYOK | Prom gelombang dan kunci API Kotak Pasir Tersuai yang anda taip dalam pelayar | Jalankan semakan dan balasan ejen untuk larian itu sahaja | Tidak disimpan. Kunci API BYOK kekal dalam memori pelayar sahaja |
| Pembayaran | Pembelian pas: id, jumlah, mata wang (USD), status, id bayaran, tarikh mula dan tamat | Beri pas 30 hari dan uruskan bayaran balik atau pertikaian. Butiran kad kekal dengan Stripe | Disimpan untuk perakaunan; e-mel anda ditetapkan kepada NULL apabila akaun dipadam |
| Keselamatan | IP dicincang SHA-256 dalam pembilang had kadar, token sesi dicincang, kiraan larian harian, log audit keselamatan | Halang serangan kekerasan, bot, dan penyalahgunaan | Pembilang had kadar: 1 minit hingga 1 jam. Kiraan larian harian akaun dipadam: dibuang selepas 30 hari UTC |
| Pengukuran laman | Paparan halaman agregat tanpa kuki dan Core Web Vitals di ai-shield.my dan play.ai-shield.my (rentetan pertanyaan pengesahan dibuang) | Semak ketersediaan dan kelajuan halaman | Seperti yang ditetapkan oleh Vercel |

## Kuki dan storan pelayar

::callout{icon="i-lucide-info"}
**Ringkasnya:** setiap kuki di sini diperlukan supaya permainan berfungsi. Tiada kuki pengiklanan atau penjejakan.
::

| Nama | Storan | Sebab | Tempoh |
| --- | --- | --- | --- |
| `shield_player_session` | Kuki HttpOnly (SameSite=Lax, Secure, play.ai-shield.my) | Sesi pemain (log masuk atau tanpa nama); pelayan menyimpan cincangan SHA-256 sahaja | 8 jam atau sehingga log keluar |
| `shield_auth_browser` | Kuki HttpOnly (SameSite=Lax, play.ai-shield.my) | Mengikat pautan pengesahan dan pemulihan e-mel kepada pelayar yang memintanya | 30 hingga 60 minit |
| `shield_session_hint` | Kuki (play.ai-shield.my) | Mengelakkan menu berkelip semasa halaman dimuatkan; tidak menyimpan e-mel atau token | Selari dengan sesi |
| `shield_session` | Kuki HttpOnly (SameSite=Strict, Secure, admin.ai-shield.my) | Akses konsol admin terasing untuk pengendali sahaja | 8 jam |
| `shield_anon_draft:v1:<level>` | localStorage (play.ai-shield.my) | Draf papan yang belum disimpan sebelum log masuk; tidak menyimpan skor | Sehingga Mula Semula, log masuk, atau data laman dikosongkan |
| `ai-shield:tour-seen:<level>` | localStorage (play.ai-shield.my) | Mengingati lawatan tahap yang telah anda lihat | Sehingga data laman dikosongkan |
| Cache papan tersimpan dan papan pendahulu | sessionStorage (play.ai-shield.my) | Tab dimuatkan lebih cepat | Sehingga tab ditutup |

## Sub-pemproses

::callout{icon="i-lucide-info"}
**Ringkasnya:** syarikat ini menjalankan sebahagian ai-shield untuk kami. Setiap satu hanya menerima data yang diperlukan untuk tugasnya.
::

| Penyedia | Peranan | Sebab | Tempoh |
| --- | --- | --- | --- |
| Supabase | Pangkalan data dan Auth | Menyimpan akaun, kemajuan, dan pembelian; mengesahkan kata laluan | Seperti di atas |
| Vercel | Pengehosan, BotID, Web Analytics, Speed Insights | Menyajikan ai-shield.my, play.ai-shield.my, admin.ai-shield.my, dan api.ai-shield.my | Seperti yang ditetapkan oleh Vercel |
| Redis (Upstash) | Pembilang dan cache jangka pendek | Had kadar, keadaan aliran pengesahan, cache papan pendahulu, model ML sementara | Beberapa minit hingga 2 hari |
| Stripe | Hosted Checkout | Memproses bayaran dan bayaran balik Pas 30 Hari $5 USD | Seperti yang ditetapkan oleh Stripe |
| Resend | E-mel transaksi dan sokongan (SMTP) | Menghantar e-mel pengesahan (no-reply@ai-shield.my) dan balasan sokongan (support@ai-shield.my) | Seperti yang ditetapkan oleh Resend |
| Google (Gemini) dan Groq | Model AI kempen | Menjalankan ejen dilindungi dan semakan pada tahap Sederhana dan Sukar | Setiap larian, seperti yang ditetapkan oleh penyedia |
| TypeSafe | Nod Jev | Menjawab soalan ya-atau-tidak nod Jev apabila anda menggunakannya | Setiap larian, seperti yang ditetapkan oleh penyedia |
| OpenAI, Anthropic, OpenRouter | Penyedia BYOK pilihan | Dipanggil hanya apabila anda memberikan kunci API anda sendiri dalam Kotak Pasir Tersuai | Seperti yang ditetapkan oleh penyedia pilihan anda |

## Pemindahan rentas sempadan

::callout{icon="i-lucide-info"}
**Ringkasnya:** sesetengah penyedia memproses data di luar Malaysia, di bawah kontrak yang memastikannya selamat.
::

Data anda mungkin diproses di luar Malaysia oleh sub-pemproses yang dinamakan (Supabase, Vercel, Upstash Redis, Stripe, Resend, Google, Groq, TypeSafe, serta penyedia BYOK OpenAI, Anthropic, dan OpenRouter) di bawah perlindungan kontrak yang selaras dengan Prinsip Keselamatan PDPA (Seksyen 9).

## Notifikasi pelanggaran data

::callout{icon="i-lucide-info"}
**Ringkasnya:** jika berlaku pelanggaran serius, kami maklumkan pengawal selia dalam 72 jam dan maklumkan anda tanpa berlengah.
::

Jika berlaku pelanggaran data peribadi yang memenuhi ambang notifikasi berkanun di bawah Akta Perlindungan Data Peribadi (Pindaan) 2024 Malaysia, kami akan memaklumkan Pesuruhjaya Perlindungan Data Peribadi (PDPC) dalam tempoh 72 jam dan memaklumkan pengguna terjejas tanpa kelewatan yang tidak wajar.

## Hak anda

::callout{icon="i-lucide-info"}
**Ringkasnya:** anda boleh melihat, memuat turun, menukar atau memadam data anda sendiri, pada bila-bila masa.
::

Anda boleh mengakses dan memuat turun data akaun anda sebagai JSON pada bila-bila masa di [play.ai-shield.my/settings](https://play.ai-shield.my/settings) (Download my data), mengemas kini nama paparan, e-mel, atau kata laluan, menetapkan semula kemajuan, atau memadam akaun anda secara kekal. Hubungi [support@ai-shield.my](mailto:support@ai-shield.my) untuk sebarang permintaan privasi.
