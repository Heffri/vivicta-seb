# Workspace UI template

All main pages use `PageHeader` and `Workspace` from
`frontend/src/components/ui/workspace.tsx`. Keep the existing semantic colors in
`frontend/src/index.css`; the same layout supports light, dark and acrylic themes.

- One page heading and a short description. Put primary page actions on the right.
- Related tasks belong in the workspace's top navigation. Show one task at a time.
- Filters belong in the toolbar, before content. Use shared Input and Select controls.
- Use one enclosing workspace border and 20px content padding. Avoid nested enclosing
  cards; reserve cards for independent content within a task.
- Use the workspace footer for actions shared between subpages.
- Subpages mount when first visited, then preserve form edits and question history.
  Use `keepMounted` only for data that must be available before visiting a page
  (for example, the prior-year comparison used by exports).
- On narrow screens, navigation scrolls horizontally and columns stack. Do not clip
  content to make a desktop layout fit.

| Page | Subpages |
| --- | --- |
| Extract | Find a company, Saved reports, Upload PDF |
| Results | Figures & sources, Maturity profile (when available), Checks & review, Prior year, Ask report, Export |
| Compare | Side by side, Ask reports |
| Ask | Conversation, Available reports |
| Knowledge base | Reports, Search index |
| Review | All checks, Figures, Reporting basis, Calculations |
| Company map | Map, Company reports |
| Settings | Model provider, Extraction (desktop), Appearance |

## Reading sources

The Results overview keeps the nine income-statement figures visible at 1280×720
without scrolling. Share common units and periods in the table heading; show
exceptions beside their values and never turn missing figures into zero. Use
compact verification icons with accessible labels, with full guidance and human
review in the selected figure's disclosure. Maturity charts have their own subpage
so they cannot push the figures below the fold.

Figures use a compact table to leave 60% of the desktop report workspace for the
source. The reader starts at 100% scale, supports 75–250% zoom and fit width, and
can expand across the workspace. The PDF viewer also provides native search,
page navigation and zoom. Image previews scroll at the selected scale; saved text
starts at 16px. The report workspace can grow to 1680px, while other pages remain
bounded at the shared normal page width. Source links from checks and answers
open Figures & sources and focus the reader.

UI-only changes should preserve API contracts, review history and exports.
