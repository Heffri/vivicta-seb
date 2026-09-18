import { expect, test } from '@playwright/test'
import { companyMentions, mentionAtCursor } from '../../src/components/ask/companyMentions'

test('company mentions are exact, longest-first, and never broaden unknown scope', () => {
  const names = ['Atlas', 'Atlas Copco AB', 'SEB']
  expect(companyMentions('Compare @Atlas Copco AB with @SEB revenue', names)).toEqual({ selected: ['Atlas Copco AB', 'SEB'], unknown: [] })
  expect(companyMentions('@seb and @SEB', names).selected).toEqual(['SEB'])
  expect(companyMentions('@Atlas Co', names).unknown).toHaveLength(1)
  expect(companyMentions('@SEBank', names).unknown).toHaveLength(1)
  expect(companyMentions('Compare (@Unknown) and @SEB', names).unknown).toHaveLength(1)
  expect(companyMentions('@', names).unknown).toHaveLength(1)
  expect(companyMentions('mail@example.com', names).selected).toEqual([])
  expect(mentionAtCursor('Ask @Atlas Co', 13)).toEqual({ start: 4, query: 'Atlas Co' })
})
