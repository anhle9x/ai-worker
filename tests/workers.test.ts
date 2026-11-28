import { expect, test } from 'claude-code/testing'
import { IMAGE_SCHEMA, imageArgv, imageTargets, newImages, safeImageName, sendingNeedsAsking, sendingRefusal, agyArgv, codexArgv, codexInput, isBatchLauncher, delegationRules, gemmaAnswer, gemmaServerIn, gemmaFallsBack, gemmaFellBack, gemmaLabel, gemmaPlace, gemmaTarget, gemmaWorkers, readGemmaMode, PROMPT_WHERE_SCHEMA, gemmaRequest, gemmaServerAnswer, gemmaServerArgv, mcpConfigured, ownTools, pickGemma, readGemmaServer } from '../hooks/workers'

test('only gemma4:26b counts as Gemma on this computer, the small sizes are ignored', () => {
  const tags = (...n: string[]) => JSON.stringify({ models: n.map(name => ({ name })) })
  expect(pickGemma(tags('llama3:8b', 'gemma4:e4b', 'gemma4:26b'))).toBe('gemma4:26b')
  expect(pickGemma(tags('gemma4:e2b', 'gemma4:e4b'))).toBe(undefined)
  expect(pickGemma(tags('llama3:8b'))).toBe(undefined)
  expect(pickGemma('not json')).toBe(undefined)
})

test('Gemma request and answer', () => {
  const body = JSON.parse(gemmaRequest('gemma4:26b', 'Summarize'))
  expect(body.model).toBe('gemma4:26b')
  expect(body.stream).toBe(false)
  // thinking off: no outline written before the answer
  // tắt suy nghĩ: không viết dàn ý trước câu trả lời
  expect(body.think).toBe(false)
  expect(body.messages[0].content.endsWith('Summarize')).toBe(true)
  expect(gemmaAnswer('{"message":{"content":" The result "}}')).toEqual({ text: 'The result', isError: false })
  expect(gemmaAnswer('{"error":"model not found"}').isError).toBe(true)
  expect(gemmaAnswer('').isError).toBe(true)
})

test('a computer that runs Gemma itself never moves to the server by itself', () => {
  const server = { url: 'https://gemma.example.com', host: 'gemma.example.com', model: 'gemma4:31b' }
  // it has the model: here, whatever else is set
  expect(gemmaPlace('has', false, server)).toBe('here')
  // it ran Gemma before and Ollama is merely off: still here, so the call says to open Ollama
  expect(gemmaPlace('off', true, server)).toBe('here')
  // a weak computer: the server when one is set, else no Gemma
  expect(gemmaPlace('off', false, server)).toBe('server')
  expect(gemmaPlace('lacks', false, server)).toBe('server')
  expect(gemmaPlace('off', false, undefined)).toBe('none')
  // Ollama answers and the model is gone: the person removed it, the server may take over
  expect(gemmaPlace('lacks', true, server)).toBe('server')
  expect(gemmaPlace('lacks', true, undefined)).toBe('none')
})

test('the Gemma server address is https, or this computer itself; the key comes only from the private file', () => {
  expect(readGemmaServer([{ url: 'https://gemma.example.com/' }])).toEqual({ url: 'https://gemma.example.com', host: 'gemma.example.com', model: 'gemma4:31b' })
  expect(readGemmaServer([{ url: 'https://gemma.example.com:8443/ai' }])?.url).toBe('https://gemma.example.com:8443/ai')
  expect(readGemmaServer([{ url: 'http://127.0.0.1:11500' }])?.host).toBe('127.0.0.1')
  expect(readGemmaServer([{ url: 'http://localhost:11500' }])?.host).toBe('localhost')
  for (const url of ['http://gemma.example.com', 'http://10.0.0.5:11434', 'https://user:pw@gemma.example.com', 'https://gemma.example.com/?k=1', 'ftp://gemma.example.com', 'gemma.example.com', '', 7])
    expect(readGemmaServer([{ url }])).toBe(undefined)
  expect(readGemmaServer([undefined, 'x', {}])).toBe(undefined)
  // the later setting wins; a bad one does not wipe a good one
  expect(readGemmaServer([{ url: 'https://a.example.com' }, { url: 'https://b.example.com' }])?.host).toBe('b.example.com')
  expect(readGemmaServer([{ url: 'https://a.example.com' }, { url: 'http://b.example.com' }])?.host).toBe('a.example.com')
  // a key in a file the office page reads is ignored
  const key = 'k'.repeat(40)
  expect(readGemmaServer([{ url: 'https://a.example.com', key }])?.key).toBe(undefined)
  expect(readGemmaServer([{ url: 'https://a.example.com' }], { key })?.key).toBe(key)
  expect(readGemmaServer([], { url: 'https://c.example.com', key })).toEqual({ url: 'https://c.example.com', host: 'c.example.com', model: 'gemma4:31b', key })
  expect(readGemmaServer([{ url: 'https://a.example.com' }], { key: 'short' })?.key).toBe(undefined)
  expect(readGemmaServer([], { key })).toBe(undefined)
  // the server runs gemma4:31b unless its settings name another model
  expect(readGemmaServer([{ url: 'https://a.example.com', model: 'gemma4:26b' }])?.model).toBe('gemma4:26b')
  expect(readGemmaServer([{ url: 'https://a.example.com', model: 'x y; rm' }])?.model).toBe('gemma4:31b')
})

test('an address set on this computer beats the one the dashboard announced, and the key never goes to the announced one', () => {
  const key = 'k'.repeat(40)
  const board = { url: 'https://aiworker.example.com/gemma', model: 'gemma4:26b' }
  expect(readGemmaServer([], undefined, board)).toEqual({ url: 'https://aiworker.example.com/gemma', host: 'aiworker.example.com', model: 'gemma4:26b' })
  expect(readGemmaServer([{ url: 'https://mine.example.com' }], undefined, board)?.host).toBe('mine.example.com')
  expect(readGemmaServer([], { url: 'https://mine.example.com', key }, board)?.key).toBe(key)
  // the dashboard's address with the key of gemma-server.json: the key stays here
  // địa chỉ của bảng tổng cùng khoá trong gemma-server.json: khoá ở lại đây
  expect(readGemmaServer([], { key }, board)?.key).toBe(undefined)
  // from the dashboard only https, not even this computer
  // từ bảng tổng chỉ https, kể cả địa chỉ của chính máy này
  expect(readGemmaServer([], undefined, { url: 'http://127.0.0.1:11500' })).toBe(undefined)
})

test('the answer to a send: an address to keep, null to drop, nothing to leave as it is', () => {
  expect(gemmaServerIn(JSON.stringify({ ok: true, gemmaServer: { url: 'https://aiworker.example.com/gemma/', model: 'gemma4:26b' } }))).toEqual({ url: 'https://aiworker.example.com/gemma', model: 'gemma4:26b' })
  expect(gemmaServerIn(JSON.stringify({ gemmaServer: { url: 'https://aiworker.example.com/gemma' } }))).toEqual({ url: 'https://aiworker.example.com/gemma' })
  expect(gemmaServerIn(JSON.stringify({ gemmaServer: { url: 'https://a.example.com', model: 'x y' } }))).toEqual({ url: 'https://a.example.com' })
  expect(gemmaServerIn(JSON.stringify({ gemmaServer: null }))).toBe(null)
  for (const answer of ['{"ok":true}', 'not json', '{"gemmaServer":{"url":"http://a.example.com"}}', '{"gemmaServer":"https://a.example.com"}', '{"gemmaServer":{}}'])
    expect([answer, gemmaServerIn(answer)]).toEqual([answer, undefined])
})

test('asking Gemma on a server: the key stays off the command line, and each failure says what to do', () => {
  const argv = gemmaServerArgv({ url: 'https://gemma.example.com', host: 'gemma.example.com', model: 'gemma4:31b', key: 'k'.repeat(40) }, '/w/h.txt', 540)
  expect(argv.join(' ')).not.toContain('kkkk')
  expect(argv).toContain('@/w/h.txt')
  expect(argv).toContain('https://gemma.example.com/api/chat')
  expect(argv.slice(-2)).toEqual(['-d', '@-'])
  expect(gemmaServerAnswer('{"message":{"content":"Done"}}\n200', 'gemma.example.com')).toEqual({ text: 'Done', isError: false })
  for (const [out, word] of [['Forbidden\n403', 'refused'], ['\n401', 'refused'], ['\n503', 'busy'], ['\n000', 'reach'], ['', 'reach'], ['<html>\n502', 'usable']] as const) {
    const g = gemmaServerAnswer(out, 'gemma.example.com')
    expect(g.isError).toBe(true)
    expect(g.text).toContain(word)
    expect(g.text).toContain('gemma.example.com')
  }
  expect(gemmaServerAnswer('{"error":"model not found"}\n404', 'h').text).toContain('model not found')
})

test('who gets which Gemma: one line per case', () => {
  const server = { url: 'https://gemma.example.com', host: 'gemma.example.com', model: 'gemma4:31b' }
  const both = { gemma: 'gemma4:26b', gemmaAlso: { host: 'gemma.example.com', model: 'gemma4:31b' } }
  // runs Gemma itself, no server: here only
  expect(gemmaWorkers('has', true, undefined, 'auto')).toEqual({ gemma: 'gemma4:26b' })
  // runs Gemma itself and has a server: both, Claude chooses
  expect(gemmaWorkers('has', false, server, 'auto')).toEqual(both)
  // its Ollama is merely off: still both, so a call for here says to open Ollama
  expect(gemmaWorkers('off', true, server, 'auto')).toEqual(both)
  // the person chose always here, or always the server (this computer then stands behind it)
  expect(gemmaWorkers('has', true, server, 'here')).toEqual({ gemma: 'gemma4:26b' })
  expect(gemmaWorkers('has', true, server, 'server')).toEqual({ gemma: 'gemma4:31b', gemmaServer: 'gemma.example.com', gemmaBackup: true })
  // too weak: the server alone whatever the mode, or nothing
  for (const mode of ['auto', 'here', 'server'] as const) expect(gemmaWorkers('lacks', false, server, mode)).toEqual({ gemma: 'gemma4:31b', gemmaServer: 'gemma.example.com' })
  expect(gemmaWorkers('off', false, undefined, 'auto')).toEqual({})
  expect([readGemmaMode('here'), readGemmaMode('server'), readGemmaMode('auto'), readGemmaMode('x'), readGemmaMode(undefined)]).toEqual(['here', 'server', 'auto', 'auto', 'auto'])
  // where one call goes
  expect([gemmaTarget(both, undefined), gemmaTarget(both, 'here'), gemmaTarget(both, 'server'), gemmaTarget(both, 'x')]).toEqual(['here', 'here', 'server', 'here'])
  expect(gemmaTarget({ gemma: 'gemma4:26b' }, 'server')).toBe('here')
  expect(gemmaTarget({ gemma: 'gemma4:31b', gemmaServer: 'h' }, 'here')).toBe('server')
  // who can answer itself when the server fails
  expect([gemmaFallsBack(both), gemmaFallsBack({ gemma: 'm', gemmaServer: 'h', gemmaBackup: true }), gemmaFallsBack({ gemma: 'm', gemmaServer: 'h' }), gemmaFallsBack({ gemma: 'm' })]).toEqual([true, true, false, false])
})

test('an answer given here in place of the server says so; with both down, both errors are told', () => {
  const ok = gemmaFellBack('The server is off.', { text: 'Done', isError: false })
  expect(ok.isError).toBe(false)
  expect(ok.text.startsWith('[Answered by Gemma on this computer (gemma4:26b), not by the server.')).toBe(true)
  expect(ok.text).toContain('The server is off.')
  expect(ok.text.endsWith('Done')).toBe(true)
  const bad = gemmaFellBack('The server is off.', { text: 'Ollama is off.', isError: true })
  expect(bad.isError).toBe(true)
  expect(bad.text).toContain('The server is off.')
  expect(bad.text).toContain('Ollama is off.')
})

test('with both, the tool takes where and the rules keep sensitive data on this computer', () => {
  const both = { gemma: 'gemma4:26b', gemmaAlso: { host: 'gemma.example.com', model: 'gemma4:31b' } }
  const tool = ownTools(both)[0]
  expect(tool?.inputSchema).toBe(PROMPT_WHERE_SCHEMA)
  expect(PROMPT_WHERE_SCHEMA.properties.where.enum).toEqual(['here', 'server'])
  expect(PROMPT_WHERE_SCHEMA.properties.where.description).toContain('not sure')
  expect(ownTools({ gemma: 'gemma4:26b' })[0]?.inputSchema).not.toBe(PROMPT_WHERE_SCHEMA)
  const rules = delegationRules(both) ?? ''
  expect(rules).toContain('Gemma on this computer (tool ask_local, gemma4:26b)')
  expect(rules).toContain('Gemma on the server gemma.example.com (tool ask_local with where "server", gemma4:31b)')
  expect(rules).toContain('treat it as sensitive and keep it on this computer')
  expect(rules).toContain('asked before each send')
  expect(rules).toContain('Gemma on this computer answers instead')
})

test('tools, rules and the dashboard say where Gemma runs', () => {
  const here = { gemma: 'gemma4:26b' }
  const there = { gemma: 'gemma4:31b', gemmaServer: 'gemma.example.com' }
  expect(ownTools(here)[0]?.description).toContain('does NOT leave the computer')
  expect(ownTools(there)[0]?.description).toContain('gemma.example.com')
  expect(ownTools(there)[0]?.description).not.toContain('does NOT leave')
  expect(delegationRules(here)).toContain('runs on this computer')
  expect(delegationRules(there)).toContain('not on this computer')
  expect(delegationRules(there)).toContain('asked before each send')
  expect(delegationRules({ chatgpt: '/x/codex' })).toContain('This computer has no Gemma')
  expect(gemmaLabel(here)).toBe('gemma4:26b')
  expect(gemmaLabel(there)).toBe('gemma4:31b (server)')
  expect(gemmaLabel({})).toBe(undefined)
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
  const t = ownTools({ gemma: 'gemma4:26b', chatgpt: '/x/codex' })
  expect(t.map(x => x.name)).toEqual(['ask_local', 'ask_chatgpt'])
  const rules = delegationRules({ gemma: 'gemma4:26b', chatgpt: '/x/codex' }) ?? ''
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
