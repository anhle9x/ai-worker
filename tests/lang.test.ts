import { expect, test } from 'claude-code/testing'
import { contextAdvice, formatUsd, shortCount } from '../hooks/edits'
import { getLang, pageLanguageScript, pickLang, setLang, tx } from '../hooks/lang'
import { formatSecs } from '../hooks/office'

test('the language is picked from AI_WORKER_LANG, then the saved choice, then the system locale', () => {
  expect(pickLang(undefined, {})).toBe('en')
  expect(pickLang('vi', {})).toBe('vi')
  expect(pickLang('vi', { AI_WORKER_LANG: 'en' })).toBe('en')
  expect(pickLang('en', { AI_WORKER_LANG: 'vi' })).toBe('vi')
  expect(pickLang(undefined, { LANG: 'vi_VN.UTF-8' })).toBe('vi')
  expect(pickLang(undefined, { LC_ALL: 'en_US.UTF-8', LANG: 'vi_VN.UTF-8' })).toBe('en')
  expect(pickLang('fr', { LANG: 'en_US.UTF-8' })).toBe('en')
  expect(pickLang(42, {})).toBe('en')
})

test('English is the default and fills in the parameters', () => {
  setLang('en')
  expect(getLang()).toBe('en')
  expect(tx('{n} min', { n: 3 })).toBe('3 min')
  expect(tx('a text nobody translated {x}', { x: 1 })).toBe('a text nobody translated 1')
  expect(tx('{n} min', {})).toBe('{n} min')
})

test('Vietnamese mode returns the Vietnamese text, and falls back to English for a text not in the dictionary', () => {
  try {
    setLang('vi')
    expect(getLang()).toBe('vi')
    expect(tx('{n} min', { n: 3 })).toBe('3 phút') // i18n-allow
    expect(tx('a text nobody translated {x}', { x: 1 })).toBe('a text nobody translated 1')
    expect(tx('Today')).toBe('Hôm nay') // i18n-allow
  } finally {
    setLang('en')
  }
  expect(tx('Today')).toBe('Today')
})

test('numbers, money and times follow the language in use', () => {
  try {
    setLang('vi')
    expect([shortCount(45678), formatUsd(0.4213), formatSecs(75), contextAdvice(85)]).toEqual(['45,7 k', '$0,42', '1 phút 15 giây', 'nên mở phiên mới']) // i18n-allow
    setLang('en')
    expect([shortCount(45678), formatUsd(0.4213), formatSecs(75), contextAdvice(85)]).toEqual(['45.7k', '$0.42', '1 min 15 sec', 'start a new session'])
  } finally {
    setLang('en')
  }
})

test('the page gets only a language chosen on purpose', () => {
  expect(pageLanguageScript('vi')).toBe('window.__aiWorkerLang = "vi";\n')
  expect(pageLanguageScript('en')).toBe('window.__aiWorkerLang = "en";\n')
  expect(pageLanguageScript(undefined)).toBe('window.__aiWorkerLang = "";\n')
  expect(pageLanguageScript('"><script>')).toBe('window.__aiWorkerLang = "";\n')
})
