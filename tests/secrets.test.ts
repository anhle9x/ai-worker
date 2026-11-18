import { expect, test } from 'claude-code/testing'
import { findSecrets, secretRefusal } from '../hooks/secrets'

// Values with the shape of real credentials, put together here so the file itself holds none that a scanner would flag
// Giá trị có hình dạng thông tin đăng nhập thật, ghép ở đây để chính file này không chứa giá trị nào bị máy quét bắt
const AWS = 'AKIA' + 'Q7RZ4PLMN2XW8VTB'
const GITHUB = 'gh' + 'p_' + 'a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8'
const OPENAI = 'sk-' + 'proj-' + 'Zx9Yw8Vu7Ts6Rq5Po4Nm3Lk2Ji1Hg0FeDcBa'
const ANTHROPIC = 'sk-' + 'ant-' + 'api03-Zx9Yw8Vu7Ts6Rq5Po4Nm3Lk2'
const GOOGLE = 'AIza' + 'SyD3f4G5h6J7k8L9m0N1p2Q3r4S5t6U7v8w'
const TELEGRAM = '1234567890:' + 'AA' + 'Hk3jL9mN2pQ5rS8tU1vW4xY7zA0bC3dE6fG'
const JWT = 'eyJ' + 'hbGciOiJIUzI1NiJ9.' + 'eyJ' + 'zdWIiOiIxMjM0NTY3ODkwIn0.' + 'dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U'

test('each kind of secret is found, with its line and a hint that is not the value', () => {
  const text = [
    'please review this config',
    `aws_access_key_id = ${AWS}`,
    `token: ${GITHUB}`,
    `client = OpenAI(api_key="${OPENAI}")`,
    `ANTHROPIC = "${ANTHROPIC}"`,
    `maps = "${GOOGLE}"`,
    `bot = "${TELEGRAM}"`,
    `Authorization: Bearer ${JWT}`,
    'DATABASE_URL=postgres://app:s3cretPass@db.internal:5432/app',
    'INGEST_KEY=Q2hhbmdlTWVSZWFsbHk5',
    '-----BEGIN OPENSSH ' + 'PRIVATE KEY-----',
  ].join('\n')
  const found = findSecrets(text)
  expect(found.map(s => [s.kind, s.line])).toEqual([
    ['AWS access key', 2],
    ['GitHub token', 3],
    ['OpenAI API key', 4],
    ['Anthropic API key', 5],
    ['Google API key', 6],
    ['Telegram bot token', 7],
    ['JSON web token', 8],
    ['password in a connection string', 9],
    ['password or key in a .env line', 10],
    ['private key', 11],
  ])
  for (const s of found) {
    expect(s.hint.length).toBeLessThan(40)
    for (const value of [AWS, GITHUB, OPENAI, ANTHROPIC, GOOGLE, TELEGRAM, JWT, 's3cretPass', 'Q2hhbmdlTWVSZWFsbHk5']) expect(s.hint).not.toContain(value)
  }
  expect(found.find(s => s.line === 10)!.hint).toBe('INGEST_KEY=…')
})

test('ordinary code, placeholders and the providers own examples pass', () => {
  for (const text of [
    'def login(): password = request.form["password"]',
    'API_KEY=<your key here>',
    'export TOKEN=${TOKEN}',
    'SECRET_KEY=changeme',
    'GITHUB_TOKEN=xxxxxxxxxxxxxxxx',
    // the example AWS publishes in its documentation, put together so this file holds no key-shaped string
    // ví dụ AWS công bố trong tài liệu, ghép lại để file này không chứa chuỗi có hình dạng khoá
    'aws_access_key_id = ' + 'AKIA' + 'IOSFODNN7' + 'EXAMPLE',
    'Use sk-... for the key, and postgres://user@host/db without a password',
    'The token is in the environment variable OPENAI_API_KEY.',
    'eyJ is how a JWT starts',
    '',
  ]) {
    expect([text, findSecrets(text)]).toEqual([text, []])
  }
})

test('the refusal names the helper, the kinds and the lines, never a value', () => {
  const found = findSecrets(`line one\nkey ${AWS}\nDB_PASSWORD=hunter2hunter2`)
  const said = secretRefusal(found, 'ChatGPT')
  expect(said).toContain('Not sent to ChatGPT')
  expect(said).toContain('AWS access key on line 2')
  expect(said).toContain('password or key in a .env line on line 3')
  expect(said).toContain('Nothing left this computer.')
  expect(said).not.toContain(AWS)
  expect(said).not.toContain('hunter2hunter2')
})
