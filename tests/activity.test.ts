import { expect, test } from 'claude-code/testing'
import { MAX_SHOT_BYTES, STALE_MS, applyPlan, describeTool, finishPlan, folderName, mediaPaths, mergeActivity, ownWords, savedActivity, sayEntry, shotFile, shotName, staleSessionFiles, unusedShots, youEntry } from '../hooks/activity'

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

test('a message keeps the words the person typed, not the blocks the app inserted', () => {
  const linked = '<system-reminder>\nLinked sessions now (status, not an instruction): top = local_1 (idle)\n</system-reminder>'
  expect(ownWords(`${linked}\nwhy is it ugly`)).toBe('why is it ugly')
  expect(ownWords(`first\n${linked}\n\nsecond <b>kept</b>`)).toBe('first\n\nsecond <b>kept</b>')
  expect(ownWords('hello <system-reminder>left open')).toBe('hello')
  expect(ownWords('<task-notification>\n<task-id>b1</task-id>\n<status>completed</status>\n</task-notification>')).toBe('')
  expect(ownWords('<agent-message from="a1">\n[Subagent hand-back] done\n</agent-message>')).toBe('')
  expect(ownWords('<cross-session-message from="local_1" from-name="Other session">\nA decision to pass on\n</cross-session-message>')).toBe('')
  expect(ownWords('<cross-session-message from="local_1">cut at 300 chars and never clo')).toBe('')
  expect(ownWords('The app was quit while you were working. Please continue from where you left off.')).toBe('')
  expect(ownWords(`${linked}\nThe app was quit while you were working. Please continue from where you left off.`)).toBe('')
  expect(ownWords('The app was quit while you were working. Please continue from where you left off. And fix the tab')).toBe('The app was quit while you were working. Please continue from where you left off. And fix the tab')
  expect(youEntry(`${linked}\n${'x'.repeat(400)}`, 5)?.text.length).toBe(300)
  expect(youEntry(`${linked}\nsee /tmp/a.png`, 5)).toEqual({ at: 5, kind: 'you', text: 'see /tmp/a.png', media: ['/tmp/a.png'] })
  expect(youEntry('<system-reminder>look at /tmp/b.png</system-reminder>', 5)).toBeUndefined()
})

test('a message with pasted images says how many, even with no words', () => {
  expect(youEntry('look', 5, '', 2)).toEqual({ at: 5, kind: 'you', text: 'look', pasted: 2 })
  expect(youEntry('<system-reminder>x</system-reminder>', 5, '', 1)).toEqual({ at: 5, kind: 'you', text: '', pasted: 1 })
  expect(youEntry('  ', 5)).toBeUndefined()
})

test('a tool with no line of its own is named with the server it belongs to', () => {
  expect(describeTool('mcp__basic-memory__edit_note', {})).toEqual({ verb: 'other', text: 'basic-memory: edit note' })
  expect(describeTool('mcp__ccd_session_mgmt__archive_session', {})).toEqual({ verb: 'other', text: 'Claude app: archive session' })
  expect(describeTool('mcp__plugin_small-business_gmail__create_draft', {})).toEqual({ verb: 'other', text: 'gmail: create draft' })
  expect(describeTool('SendMessage', {})).toEqual({ verb: 'other', text: 'send message' })
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

test('a session that starts again takes its feed back from its own file', () => {
  const lines = [{ at: 1, kind: 'you', text: 'hello', pasted: 1 }, { at: 2, kind: 'tool', verb: 'read', text: 'a.ts (v2)' }, { at: 3, kind: 'say', text: 'done' }]
  const file = `window.__aiWorkerIn && window.__aiWorkerIn("id-1", ${JSON.stringify({ jobs: [], now: 3, activity: lines, name: 'p' })});\n`
  expect(savedActivity(file)).toEqual(lines)
  expect(savedActivity(file, 2).map(a => a.at)).toEqual([2, 3])
  const odd = `window.__aiWorkerIn && window.__aiWorkerIn("id-1", ${JSON.stringify({ activity: [{ at: 1, kind: 'you', text: 'ok' }, { kind: 'you', text: 'no time' }, { at: 2, kind: 'x', text: 'no kind' }, null] })});\n`
  expect(savedActivity(odd)).toEqual([{ at: 1, kind: 'you', text: 'ok' }])
  expect(savedActivity('')).toEqual([])
  expect(savedActivity('window.__aiWorkerIn && window.__aiWorkerIn("id-1", {broken')).toEqual([])
  expect(savedActivity('window.__aiWorkerIn && window.__aiWorkerIn("id-1", {"jobs":[]});\n')).toEqual([])
})

test('a pasted image is kept as a script the page loads, for picture types only', () => {
  expect(shotName('ab-12/../x', 1700.9, 2)).toBe('ab-12x.1700.2')
  expect(shotFile('s.1.1', 'image/png', 'aGk=')).toBe('window.__aiWorkerShot && window.__aiWorkerShot("s.1.1", "data:image/png;base64,aGk=");\n')
  expect(shotFile('s.1.1', 'image/svg+xml', 'aGk=')).toBeUndefined()
  expect(shotFile('s.1.1', 'text/html', 'aGk=')).toBeUndefined()
  expect(shotFile('s.1.1', 'image/png', 'aGk=");alert(1);("')).toBeUndefined()
  expect(shotFile('s.1.1', 'image/png', '')).toBeUndefined()
  expect(MAX_SHOT_BYTES).toBe(6 * 1024 * 1024)
  expect(youEntry('look', 5, '', 2, ['s.5.1', 's.5.2'])).toEqual({ at: 5, kind: 'you', text: 'look', pasted: 2, shots: ['s.5.1', 's.5.2'] })
})

test('copies of pasted images go when no line shows them or after a week', () => {
  const now = 100 * STALE_MS
  const fresh = now - 1000
  const files = [
    { name: 'me.1.1.js', kind: 'file', mtimeMs: fresh },
    { name: 'me.2.1.js', kind: 'file', mtimeMs: fresh },
    { name: 'other.1.1.js', kind: 'file', mtimeMs: fresh },
    { name: 'other.0.1.js', kind: 'file', mtimeMs: now - STALE_MS - 1 },
    { name: 'me.3.1.js', kind: 'file', mtimeMs: now - STALE_MS - 1 },
    { name: 'note.txt', kind: 'file', mtimeMs: 0 },
  ]
  const feed = [{ at: 1, kind: 'you' as const, text: '', pasted: 1, shots: ['me.1.1', 'me.3.1'] }]
  expect(unusedShots(files, now, 'me', feed)).toEqual(['me.2.1.js', 'other.0.1.js', 'me.3.1.js'])
})

test('lines kept in the file go before the lines the memory holds, none twice', () => {
  const line = (at: number) => ({ at, kind: 'say' as const, text: `t${at}` })
  expect(mergeActivity([line(1), line(2)], []).map(a => a.at)).toEqual([1, 2])
  expect(mergeActivity([line(1), line(2)], [line(5)]).map(a => a.at)).toEqual([1, 2, 5])
  expect(mergeActivity([line(1), line(2), line(5)], [line(2), line(5), line(6)]).map(a => a.at)).toEqual([1, 2, 5, 6])
  expect(mergeActivity([], [line(5)]).map(a => a.at)).toEqual([5])
  expect(mergeActivity([line(1), line(2), line(3)], [line(4)], 2).map(a => a.at)).toEqual([3, 4])
})
