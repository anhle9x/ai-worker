import { expect, test } from 'claude-code/testing'
import { chatTitle, cleanTitle, newTitles, nextTitle, notePrompt, noteRename, titleDue } from '../hooks/titles'

// hooks/titles.ts: when a fresh title is due, how an answer becomes a title, and that a chat the person renamed stays theirs.
// hooks/titles.ts: khi nào tới lúc làm tiêu đề mới, câu trả lời thành tiêu đề ra sao, và cuộc trò chuyện người dùng đã đổi tên vẫn là của họ.

test('a fresh title is due after the 4th prompt, then every 10th; slash commands and blank prompts do not count', () => {
  const t = newTitles()
  const due: number[] = []
  notePrompt(t, '/compact')
  notePrompt(t, '   ')
  notePrompt(t, 42)
  for (let i = 1; i <= 30; i++) {
    notePrompt(t, `question ${i}`)
    if (titleDue(t)) due.push(i)
  }
  expect(due).toEqual([4, 14, 24])
  expect(t.recent).toEqual(['question 25', 'question 26', 'question 27', 'question 28', 'question 29', 'question 30'])
})

test('prompts are kept on one line and clipped', () => {
  const t = newTitles()
  notePrompt(t, `  a\n\nb  ${'x'.repeat(300)}`)
  expect(t.recent[0]!.startsWith('a b x')).toBe(true)
  expect(t.recent[0]!.length).toBe(240)
})

test("the model's answer and an event's title are cleaned", () => {
  expect(cleanTitle('"Fixing the login page."\nBecause...')).toBe('Fixing the login page')
  expect(cleanTitle('## *Login page*')).toBe('Login page*')
  expect(cleanTitle('x'.repeat(80)).length).toBe(60)
  expect(chatTitle('  Plan\n for  Q4 ')).toBe('Plan for Q4')
  expect(chatTitle(undefined)).toBe('')
  expect(chatTitle('y'.repeat(100)).length).toBe(80)
})

test('a waiting title is applied once; after the person renames the chat, none is', () => {
  const t = newTitles()
  t.pending = 'Login page'
  expect(nextTitle(t)).toBe('Login page')
  expect(t.auto).toBe('Login page')
  expect(nextTitle(t)).toBeUndefined()
  // the app still shows our title: nothing changes
  // app vẫn hiện tiêu đề của plugin: không có gì đổi
  noteRename(t, 'Login page')
  expect(t.off).toBe(false)
  noteRename(t, 'My own name')
  expect(t.off).toBe(true)
  t.pending = 'Another'
  expect(nextTitle(t)).toBeUndefined()
  for (let i = 0; i < 4; i++) notePrompt(t, 'q')
  expect(titleDue(t)).toBe(false)
})

test('before the plugin set a title, the title shown is the app\'s own and is not a rename', () => {
  const t = newTitles()
  noteRename(t, 'Whatever the app chose')
  expect(t.off).toBe(false)
})
