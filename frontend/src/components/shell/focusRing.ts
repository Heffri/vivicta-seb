// The shell's focus ring recipe: 2px solid outline, 2px offset, shown only for
// focus-visible so a mouse click (or a programmatic .focus() that followed one) stays quiet
// — see docs/acrylic/evidence/v027.md for the heading-focus-on-tab-switch use of this.
export const FOCUS_RING =
  'outline-none focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-offset-2 focus-visible:outline-ring'
