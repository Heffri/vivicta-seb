import { defineConfig } from '@playwright/test'

// No webServer block on purpose: backend (fixture mode) + `npm run dev` must already be running
// against whatever E2E_BASE_URL points at — see the frontend README's "Playwright e2e" section.
//
// Serial on purpose (fullyParallel: false, workers: 1): every test shares one long-lived dev
// backend (in-memory report store, data/kb on disk). Two tests registering the same cached PDF
// at once would race on the KB re-registration write (docs/acrylic/... LESSONS.md #27); a smoke
// suite this small doesn't need the parallelism enough to risk that.
export default defineConfig({
  testDir: './tests',
  outputDir: './test-results', // keep run artifacts under e2e/, not scattered into frontend/
  fullyParallel: false,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://127.0.0.1:5173',
    viewport: { width: 1440, height: 900 },
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'edge',
      // Local Microsoft Edge, zero browser download (frontend/README.md's Acrylic UI section /
      // LESSONS.md #24). CI without Edge installed: drop `channel` to fall back to bundled Chromium
      // (after an `npx playwright install chromium`).
      use: { channel: 'msedge' },
    },
  ],
})
