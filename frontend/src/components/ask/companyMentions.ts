/** Exact, longest-name-first mentions. Unknown @ tokens never broaden the scope. */
export function companyMentions(text: string, companies: string[]) {
  const names = [...companies].sort((a, b) => b.length - a.length)
  const selected: string[] = []
  const unknown: string[] = []
  const starts = [...text.matchAll(/(^|[^\p{L}\p{N}_])@/gu)]
  for (const match of starts) {
    const start = match.index! + match[0].length
    const tail = text.slice(start)
    const fragment = tail.split(/[@\n]/, 1)[0].trim().toLocaleLowerCase()
    const incomplete = names.some((name) => name.toLocaleLowerCase().startsWith(fragment) && name.toLocaleLowerCase() !== fragment) && !names.some((name) => name.toLocaleLowerCase() === fragment)
    const company = !incomplete && names.find((name) => tail.toLocaleLowerCase().startsWith(name.toLocaleLowerCase()) && !/[\p{L}\p{N}_-]/u.test(tail[name.length] ?? ''))
    if (company) {
      if (!selected.includes(company)) selected.push(company)
    } else unknown.push(tail.split(/[@\n]/, 1)[0].trim() || '(unfinished mention)')
  }
  return { selected, unknown }
}

export function mentionAtCursor(text: string, cursor: number) {
  const match = text.slice(0, cursor).match(/(^|[^\p{L}\p{N}_])@([^@\n]*)$/u)
  return match ? { start: cursor - match[2].length - 1, query: match[2] } : null
}
