import type { On } from 'claude-code'
import { expect, mock, test, type TestBody } from 'claude-code/testing'
import { voiceSettingsCommand, voiceSteps } from '../hooks/voice'

type Engine = Parameters<TestBody>[0]

const MAC_PAGE = ['open', 'x-apple.systempreferences:com.apple.Keyboard-Settings.extension?Dictation']
const WINDOWS_PAGE = ['cmd', '/d', '/c', 'start', 'ms-settings:regionlanguage']

test('each system has its own settings page and its own steps', () => {
  expect(voiceSettingsCommand('Mac')).toEqual(MAC_PAGE)
  expect(voiceSettingsCommand('Windows')).toEqual(WINDOWS_PAGE)
  expect(voiceSettingsCommand('Linux')).toBe(undefined)

  const mac = voiceSteps('Mac', true)
  expect(mac).toContain('The Keyboard page of System Settings is now open.')
  expect(mac).toContain('1. Scroll down to "Dictation".')
  expect(mac).toContain('for example Vietnamese')
  // the person is told where their voice goes before they speak a name
  expect(mac).toContain('on this Mac or sent to Apple')
  expect(mac).not.toContain('Windows')

  const windows = voiceSteps('Windows', true)
  expect(windows).toContain('The "Language & region" page of Settings is now open.')
  expect(windows).toContain('3. Press the Windows key + H')
  expect(windows).toContain('sends your voice to Microsoft')
  expect(windows).not.toContain('Apple')

  expect(voiceSteps('Linux', false)).toContain('On Linux the plugin knows no built-in dictation to open.')
})

test('when the page did not open, the steps say how to get there by hand', () => {
  expect(voiceSteps('Mac', false)).toContain('Open the Apple menu, then System Settings, then Keyboard.')
  expect(voiceSteps('Mac', false)).not.toContain('is now open')
  expect(voiceSteps('Windows', false)).toContain('Open Start, then Settings, then "Time & language", then "Language & region".')
  expect(voiceSteps('Windows', false)).not.toContain('is now open')
})

/** A computer of the given system. `opens` says whether its settings page can be opened. Returns every command the plugin ran. */
function computer(on: On, system: 'Darwin' | 'Linux' | 'Windows', opens = true): string[][] {
  const ran: string[][] = []
  mock.clock(on)
  mock.store(on)
  mock.env(on, system === 'Windows' ? { OS: 'Windows_NT', USERPROFILE: 'C:\\Users\\an' } : { HOME: '/Users/an' })
  on('command.register', () => ({ value: { command: 'office' } }))
  on('command.run', () => ({ text: 'not the plugin' }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.toast', () => ({ value: undefined }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('fs.exists', () => ({ value: false }))
  on('fs.write', () => ({ value: undefined }))
  on('fs.list', () => ({ value: [] }) as never)
  on('fs.read', (_, e) => {
    if (e.path.includes('web')) return { value: '' }
    throw new Error('no such file')
  })
  on('http.fetch', () => ({ value: { ok: false, status: 0, headers: {}, text: '' } }))
  on('process.run', (_, e) => {
    ran.push([...e.argv])
    const page = e.argv[0] === 'open' || e.argv.includes('start')
    const ok = e.argv[0] === 'uname' || (page && opens)
    return { value: { exitCode: ok ? 0 : 1, stdout: e.argv[0] === 'uname' ? `${system}\n` : '', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  return ran
}

const run = async ($: Engine) =>
  ((await $.command.run({ command: 'ai-worker:voice', args: '', origin: { kind: 'composer' }, presentation: { isFullscreen: false, columns: 80 } })) as { text: string }).text

test('/ai-worker:voice on a Mac opens the Keyboard settings and shows the steps', async ($, on) => {
  const ran = computer(on, 'Darwin')
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  const before = ran.length
  const text = await run($)
  expect(text).toContain('The Keyboard page of System Settings is now open.')
  expect(text).toContain('press the microphone key')
  // it opens one page and changes no setting: nothing else runs but the question of which system this is
  expect(ran.slice(before).filter(argv => argv[0] !== 'uname')).toEqual([MAC_PAGE])
})

test('/ai-worker:voice on Windows opens the language settings and shows Windows + H', async ($, on) => {
  const ran = computer(on, 'Windows')
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  const before = ran.length
  const text = await run($)
  expect(text).toContain('The "Language & region" page of Settings is now open.')
  expect(text).toContain('Windows key + H')
  expect(ran.slice(before)).toEqual([WINDOWS_PAGE])
})

test('/ai-worker:voice still helps when the settings page does not open', async ($, on) => {
  const ran = computer(on, 'Darwin', false)
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  expect(await run($)).toContain('Open the Apple menu, then System Settings, then Keyboard.')
  expect(ran.some(argv => argv[0] === 'open')).toBe(true)
})

test('/ai-worker:voice on Linux says there is nothing to open', async ($, on) => {
  const ran = computer(on, 'Linux')
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  const before = ran.length
  expect(await run($)).toContain('On Linux the plugin knows no built-in dictation to open.')
  expect(ran.slice(before).filter(argv => argv[0] !== 'uname')).toEqual([])
})
