// Run directly: node --test src/components/ask/renderAnswer.test.ts (Node 24 strips types, no deps).
// @ts-nocheck -- tsconfig.app.json's `types` is browser-only (vite/client), so tsc can't see
// node:test/node:assert here; out of territory to change. Vite's module graph never imports
// this file, so it never reaches the app build — only `node --test` runs it.
import assert from 'node:assert/strict'
import test from 'node:test'
import { type CitationNode, renderAnswer } from './renderAnswer.ts'

test('plain paragraph with no markup passes through as one text node', () => {
  const blocks = renderAnswer('Hello world.')
  assert.deepEqual(blocks, [{ type: 'paragraph', children: [{ type: 'text', text: 'Hello world.' }] }])
})

test('a blank line splits two paragraphs', () => {
  const blocks = renderAnswer('First.\n\nSecond.')
  assert.equal(blocks.length, 2)
  assert.equal(blocks[0].type, 'paragraph')
  assert.equal(blocks[1].type, 'paragraph')
})

test('**bold** becomes a bold node', () => {
  const blocks = renderAnswer('This is **important**.')
  assert.deepEqual(blocks[0], {
    type: 'paragraph',
    children: [
      { type: 'text', text: 'This is ' },
      { type: 'bold', children: [{ type: 'text', text: 'important' }] },
      { type: 'text', text: '.' },
    ],
  })
})

test('inline `code` becomes a code node', () => {
  const blocks = renderAnswer('Run `npm test` now.')
  assert.deepEqual(blocks[0], {
    type: 'paragraph',
    children: [
      { type: 'text', text: 'Run ' },
      { type: 'code', text: 'npm test' },
      { type: 'text', text: ' now.' },
    ],
  })
})

test('- marker lines become an unordered list', () => {
  const blocks = renderAnswer('- one\n- two\n- three')
  assert.deepEqual(blocks, [
    {
      type: 'list',
      ordered: false,
      items: [[{ type: 'text', text: 'one' }], [{ type: 'text', text: 'two' }], [{ type: 'text', text: 'three' }]],
    },
  ])
})

test('N. marker lines become an ordered list', () => {
  const blocks = renderAnswer('1. first\n2. second')
  const block = blocks[0]
  if (block.type !== 'list') throw new Error('expected a list block')
  assert.equal(block.ordered, true)
  assert.equal(block.items.length, 2)
})

test('[Company p.N] in the fixture sentence becomes a citation node', () => {
  const blocks = renderAnswer('Revenue was 152 340 MSEK [Nordic Industrials p.64].')
  const block = blocks[0]
  if (block.type !== 'paragraph') throw new Error('expected a paragraph block')
  const citation = block.children.find((n): n is CitationNode => n.type === 'citation')
  assert.deepEqual(citation, { type: 'citation', company: 'Nordic Industrials', page: 64 })
  const last = block.children.at(-1)
  assert.deepEqual(last, { type: 'text', text: '.' })
})

test('a company name containing "&" is captured whole', () => {
  const blocks = renderAnswer('See [H & M p.7] for details.')
  const block = blocks[0]
  if (block.type !== 'paragraph') throw new Error('expected a paragraph block')
  const citation = block.children.find((n): n is CitationNode => n.type === 'citation')
  assert.deepEqual(citation, { type: 'citation', company: 'H & M', page: 7 })
})
