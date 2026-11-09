import { expect, test } from 'claude-code/testing'
import { STALE_MS, applyPlan, describeTool, finishPlan, folderName, mediaPaths, sayEntry, staleSessionFiles } from '../hooks/activity'

test('tool calls read as short lines', () => {
  expect(describeTool('Bash', { command: 'ls -la', description: 'List files' })).toEqual({ verb: 'run', text: 'List files' })
  expect(describeTool('Read', { file_path: '/a/b/register.tsx' })).toEqual({ verb: 'read', text: 'register.tsx' })
  expect(describeTool('mcp__ai-workers__ask_gemini', { prompt: 'secret' })).toEqual({ verb: 'delegate', text: 'handing work to Gemini' })
  expect(describeTool('mcp__ccd_turn__update_plan', {})).toBeUndefined()
})

test('a worker line never carries the prompt', () => {
  const line = describeTool('mcp__ai-workers__ask_local', { prompt: 'John Smith, student ID 123' })
  expect(line?.text.includes('John')).toBe(false)
})

test('the plan follows items, advance, done, start and wrap-up', () => {
  let p = applyPlan(undefined, { items: [
    { content: 'One', status: 'in_progress' }, { content: 'Two', status: 'pending' }, { content: 'Three', status: 'pending' },
  ] })
  p = applyPlan(p, { advance: true })
  expect(p.map(i => i.status)).toEqual(['completed', 'in_progress', 'pending'])
  p = applyPlan(p, { done: [2], start: 3 })
  expect(p.map(i => i.status)).toEqual(['completed', 'completed', 'in_progress'])
  expect(finishPlan(p)?.every(i => i.status === 'completed')).toBe(true)
})

test('empty text says nothing; long text is cut', () => {
  expect(sayEntry('   ', 1)).toBeUndefined()
  expect(sayEntry('x'.repeat(700), 1)?.text.length).toBe(600)
})

test('a prompt and a Read show the image and video files they name', () => {
  expect(mediaPaths('@"/Users/me/Desktop/Recording 1.mp4"\nsee this')).toEqual(['/Users/me/Desktop/Recording 1.mp4'])
  expect(mediaPaths('image @/tmp/a.png and /tmp/b.JPG, file /tmp/c.ts')).toEqual(['/tmp/a.png', '/tmp/b.JPG'])
  expect(mediaPaths('nothing here')).toEqual([])
  expect(mediaPaths('@src/a.ts @"/x/Lesson 1.docx" @.env mail ocn@example.com', '/p')).toEqual(['/p/src/a.ts', '/x/Lesson 1.docx'])
  expect(describeTool('Read', { file_path: '/x/a.pdf' })?.media).toEqual(['/x/a.pdf'])
  expect(describeTool('Read', { file_path: '/x/a.ts' })?.media).toBeUndefined()
  expect(describeTool('Read', { file_path: '/x/f02.png' })).toEqual({ verb: 'read', text: 'f02.png', media: ['/x/f02.png'] })
})

test('a session is named by its last folder on every system', () => {
  expect(folderName('/Users/an/du-an')).toBe('du-an')
  expect(folderName('C:\\Users\\an\\du-an')).toBe('du-an')
  expect(folderName('C:\\Users\\an\\du-an\\')).toBe('du-an')
  expect(folderName('/')).toBe('')
})

test('only office files of sessions idle over a week are cleared, never this one', () => {
  const now = 100 * STALE_MS
  const old = now - STALE_MS - 1
  const files = [
    { name: 'cu.js', kind: 'file', mtimeMs: old },
    { name: 'moi.js', kind: 'file', mtimeMs: now - 1000 },
    { name: 'toi.js', kind: 'file', mtimeMs: old },
    { name: 'ghichu.txt', kind: 'file', mtimeMs: old },
    { name: 'thu-muc.js', kind: 'dir', mtimeMs: old },
  ]
  expect(staleSessionFiles(files, now, 'toi')).toEqual(['cu.js'])
})
