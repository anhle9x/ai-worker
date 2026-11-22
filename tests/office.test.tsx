import type { On } from 'claude-code'
import { expect, mock, test } from 'claude-code/testing'
import { assistantName } from '../hooks/office'

const PANE = {
  plugin: 'ai-worker',
  component: 'Pane',
  requestId: 'ai-worker',
  props: {
    title: 'AI Office',
    isFocused: false,
    bodyColumns: 60,
    placement: 'dock',
    scroll: { offset: 0, bodyRows: 30 },
    view: {},
  },
} as const

const ASK = 'mcp__ai-workers__ask_gemini'
const GET = 'mcp__ai-workers__get_gemini_result'

test('a quick Gemini task shows as done, without its prompt', async ($, on) => {
  mock.clock(on)
  on('command.register', () => ({ value: { command: 'office' } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('tool.call', () => ({ result: 'Secret result: John Smith' }))

  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  await $.tool.call({ tool: ASK, prompt: 'Look up the latest price for John Smith' })

  for (const surface of ['terminal', 'desktop'] as const) {
    const ui = await $.ui.mount({ ...PANE, surface })
    const row = await ui.find({ type: 'Text', text: /Web research done/ })
    expect(row).toBeDefined()
    const leak = await ui.find({ type: 'Text', text: /John/ })
    expect(leak).toBeUndefined()
    await ui.unmount()
  }
})

test('a slow task stays busy until its result arrives', async ($, on) => {
  mock.clock(on)
  on('command.register', () => ({ value: { command: 'office' } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  let finished = false
  on('tool.call', (_, e) =>
    e.tool === ASK || !finished
      ? { result: 'Gemini is still working (25 seconds so far). job_id: job-7. Call get_gemini_result with this job_id to get the result.' }
      : { result: 'All done' },
  )

  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  await $.tool.call({ tool: ASK, prompt: 'critique this plan' })

  let ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect(await ui.find({ type: 'Text', text: /working on Critique/ })).toBeDefined()
  await ui.unmount()

  await $.tool.call({ tool: GET, job_id: 'job-7' })
  ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect(await ui.find({ type: 'Text', text: /working on Critique/ })).toBeDefined()
  await ui.unmount()

  finished = true
  await $.tool.call({ tool: GET, job_id: 'job-7' })
  ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect(await ui.find({ type: 'Text', text: /Critique done/ })).toBeDefined()
  await ui.unmount()
})

test('a failed task shows an error', async ($, on) => {
  mock.clock(on)
  on('command.register', () => ({ value: { command: 'office' } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('tool.call', () => ({ isError: true, result: 'token expired' }))

  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  await $.tool.call({ tool: 'mcp__ai-workers__ask_chatgpt', prompt: 'review' })

  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect(await ui.find({ type: 'Text', text: /failed: Code review/ })).toBeDefined()
  await ui.unmount()
})

function engine(on: On) {
  mock.clock(on)
  on('command.register', () => ({ value: { command: 'office' } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
}

test('Claude waits on the person while a question is open and after a turn ends on one', async ($, on) => {
  engine(on)
  let seen = ''
  on('tool.call', async (_, e) => {
    if (e.tool === 'AskUserQuestion') {
      const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
      seen = (await ui.find({ type: 'Text', text: /waiting for your answer/ }))?.text ?? ''
      await ui.unmount()
    }
    return { result: 'ok' }
  })
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  await $.tool.call({ tool: 'AskUserQuestion', questions: [] })
  expect(seen).toContain('waiting for your answer')

  let ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect(await ui.find({ type: 'Text', text: /waiting for your answer/ })).toBeUndefined()
  await ui.unmount()

  await $.tool.call({ tool: 'mcp__ccd_turn__wrap_up', recap: 'x', ask: 'Continue?' })
  ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect(await ui.find({ type: 'Text', text: /waiting for your answer/ })).toBeDefined()
  await ui.unmount()
})

test('edits are listed, and a secrets file keeps no lines', async ($, on) => {
  engine(on)
  on('tool.call', (_, e) => {
    const path = (e as unknown as { file_path: string }).file_path
    return {
      result: {
        filePath: path,
        structuredPatch: [{ oldStart: 1, oldLines: 1, newStart: 1, newLines: 2, lines: ['-a', '+b', '+c'] }],
      },
    }
  })
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  await $.tool.call({ tool: 'Edit', file_path: '/p/app.ts', old_string: 'a', new_string: 'b\nc' })
  await $.tool.call({ tool: 'Edit', file_path: '/p/.env', old_string: 'K=1', new_string: 'K=2' })

  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect(await ui.find({ type: 'Text', text: /Files Claude edited: 2 times/ })).toBeDefined()
  await ui.unmount()
})

test('a subagent is named by its type and model, not just as an assistant', async ($, on) => {
  engine(on)
  let seen = ''
  on('session.cwd', () => ({ value: '/' }))
  on('env.get', () => ({ value: undefined }))
  on('turn.start', () => ({ turnId: 't1' }))
  on('agent.spawn', () => ({ model: 'claude-haiku-4-5-20251001', agentId: 'a1' }))
  on('tool.call', async (_, e) => {
    if (e.tool === 'Agent') {
      await $.agent.spawn({ prompt: 'Find where the office is drawn', subagentType: 'Explore', description: 'Find the drawing' })
      const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
      seen = (await ui.find({ type: 'Text', text: /Explore/ }))?.text ?? ''
      await ui.unmount()
    }
    return { result: 'ok' }
  })
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  await $.turn.start({ text: 'Where is the office drawn?', turnId: 't1' })
  await $.tool.call({ tool: 'Agent', subagent_type: 'Explore', description: 'Find the drawing', prompt: 'Find where the office is drawn' })
  expect(seen).toContain('Explore (Haiku 4.5)')
})

test('assistantName reads the model the way the board shows it', () => {
  expect(assistantName('Explore', 'claude-haiku-4-5-20251001')).toBe('Explore (Haiku 4.5)')
  expect(assistantName('general-purpose', 'claude-sonnet-5-5')).toBe('Sonnet 5.5')
  expect(assistantName('general-purpose', 'sonnet')).toBe('Sonnet')
  expect(assistantName('fork', 'claude-opus-5-5[1m]')).toBe('Opus 5.5')
  expect(assistantName('Plan', 'claude-sonnet-4-20250514')).toBe('Plan (Sonnet 4)')
  expect(assistantName('Explore')).toBe('Explore')
  expect(assistantName('Explore', 'inherit')).toBe('Explore')
  expect(assistantName('general-purpose', 'some/odd model')).toBe('general-purpose')
})
