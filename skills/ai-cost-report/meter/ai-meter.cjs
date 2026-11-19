// Measures the cost and speed of an AI project or application that calls an LLM, one JSON line per user turn.
// Đo chi phí và tốc độ của một dự án hay ứng dụng AI có gọi LLM, mỗi lượt người dùng một dòng JSON.
// Copy this one file into the project. Node 18+, no package needed; works from require() and from import.
// Chép đúng file này vào dự án. Node 18+, không cần gói nào; dùng được với require() và import.
// It never writes a prompt, an answer, a user id or an error message. The line format is in FORMAT.md next to this folder.
// Không bao giờ ghi câu hỏi, câu trả lời, mã người dùng hay thông báo lỗi. Định dạng dòng nằm trong FORMAT.md cạnh thư mục này.
//
//   const { Meter } = require('./ai-meter.cjs')
//   const meter = new Meter({ file: 'ai-meter.jsonl', env: 'prod' })
//   const answer = await meter.turn(async (t) => { const r = await client.messages.create(...); t.record(r); return r })
//   t.count('myprovider', 'my-model', { input: 812, output: 95 })   // any other provider, counts by hand
'use strict'
const fs = require('fs')
const crypto = require('crypto')

const VERSION = 1
// A provider is a short name: lowercase letters, digits, "_", "." and "-", at most 32; anything else is written as "other"
// Hãng là một tên ngắn: chữ thường, số, "_", "." và "-", tối đa 32 ký tự; tên khác ghi thành "other"
const PROVIDER_RE = /^[a-z0-9][a-z0-9_.-]{0,31}$/
const MODEL_RE = /^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,78}$/
const COUNTS = ['input', 'output', 'cacheRead', 'cacheWrite', 'cacheWriteLong']

// A token count is a whole number of zero or more; anything else is "not measured"
// Số token là số nguyên từ 0 trở lên; thứ khác là "không đo được"
function int(v) {
  return Number.isSafeInteger(v) && v >= 0 ? v : null
}

function pick(d, ...keys) {
  if (!d || typeof d !== 'object') return undefined
  for (const k of keys) if (d[k] !== undefined && d[k] !== null) return d[k]
  return undefined
}

function counts(inp, out, read = 0, write = 0, long = 0) {
  const v = [inp, out, read, write, long].map(int)
  if (v.includes(null) || v[4] > v[3]) return null
  return { input: v[0], output: v[1], cacheRead: v[2], cacheWrite: v[3], cacheWriteLong: v[4] }
}

// Only used when neither the caller nor the usage shape names the provider
// Chỉ dùng khi cả người gọi lẫn hình dạng usage đều không cho biết hãng
function guessProvider(model) {
  const m = String(model || '').toLowerCase().split('/').pop()
  if (m.includes('claude')) return 'anthropic'
  if (/^(gpt-|o1|o3|o4|chatgpt)/.test(m)) return 'openai'
  if (/^(gemini|gemma)/.test(m)) return 'google'
  for (const [prefix, name] of [['deepseek', 'deepseek'], ['mistral', 'mistral'], ['mixtral', 'mistral'], ['codestral', 'mistral'], ['grok', 'xai'], ['command', 'cohere']]) {
    if (m.startsWith(prefix)) return name
  }
  return 'other'
}

// Reads { provider, model, counts } from an API response or its usage; counts is null when there is no usage.
// Đọc { provider, model, counts } từ phản hồi API hay phần usage của nó; counts là null khi không có usage.
// Same shapes as ai_meter.py: Anthropic, OpenAI and every API that copies it, Gemini, Bedrock Converse, Ollama /api/chat, Cohere v2.
// Cùng các dạng như ai_meter.py: Anthropic, OpenAI và mọi API chép theo nó, Gemini, Bedrock Converse, Ollama /api/chat, Cohere v2.
function readUsage(resp, provider) {
  if (!resp || typeof resp !== 'object') return { provider, model: undefined, counts: null }
  const model = pick(resp, 'model', 'modelVersion', 'model_version', 'modelId')
  // Gemini: promptTokenCount includes the cache; thinking tokens are billed as output
  // Gemini: promptTokenCount đã gồm cache; token suy nghĩ tính tiền như output
  let gem = pick(resp, 'usageMetadata', 'usage_metadata')
  if (gem === undefined && pick(resp, 'promptTokenCount', 'prompt_token_count') !== undefined) gem = resp
  if (gem && typeof gem === 'object') {
    const prompt = int(pick(gem, 'promptTokenCount', 'prompt_token_count'))
    const cached = int(pick(gem, 'cachedContentTokenCount', 'cached_content_token_count') ?? 0)
    const cand = int(pick(gem, 'candidatesTokenCount', 'candidates_token_count') ?? 0)
    const think = int(pick(gem, 'thoughtsTokenCount', 'thoughts_token_count') ?? 0)
    const p = provider || 'google'
    if ([prompt, cached, cand, think].includes(null) || cached > prompt) return { provider: p, model, counts: null }
    return { provider: p, model, counts: counts(prompt - cached, cand + think, cached) }
  }
  // Ollama /api/chat: prompt_eval_count and eval_count on the answer itself
  // /api/chat của Ollama: prompt_eval_count và eval_count nằm ngay trên câu trả lời
  if ('eval_count' in resp || 'prompt_eval_count' in resp) {
    return { provider: provider || 'ollama', model, counts: counts(resp.prompt_eval_count, resp.eval_count) }
  }
  const u = resp.usage && typeof resp.usage === 'object' ? resp.usage : resp
  // Vercel AI SDK: inputTokens include the cache; inputTokenDetails splits them
  // Vercel AI SDK: inputTokens đã gồm cache; inputTokenDetails tách ra
  if (u.inputTokenDetails && typeof u.inputTokenDetails === 'object') {
    const det = u.inputTokenDetails
    const read = det.cacheReadTokens ?? 0, write = det.cacheWriteTokens ?? 0
    let plain = det.noCacheTokens
    if (plain == null && int(u.inputTokens) !== null && int(read) !== null && int(write) !== null) plain = u.inputTokens - read - write
    return { provider: provider || guessProvider(model), model, counts: counts(plain, u.outputTokens, read, write) }
  }
  // Bedrock Converse: inputTokens are only the tokens not read from or written to the cache
  // Bedrock Converse: inputTokens chỉ là phần không đọc từ cache và không ghi vào cache
  if ('inputTokens' in u || 'outputTokens' in u) {
    return { provider: provider || 'bedrock', model, counts: counts(u.inputTokens, u.outputTokens, u.cacheReadInputTokens ?? 0, u.cacheWriteInputTokens ?? 0) }
  }
  // Cohere v2: the billed units are what costs money
  // Cohere v2: billed_units là phần bị tính tiền
  if (u.billed_units && typeof u.billed_units === 'object') {
    return { provider: provider || 'cohere', model, counts: counts(u.billed_units.input_tokens, u.billed_units.output_tokens) }
  }
  // Anthropic: input_tokens excludes the cache
  // Anthropic: input_tokens không gồm cache
  if ('cache_read_input_tokens' in u || 'cache_creation_input_tokens' in u || provider === 'anthropic') {
    const long = pick(u.cache_creation, 'ephemeral_1h_input_tokens') ?? 0
    return { provider: provider || 'anthropic', model, counts: counts(u.input_tokens, u.output_tokens, u.cache_read_input_tokens ?? 0, u.cache_creation_input_tokens ?? 0, long) }
  }
  // OpenAI and every API that copies it: input or prompt tokens include cache reads and writes
  // OpenAI và mọi API chép theo nó: input hay prompt tokens đã gồm cache đọc và ghi
  const total = int(pick(u, 'input_tokens', 'prompt_tokens'))
  const out = int(pick(u, 'output_tokens', 'completion_tokens'))
  const p = provider || guessProvider(model)
  if (total === null && out === null) return { provider: p, model, counts: null }
  const det = pick(u, 'input_tokens_details', 'prompt_tokens_details') || {}
  const read = int(pick(det, 'cached_tokens', 'prompt_cache_hit_tokens') ?? pick(u, 'prompt_cache_hit_tokens') ?? 0)
  const write = int(pick(det, 'cache_write_tokens') ?? 0)
  const long = int(pick(pick(det, 'cache_write_tokens_details'), 'ttl_12h_tokens') ?? 0)
  if ([total, out, read, write, long].includes(null) || read + write > total) return { provider: p, model, counts: null }
  // Some of these APIs (xAI's Chat Completions) leave reasoning tokens out of completion_tokens; total_tokens shows it
  // Vài API loại này (Chat Completions của xAI) không tính token suy nghĩ vào completion_tokens; total_tokens cho thấy điều đó
  const think = int(pick(pick(u, 'completion_tokens_details', 'output_tokens_details'), 'reasoning_tokens') ?? 0)
  const output = think && int(u.total_tokens) === total + out + think ? out + think : out
  return { provider: p, model, counts: counts(total - read - write, output, read, write, long) }
}

function cleanProvider(p) {
  const s = String(p || 'other').trim().toLowerCase()
  return PROVIDER_RE.test(s) ? s : 'other'
}

function cleanModel(m) {
  const s = String(m || '')
  return MODEL_RE.test(s) ? s : 'unknown'
}

// One user turn: every LLM call made to answer it. Get one from meter.start() or meter.turn(fn).
// Một lượt người dùng: mọi lần gọi LLM để trả lời lượt đó. Lấy từ meter.start() hay meter.turn(fn).
class Turn {
  constructor(meter) {
    this._meter = meter
    this._at = new Date()
    this._t0 = performance.now()
    this._ttft = null
    this._models = new Map()
    this._done = false
    this.outcome = 'ok'
  }

  _slot(provider, model) {
    const key = cleanProvider(provider) + '\n' + cleanModel(model)
    if (!this._models.has(key)) {
      this._models.set(key, { calls: 0, errors: 0, retries: 0, unmeasured: 0, input: 0, output: 0, cacheRead: 0, cacheWrite: 0, cacheWriteLong: 0 })
    }
    return this._models.get(key)
  }

  _add(provider, model, c, retry) {
    const s = this._slot(provider, model)
    s.calls += 1
    if (retry) s.retries += 1
    if (c === null) s.unmeasured += 1
    else for (const k of COUNTS) s[k] += c[k]
  }

  // Counts one LLM call from its response (or its usage). opts.provider/opts.model override what the response says.
  // Đếm một lần gọi LLM từ phản hồi (hay usage) của nó. opts.provider/opts.model thay cho điều phản hồi ghi.
  record(resp, opts = {}) {
    try {
      const r = readUsage(resp, opts.provider)
      this._add(r.provider, opts.model || r.model, r.counts, opts.retry)
    } catch {}
  }

  // Counts one LLM call from numbers you read yourself, for a provider whose answer this file does not know.
  // Đếm một lần gọi LLM từ số bạn tự đọc, cho hãng mà file này chưa biết dạng câu trả lời.
  // n.input is the input tokens billed at the normal price (without cache reads and writes); leaving it out means not measured.
  // n.input là token đầu vào tính giá thường (không gồm đọc và ghi cache); bỏ trống nghĩa là không đo được.
  count(provider, model, n = {}) {
    try {
      const c = n.input == null || n.output == null ? null : counts(n.input, n.output, n.cacheRead ?? 0, n.cacheWrite ?? 0, n.cacheWriteLong ?? 0)
      this._add(provider, model, c, n.retry)
    } catch {}
  }

  // Counts one LLM call that failed (no answer, so no usage). Pass no error text.
  // Đếm một lần gọi LLM bị lỗi (không có trả lời nên không có usage). Không truyền chữ của lỗi.
  fail(provider, model, opts = {}) {
    try {
      const s = this._slot(provider, model)
      s.calls += 1
      s.errors += 1
      if (opts.retry) s.retries += 1
    } catch {}
  }

  // Marks the first streamed piece of the answer; only the first mark counts.
  // Đánh dấu mẩu đầu tiên của câu trả lời khi streaming; chỉ lần đầu được tính.
  firstToken() {
    if (this._ttft === null) this._ttft = performance.now()
  }

  // Writes the line; meter.turn(fn) calls it for you.
  // Ghi dòng; meter.turn(fn) tự gọi.
  end(outcome) {
    if (this._done) return
    this._done = true
    try {
      const o = outcome || this.outcome
      const line = {
        v: VERSION,
        turnId: crypto.randomBytes(8).toString('hex'),
        at: this._at.toISOString(),
        durationMs: Math.floor(performance.now() - this._t0),
        outcome: ['ok', 'error', 'timeout'].includes(o) ? o : 'error',
        env: this._meter.env,
        models: [],
      }
      if (this._ttft !== null) line.ttftMs = Math.floor(this._ttft - this._t0)
      for (const [key, s] of this._models) {
        const [provider, model] = key.split('\n')
        const row = { provider, model, ...s }
        // every answered call lacked usage: the tokens are unknown, not zero
        // mọi lần gọi có trả lời đều thiếu usage: token là chưa biết, không phải 0
        if (s.unmeasured && s.calls - s.errors === s.unmeasured) for (const k of COUNTS) row[k] = null
        line.models.push(row)
      }
      this._meter._write(line)
    } catch {}
  }
}

// Where the lines go. env is "prod" or "test". AI_METER_FILE and AI_METER_ENV override; AI_METER_OFF=1 turns it off.
// Nơi ghi các dòng. env là "prod" hay "test". AI_METER_FILE và AI_METER_ENV ghi đè; AI_METER_OFF=1 thì tắt.
class Meter {
  constructor(opts = {}) {
    this.file = process.env.AI_METER_FILE || opts.file || 'ai-meter.jsonl'
    const e = process.env.AI_METER_ENV || opts.env || 'prod'
    this.env = e === 'test' ? 'test' : 'prod'
    this.off = process.env.AI_METER_OFF === '1'
    this.sync = !!opts.sync
  }

  start() {
    return new Turn(this)
  }

  // Runs fn(turn), writes the line when it ends, and returns or rethrows what fn did.
  // Chạy fn(turn), ghi dòng khi xong, và trả về hay ném lại đúng điều fn làm.
  async turn(fn) {
    const t = new Turn(this)
    try {
      return await fn(t)
    } catch (err) {
      const name = String((err && (err.name || (err.constructor && err.constructor.name))) || '')
      t.outcome = /timeout/i.test(name) ? 'timeout' : 'error'
      throw err
    } finally {
      t.end()
    }
  }

  _write(line) {
    if (this.off) return
    try {
      const data = JSON.stringify(line) + '\n'
      if (this.sync) fs.appendFileSync(this.file, data)
      else fs.appendFile(this.file, data, () => {})
    } catch {}
  }
}

module.exports = { Meter, Turn, readUsage, VERSION }
