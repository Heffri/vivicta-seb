import { expect, test } from '@playwright/test'

// w212: the deep-search switch (EXTRACT_SECOND_PASS) round-trips from Settings into the
// backend's live env and back. The editable Settings view only mounts where `window.arp`
// exists (desktop preload.js), so this spec stands in for the shell the way the real one
// behaves: settings.set() persists config.json (here localStorage) and the restarted
// backend's /api/config echoes the new env — second_pass derived from the saved secondPass
// key, exactly desktop/settings.js's envForConfig -> apply_second_pass translation. A reload
// re-reads the persisted echo, so "/api/config changed" is asserted against the same store
// the bridge actually wrote, not against a mock copy of the assertion.

test('deep search toggle survives Save, reload and the off round trip', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.addInitScript(() => {
    const KEY = 'e2e-desktop-config'
    const defaults = { provider: 'fixture', baseUrl: '', model: '', apiKey: '', embedModel: '', codexModel: 'gpt-5.6-terra', claudeModel: 'claude-sonnet-5', extractTwoPass: true, maturityBasis: 'carrying', mergeRuns: 'off', secondPass: false, theme: 'solid' }
    const stored = () => JSON.parse(localStorage.getItem(KEY) ?? 'null') ?? { ...defaults }
    // The restarted backend's /api/config echo: second_pass mirrors the saved secondPass the
    // same way the desktop's EXTRACT_SECOND_PASS env does on the real shell.
    const echo = (cfg: Record<string, unknown>) => ({ provider: cfg.provider, model: 'test', embed_model: '', base_url: null, llm: false, retrieval: 'fixture', second_pass: cfg.secondPass === true, scan_all: false })
    ;(window as unknown as { arp: unknown }).arp = {
      material: 'none', platform: 'e2e', version: 'e2e',
      settings: {
        get: async () => stored(),
        set: async (cfg: Record<string, unknown>) => {
          localStorage.setItem(KEY, JSON.stringify(cfg))
          return { ok: true, port: 1, config: echo(cfg) }
        },
        test: async () => ({ ok: true, kind: 'models', models: [] }),
        codexStatus: async () => ({ ok: true, kind: 'codex', version: 'e2e', loggedIn: true }),
        claudeStatus: async () => ({ ok: true, kind: 'claude', version: 'e2e', loggedIn: true }),
      },
    }
  })
  await page.route('**/api/config', async route => {
    const saved = await page.evaluate(() => JSON.parse(localStorage.getItem('e2e-desktop-config') ?? 'null'))
    return route.fulfill({ json: { provider: 'fixture', model: 'test', embed_model: '', base_url: null, llm: false, retrieval: 'fixture', second_pass: saved?.secondPass === true, scan_all: false } })
  })

  await page.goto('/')
  await page.getByRole('tab', { name: 'Settings', exact: true }).click()
  await expect(page.getByText('Running now', { exact: true })).toBeVisible()
  await expect(page.getByText('deep search off')).toBeVisible() // w197's default, echoed
  await expect(page.getByText('scan all off')).toBeVisible() // m02's offline scan, echo-only

  await page.getByRole('button', { name: 'Extraction', exact: true }).click()
  const group = page.getByRole('group', { name: 'Deep search for missing figures' })
  await expect(group).toBeVisible()
  await expect(group.getByRole('button', { name: 'On', exact: true })).toHaveAttribute('aria-pressed', 'false')
  await group.getByRole('button', { name: 'On', exact: true }).click()
  await page.getByRole('button', { name: 'Save', exact: true }).click()
  await expect(page.getByRole('status')).toHaveText('Saved — backend restarted.')
  // The "Running now" strip lives on the Model provider page; the Workspace keeps inactive
  // pages mounted-but-hidden, so read the save's own echo (res.config) from the visible page.
  await page.getByRole('button', { name: 'Model provider', exact: true }).click()
  await expect(page.getByText('deep search on')).toBeVisible()
  const saved = await page.evaluate(() => JSON.parse(localStorage.getItem('e2e-desktop-config')!))
  expect(saved.secondPass).toBe(true) // config.json stand-in carries the key

  await page.reload() // a fresh /api/config now echoes the persisted value
  await page.getByRole('tab', { name: 'Settings', exact: true }).click()
  await expect(page.getByText('deep search on')).toBeVisible()

  await page.getByRole('button', { name: 'Extraction', exact: true }).click()
  await group.getByRole('button', { name: 'Off', exact: true }).click()
  await page.getByRole('button', { name: 'Save', exact: true }).click()
  await page.getByRole('button', { name: 'Model provider', exact: true }).click()
  await expect(page.getByText('deep search off')).toBeVisible()
  await page.reload()
  await page.getByRole('tab', { name: 'Settings', exact: true }).click()
  await expect(page.getByText('deep search off')).toBeVisible()
  expect(errors).toEqual([])
})
