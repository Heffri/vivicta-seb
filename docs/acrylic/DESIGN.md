# Acrylic design tokens

Source: unified-agent-workbench (UAW) `demo` branch — `src/workbench-shell/renderer/themes/theme-acrylic.css`
(+ `theme-schemes.css`, `styles.css` for rail/titlebar/statusbar sizing). Read via
`git -C <UAW checkout> show demo:<path>`, reference-only, nothing written there. Browsers have no OS acrylic
material, so UAW's own "no material" fallback — wallpaper gradient behind a `backdrop-filter` pane — is our
permanent state, not an edge case. Font stays Geist Variable; not part of the UAW port.

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
| `--bg-0` | shell fill only | `rgb(11 11 14/88%)` | `rgb(252 252 254/90%)` | the one blurred ground |
| `--bg-1` | `--background` | `rgb(22 22 27/58%)` | `rgb(0 0 0/2.5%)` | subtlest raised step (outline button fill) |
| `--bg-2` | `--muted`, `--secondary` | `rgb(32 32 39/62%)` | `rgb(0 0 0/4%)` | hover feedback, quiet fill |
| `--bg-3` | `--card`, `--accent` | `rgb(48 48 57/58%)` | `rgb(0 0 0/6%)` | card surface, hover/selected row |
| `--bg-4` | `--popover` | `rgb(62 62 73/62%)` | `rgb(0 0 0/10%)` | floating popover fill (kept for v002+; nothing renders it yet, `SelectContent` uses `--bg-0` — see above) |
| `--line-0/1/2` | middle step → `--border`, `--input` | alpha-white 6/11/19% | alpha-black 7/12/20% | hairlines; shadcn only needs one, uses `--line-1` |
| `--fg-0..3` | `--foreground` (0), `--muted-foreground` (2) | `#f4f4f7` … `#8a8a95` | `#16161a` … `#60606b` | four text weights, contrast ratios lifted verbatim from UAW |
| `--glass-hi` | `.glass`, card/badge top edge | `rgb(255 255 255/8%)` | `rgb(255 255 255/65%)` | the 1px specular highlight |
| `--glass-shadow` | `.glass` | `0 22px 60px rgb(0 0 0/55%)` | `0 22px 60px rgb(40 44 60/22%)` | contact shadow under the pane |
| `--blur` | `.glass` | `saturate(180%) blur(26px)` | same | the one `backdrop-filter` in the app |
| `--radius` | `--radius` | `0.875rem` | same, tone-independent | shadcn's sm/md/lg/xl ladder now lands near UAW's 7/10/14px |
| accent (raw hue) | feeds `--primary`, `--ring` | `#7aa2f7` (UAW default scheme) | `#2b5cb4` (UAW light-acrylic accent) | focus rings, links, primary button tint |
| `--destructive` | `--destructive` | `#e0897f` | `#a23a32` | UAW's `--err` |

`--primary` is never a flat accent fill — it reads as a sticker glued onto glass. UAW's `.btn.primary`/`.send`
always tint the ground instead: dark = `color-mix(in srgb, #7aa2f7 22%, var(--bg-0))`,
light = `color-mix(in srgb, #2b5cb4 16%, transparent)`. Text follows the same split, not a palette swap: dark
gets near-white (`color-mix(in srgb, #7aa2f7 34%, #f0f5ff)`), light gets solid navy `#12305e` — a light wash on
an already-light ground needs dark text, not a paler white.

Naming collision to note: shadcn's own `--accent`/`--accent-foreground` (neutral hover surface, e.g.
`SelectItem`'s `focus:bg-accent`) is a **different variable** from "the accent colour" above — it stays a
neutral `--bg-3`, per shadcn's meaning, not UAW's. The brand hue only feeds `--primary` and `--ring`.

## Reference

UAW screenshot for comparison: [`evidence/v001/uaw-reference-dark.png`](evidence/v001/uaw-reference-dark.png),
copied from a private sibling checkout's
`.scratch/unified-ai-workbench/evidence/production-explicit-new-agent-session/explicit-new-session-wide-1440x900.png`
(fixture project/session names only, no owner identifiers).
