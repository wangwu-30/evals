# Validation task v1: daily-skill cold start, GitHub Actions + API mode, different persona

You are setting up a Personal AI Daily for a TEST user. This is a fixture run: there is no interview; use exactly the persona below and mark the profile `generated_from: fixture`.

Persona "Amara": product manager in Lagos, Nigeria (timezone Africa/Lagos), reads and writes English.
Interests: African fintech and payments, climate tech, open-source hardware.
Trusted feeds/accounts: TechCabal (https://techcabal.com/feed/), Rest of World (https://restofworld.org/feed/latest), Canary Media (https://www.canarymedia.com/rss.rss), Hackaday (https://hackaday.com/blog/feed/), GitHub releases of meshtastic/firmware (https://github.com/meshtastic/firmware/releases.atom), Hugging Face daily papers (https://huggingface.co/api/daily_papers), Hacker News front page via Algolia (https://hn.algolia.com/api/v1/search?tags=front_page).
The site is hosted on GitHub: repo amara-o/afro-tech-daily, site base https://amara-o.github.io/afro-tech-daily . The daily run is done by GitHub Actions (not by an agent). A model API key is stored as the repository secret DEEPSEEK_API_KEY.

Today's issue: run started 2026-10-12T07:05:00+01:00, fetch window 2026-10-11T07:00:00+01:00 .. 2026-10-12T07:00:00+01:00, build finished 2026-10-12T07:18:00+01:00, deployed (published) 2026-10-12T07:22:00+01:00.
Fetched raw items (all from the sources above):
1. TechCabal: Moniepoint launches cross-border payments to Ghana — https://techcabal.com/2026/10/11/moniepoint-cross-border-ghana/ — 2026-10-11T10:00:00+01:00
2. Canary Media: Solar mini-grids now power 2,000 Nigerian clinics — https://www.canarymedia.com/articles/solar/nigeria-mini-grids-clinics — 2026-10-11T15:30:00Z
3. meshtastic/firmware v2.7.1 — https://github.com/meshtastic/firmware/releases/tag/v2.7.1 — 2026-10-11T20:00:00Z
4. Hackaday: An open-source LoRa weather station for farms — https://hackaday.com/2026/10/11/open-source-lora-weather-station/ — 2026-10-11T17:00:00Z
5. HF paper: Low-power keyword spotting on microcontrollers — https://huggingface.co/papers/2610.05512 — 2026-10-11T08:00:00Z
6. HN: M-Pesa API outage post-mortem (412 points) — https://news.ycombinator.com/item?id=45100001 — 2026-10-11T22:00:00Z

Produce exactly these five files, each in its own block, in this format and nothing else between blocks:
=== FILE: config/profile.yaml ===
...content...
=== FILE: config/sources.yaml ===
...
=== FILE: .github/workflows/daily.yml ===
...
=== FILE: 2026-10-12/data.json ===
...  (the public issue JSON for 2026-10-12, current digest schema version)
=== FILE: index.json ===
...
=== END ===
