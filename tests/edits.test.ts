import { expect, test } from 'claude-code/testing'
import { addUsage, buildFileEdit, shortCount, toUsage } from '../hooks/edits'

test('a patch becomes counted lines', () => {
  const e = buildFileEdit('Edit', { file_path: '/a.ts' }, {
    filePath: '/a.ts',
    structuredPatch: [{ oldStart: 3, oldLines: 2, newStart: 3, newLines: 3, lines: [' x', '-y', '+y2', '+z'] }],
  }, 1, 'k')
  expect(e?.added).toBe(2)
  expect(e?.removed).toBe(1)
  expect(e?.lines[0]).toBe('@@ -3,2 +3,3 @@')
})

test('a secrets file keeps its name and counts, never its lines', () => {
  const e = buildFileEdit('Write', { file_path: '/p/.env.local' }, { filePath: '/p/.env.local', type: 'create', content: 'API_KEY=abc', structuredPatch: [] }, 1, 'k')
  expect(e?.isHidden).toBe(true)
  expect(e?.lines.length).toBe(0)
  expect(e?.added).toBe(1)
})

test('a staged edit is not recorded', () => {
  expect(buildFileEdit('Edit', { file_path: '/a' }, { filePath: '/a', staged: true }, 1, 'k')).toBeUndefined()
})

test('usage adds up across turns', () => {
  const t = { input_tokens: 10, output_tokens: 5, cache_read_input_tokens: 100, cache_creation_input_tokens: 7 }
  const sum = addUsage(addUsage(undefined, toUsage(t, 1)), toUsage(t, 1))
  expect(sum).toEqual({ input: 20, output: 10, cacheRead: 200, cacheWrite: 14, turns: 2 })
  expect(shortCount(45678)).toBe('45.7k')
})
