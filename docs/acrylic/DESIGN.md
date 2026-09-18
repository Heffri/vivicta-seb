# Acrylic design tokens

Source: unified-agent-workbench (UAW) `demo` branch — `src/workbench-shell/renderer/themes/theme-acrylic.css`
(+ `theme-schemes.css`, `styles.css` for rail/titlebar/statusbar sizing). Read via
`git -C <UAW checkout> show demo:<path>`, reference-only, nothing written there. Browsers have no OS acrylic
material, so UAW's own "no material" fallback — wallpaper gradient behind a `backdrop-filter` pane — is our
permanent state, not an edge case. Font stays Geist Variable in the browser; desktop/'s real material
(v029) also switches the font stack, see the `--font-sans`/`--font-mono` row below.

## One material

The app shell (titlebar + rail + stage + statusbar, all of `App.tsx`) is **one** blurred glass pane sitting on
the wallpaper gradient painted on `body` — the `.glass` utility, applied once. Everything inside it is a flat,
translucent step of `--bg-1..4`, no per-component `backdrop-filter`, so the window reads as one pane of glass,
not a stack of separately-blurred plates. The one exception UAW itself makes: floating popovers keep their own
thin glass, since they render outside the window pane. `SelectContent` gets `.glass` for that reason; cards,
tables and badges never do — they just get the highlight (`--glass-hi`) and a flat `--bg-N`.

## Token table — dark is `:root`'s default, light is `[data-tone="light"]` (no `.dark` class, see index.css)

| Token | shadcn variable | Dark | Light | Use |
|---|---|---|---|---|
| `--bg-0` | shell fill only | `rgb(11 11 14/66%)` | `rgb(252 252 254/76%)` | the one blurred ground. v006b: 88/90% → 66/76% — at 88/90% only ~10% of the wallpaper showed and the window read flat. Contrast re-verified on the composited ground (worst = under the brightest glow), `evidence/v006.md` §v006b |
| `--bg-0` under `[data-material="on"]` | same | `rgb(11 11 14/52%)` | `rgb(252 252 254/62%)` | desktop/'s real Windows acrylic (v029) replaces the painted `--wallpaper` with the OS's own blurred desktop, so `--bg-0` drops another 14pp to let more of it through; browser tab is unaffected (attribute is never set outside Electron), `evidence/v029.md` |
| `--font-sans`/`--font-mono` under `[data-material="on"]` | `--font-heading`, `html`'s base font, `.font-mono` | `'Segoe UI Variable Text', 'Segoe UI', system-ui, sans-serif` / `'Cascadia Code', 'Cascadia Mono', ui-monospace, Consolas, monospace` | same, tone-independent | UAW's own stack (`renderer/styles.css:73-74`) is `Inter, "Segoe UI Variable Text", ...` / `"Cascadia Code", "Cascadia Mono", ...`; ours drops the leading `Inter` since we don't bundle it and the whole point (owner, 2026-09-16) is a zero-download desktop font — both remaining stacks ship with Windows 11. Required an `html { font-family: var(--font-sans) }` fix alongside: `@apply font-sans` (the prior rule) bakes Tailwind's font utility in as a literal at build time and never re-resolves per `data-material`, confirmed by inspecting the compiled CSS — `.font-mono` was already a real `var()` reference so needed no such fix. Browser tab keeps Geist (`--font-sans` only changes under the attribute Electron sets), `evidence/v029.md` |
| `--bg-1` | `--background` | `rgb(22 22 27/58%)` | `rgb(0 0 0/2.5%)` | subtlest raised step (outline button fill) |
| `--bg-2` | `--muted`, `--secondary` | `rgb(32 32 39/62%)` | `rgb(0 0 0/4%)` | hover feedback, quiet fill, selected table row |
| `--bg-3` | `--card`, `--accent` | `rgb(48 48 57/64%)` | `rgb(0 0 0/6%)` | card surface, hover/selected row, active button step. Dark rose 58% → 64% in v006b so cards stay solid over the more transparent glass (light keeps 6% — raising it darkens the card and kills the badge-text gate) |
| `--bg-4` | `--popover` | `rgb(62 62 73/62%)` | `rgb(0 0 0/10%)` | floating popover fill (kept for v002+; nothing renders it yet, `SelectContent` uses `--bg-0` — see above) |
| `--wallpaper` | `body` background | deep blue → indigo → near black + blue/violet glows | cream → pale blue-violet + blue/lavender glows | what the glass sits on; browsers have no OS material, so the wallpaper carries the colour. v006: UAW's flat fallback replaced by a two-glow composition (blue top-left, violet/lavender bottom-right over a `168deg` deep gradient) — glows capped at luminances that keep the resolved glass ground on v001's contrast ladder (see `evidence/v006.md` for the numbers) |
| `--line-0/1/2` | middle step → `--border`, `--input` | alpha-white 6/11/19% | alpha-black 7/12/20% | hairlines; shadcn only needs one, uses `--line-1` |
| `--fg-0..3` | `--foreground` (0), `--muted-foreground` (2) | `#f4f4f7` … `#8a8a95` | `#16161a` … `#60606b` | four text weights, contrast ratios lifted verbatim from UAW |
| `--glass-hi` | `.glass`, card/badge top edge | `rgb(255 255 255/8%)` | `rgb(255 255 255/65%)` | the 1px specular highlight |
| `--glass-shadow` | `.glass` | `0 22px 60px rgb(0 0 0/55%)` | `0 22px 60px rgb(40 44 60/22%)` | contact shadow under the pane |
| `--blur` | `.glass` | `saturate(180%) blur(26px)` | same | the one `backdrop-filter` in the app |
| `--radius` | `--radius` | `0.875rem` | same, tone-independent | shadcn's sm/md/lg/xl ladder now lands near UAW's 7/10/14px |
| accent (raw hue) | feeds `--primary`, `--primary-hover`, `--ring` | `#7aa2f7` (UAW default scheme) | `#2b5cb4` (UAW light-acrylic accent) | focus rings, links, primary button tint |
| `--destructive` | `--destructive` | `#e0897f` | `#a23a32` | UAW's `--err` |
| `--success`/`-foreground`/`-muted` | `--success`, `--success-foreground`, `--success-muted` | `#7bc99a` / `#0f2a1c` / 12%-tint | `#276f47` / `#eafff2` / 5%-tint | UAW's `--ok`; status badges. Light tint is 5% (v001 12% → v006 8% → v006b 5%, chasing the light card ground as the glass cleared): success text on that ground is the binding constraint — 12% measured 4.31:1, 8% 4.32–4.40 across the v006b glass band, 5% clears 4.5 wherever the gate holds. Dark keeps 12% (worst 4.63:1 at the v006b glass). Numbers in `evidence/v006.md` |
| `--warning`/`-foreground`/`-muted` | `--warning`, `--warning-foreground`, `--warning-muted` | `#d9b06a` / `#2b1c05` / 12%-tint | `#805208` / `#fff6e6` / 5%-tint | UAW's `--warn`; same treatment as success |
| `--danger`/`-foreground`/`-muted` | `--danger`, `--danger-foreground`, `--danger-muted` | `#e0897f` / `#2a0d09` / 12%-tint | `#a23a32` / `#fff1ee` / 5%-tint | UAW's `--err` again — same hue as `--destructive`, kept as a separate token because it names a data *status* (a failed check), not a destructive *action*; `Badge` gets matching `success`/`warning`/`danger` variants (additive, existing variants untouched) |

`--primary` is never a flat accent fill — it reads as a sticker glued onto glass. UAW's `.btn.primary`/`.send`
always tint the ground instead: dark = `color-mix(in srgb, #7aa2f7 22%, var(--bg-0))`,
light = `color-mix(in srgb, #2b5cb4 16%, transparent)`. Text follows the same split, not a palette swap: dark
gets near-white (`color-mix(in srgb, #7aa2f7 34%, #f0f5ff)`), light gets solid navy `#12305e` — a light wash on
an already-light ground needs dark text, not a paler white. `--primary-hover` raises the accent share the way
UAW's own `:hover` does (dark 22% → 29%, light 16% → 24%) — v006 replaced the old `hover:bg-primary/80`
alpha-dilution with it.

Focus rings (v006): interactive primitives (Button, SelectTrigger, Badge-as-link) show a **2px solid
`--ring` outline with a 2px offset** on `:focus-visible` — the offset gap shows the glass, Windows-11 style.
(The shell's rail buttons are not covered by this; they still get the browser's default ring tinted by the
base `outline-ring/50` — shell is outside the primitives' territory.)

`ui/table.tsx`'s `Table` takes an optional `containerClassName` merged into the `table-container` wrapper div
(default behaviour unchanged). The wrapper is hardcoded `overflow-x-auto`, and per CSS that forces
`overflow-y: auto` too, which makes it the nearest scroll container and silently defeats `position: sticky`
headers inside any bounded box (v005 hit this and had to reach in via an arbitrary `[data-slot]` selector);
pass `containerClassName="max-h-[70vh] overflow-y-auto"` instead.

Naming collision to note: shadcn's own `--accent`/`--accent-foreground` (neutral hover surface, e.g.
`SelectItem`'s `focus:bg-accent`) is a **different variable** from "the accent colour" above — it stays a
neutral `--bg-3`, per shadcn's meaning, not UAW's. The brand hue only feeds `--primary` and `--ring`.

## Reference

UAW screenshot for comparison: [`evidence/v001/uaw-reference-dark.png`](evidence/v001/uaw-reference-dark.png),
copied from a private sibling checkout's
`.scratch/unified-ai-workbench/evidence/production-explicit-new-agent-session/explicit-new-session-wide-1440x900.png`
(fixture project/session names only, no owner identifiers).
