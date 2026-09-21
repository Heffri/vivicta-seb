// Scroll the report pane only. scrollIntoView also scrolls outer ancestors,
// which can move the desktop shell and expose the wallpaper beneath it.
export function scrollContent(target: HTMLElement | null, behavior: ScrollBehavior = 'auto') {
  const content = document.getElementById('content')
  if (!target || !content || !content.contains(target)) return
  content.scrollTo({ top: content.scrollTop + target.getBoundingClientRect().top - content.getBoundingClientRect().top - 16, behavior })
}
