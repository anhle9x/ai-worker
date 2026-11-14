import { expect, test } from 'claude-code/testing'
import { IMAGE_SCHEMA, imageArgv, imageTargets, newImages, safeImageName, sendingNeedsAsking, sendingRefusal, agyArgv, codexArgv, codexInput, isBatchLauncher, delegationRules, gemmaAnswer, gemmaRequest, mcpConfigured, ownTools, pickGemma } from '../hooks/workers'

test('the largest installed Gemma is used, other models ignored', () => {
  const tags = (...n: string[]) => JSON.stringify({ models: n.map(name => ({ name })) })
  expect(pickGemma(tags('llama3:8b', 'gemma4:e4b', 'gemma4:26b'))).toBe('gemma4:26b')
  expect(pickGemma(tags('gemma4:e2b', 'gemma4:e4b'))).toBe('gemma4:e4b')
  expect(pickGemma(tags('llama3:8b'))).toBe(undefined)
  expect(pickGemma('not json')).toBe(undefined)
})

test('Gemma request and answer', () => {
  const body = JSON.parse(gemmaRequest('gemma4:e4b', 'Summarize'))
  expect(body.model).toBe('gemma4:e4b')
  expect(body.stream).toBe(false)
  expect(body.messages[0].content.endsWith('Summarize')).toBe(true)
  expect(gemmaAnswer('{"message":{"content":" The result "}}')).toEqual({ text: 'The result', isError: false })
  expect(gemmaAnswer('{"error":"model not found"}').isError).toBe(true)
  expect(gemmaAnswer('').isError).toBe(true)
})

test('text for Codex never becomes an argument, and batch launchers are recognised', () => {
  const hidden = 'hello" & echo x> marker.txt & rem "'
  expect(codexArgv('C:\\npm\\codex.cmd', 'out.txt', 'vua').join(' ')).not.toContain('echo')
  expect(codexInput(hidden).endsWith(hidden)).toBe(true)
  for (const p of ['C:\\npm\\codex.cmd', 'C:\\x\\AGY.BAT']) expect(isBatchLauncher(p)).toBe(true)
  for (const p of ['C:\\x\\agy.exe', '/usr/local/bin/codex', 'cmd-tool']) expect(isBatchLauncher(p)).toBe(false)
})

test('Codex runs read-only and writes its last message to a file', () => {
  const a = codexArgv('/x/codex', '/tmp/out.txt')
  expect(a.slice(0, 2)).toEqual(['/x/codex', 'exec'])
  expect(a[a.indexOf('-s') + 1]).toBe('read-only')
  expect(a[a.indexOf('-o') + 1]).toBe('/tmp/out.txt')
  expect(a[a.length - 1]).toBe('-')
  expect(codexInput('review').endsWith('review')).toBe(true)
  expect(a).toContain('model_reasoning_effort="medium"')
  expect(codexArgv('/x/codex', '/o', 'ky')).toContain('model_reasoning_effort="high"')
  expect(agyArgv('/x/agy', 'p', 'nhanh').slice(-2)).toEqual(['--model', 'gemini-3.8-flash-low'])
  expect(agyArgv('/x/agy', 'p', 'la-gi').slice(-1)[0]).toBe('gemini-3.8-flash-medium')
})

test('only the helpers a machine has become tools and rules', () => {
  expect(ownTools({}).length).toBe(0)
  expect(delegationRules({})).toBe(undefined)
  const t = ownTools({ gemma: 'gemma4:e4b', chatgpt: '/x/codex' })
  expect(t.map(x => x.name)).toEqual(['ask_local', 'ask_chatgpt'])
  const rules = delegationRules({ gemma: 'gemma4:e4b', chatgpt: '/x/codex' }) ?? ''
  expect(rules.includes('ask_local')).toBe(true)
  expect(rules.includes('ask_gemini')).toBe(false)
  expect(rules.includes('Never send to ChatGPT')).toBe(true)
})

test('an ai-workers server set up in an MCP config is found before it connects', () => {
  expect(mcpConfigured(JSON.stringify({ mcpServers: { 'ai-workers': { command: 'node' } } }))).toBe(true)
  expect(mcpConfigured(JSON.stringify({ projects: { '/x': { mcpServers: { 'ai-workers': {} } } } }))).toBe(true)
  expect(mcpConfigured(JSON.stringify({ mcpServers: { playwright: {} } }))).toBe(false)
  expect(mcpConfigured('not json')).toBe(false)
})

test('text for ChatGPT or Gemini is sent only with an allow rule or a clear yes', () => {
  expect(sendingNeedsAsking('ask', 'ChatGPT')).toBe(true)
  // an allow rule the person set for this tool: no question
  expect(sendingNeedsAsking('allow', 'ChatGPT', true)).toBe(false)
  // a permission mode that asks nothing allows every tool, with no rule behind it: the text still leaves the computer, so ask
  expect(sendingNeedsAsking('allow', 'ChatGPT')).toBe(true)
  expect(sendingNeedsAsking('allow', 'Gemini', false)).toBe(true)
  // Gemma stays on this computer
  expect(sendingNeedsAsking('ask', undefined)).toBe(false)
  expect(sendingNeedsAsking('allow', undefined)).toBe(false)
  expect(sendingRefusal('allow', undefined, 'Send')).toBe(undefined)
  expect(sendingRefusal('ask', 'Send', 'Send')).toBe(undefined)
  expect(sendingRefusal('ask', 'Do not send', 'Send')).toBeTruthy()
  // the question failed or nobody answered
  // câu hỏi bị lỗi hoặc không ai trả lời
  expect(sendingRefusal('ask', '', 'Send')).toBeTruthy()
  expect(sendingRefusal('deny', undefined, 'Send')).toBeTruthy()
  expect(sendingRefusal('deny', 'Send', 'Send')).toBeTruthy()
})

test('Gemini on the machine also brings the image tool and its rule', () => {
  const t = ownTools({ gemini: '/x/agy' })
  expect(t.map(x => x.name)).toEqual(['ask_gemini', 'generate_image'])
  expect(t[1]?.inputSchema).toBe(IMAGE_SCHEMA)
  expect((delegationRules({ gemini: '/x/agy' }) ?? '').includes('generate_image')).toBe(true)
  expect(ownTools({ chatgpt: '/x/codex' }).some(x => x.name === 'generate_image')).toBe(false)
  expect(imageArgv('/x/agy', 'a cat').slice(0, 2)).toEqual(['/x/agy', '-p'])
  expect(imageArgv('/x/agy', 'a cat')[2]?.endsWith('a cat')).toBe(true)
})

test('only new, untaken images count, oldest first', () => {
  const files = [
    { path: '/b/a.png', mtimeMs: 300 },
    { path: '/b/old.png', mtimeMs: 50 },
    { path: '/b/notes.md', mtimeMs: 400 },
    { path: '/b/b.JPG', mtimeMs: 200 },
    { path: '/b/c.webp', mtimeMs: 250 },
  ]
  expect(newImages(files, 100, new Set(['/b/c.webp']))).toEqual(['/b/b.JPG', '/b/a.png'])
})

test('image file names are safe and never overwrite', () => {
  expect(safeImageName('../../etc/x')).toBe('etc-x')
  expect(safeImageName('course banner.png')).toBe('course-banner')
  expect(safeImageName(undefined)).toBe('')
  const taken = new Set(['/p/banner.png'])
  expect(imageTargets(['/b/d1.png', '/b/d2.PNG'], '/p', 'banner', p => taken.has(p))).toEqual(['/p/banner-draft-1.png', '/p/banner-2.png'])
  expect(imageTargets(['/b/x\\gemini.jpeg'], '/p', '', () => false)).toEqual(['/p/gemini.jpeg'])
})
