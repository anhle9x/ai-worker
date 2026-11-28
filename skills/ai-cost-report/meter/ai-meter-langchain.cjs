// Measures an app built with LangChain.js or LangGraph.js: callbacks that count every LLM call of a user turn into ai-meter.
// Đo một app dựng bằng LangChain.js hay LangGraph.js: các callback đếm mọi lần gọi LLM của một lượt người dùng vào ai-meter.
// Copy this file next to ai-meter.cjs. Node 18+, no package of its own: it only uses the @langchain/core the app already has.
// Chép file này cạnh ai-meter.cjs. Node 18+, không cần gói riêng nào: nó chỉ dùng @langchain/core mà app đã có sẵn.
// It never reads a prompt, an answer or an error message: token counts, the model's name and times only.
// Không bao giờ đọc câu hỏi, câu trả lời hay thông báo lỗi: chỉ số token, tên model và thời gian.
//
//   const { Meter } = require('./ai-meter.cjs')
//   const { meterCallback } = require('./ai-meter-langchain.cjs')
//   const meter = new Meter({ file: 'ai-meter.jsonl', env: 'prod' })
//   const answer = await meter.turn((t) => chain.invoke(question, { callbacks: [meterCallback(t)] }))   // a chain, an agent or a graph
'use strict'
const { readUsage } = require('./ai-meter.cjs')

// LangChain's name for a provider (ls_provider), where it differs from the name the price file uses
// Tên LangChain đặt cho một hãng (ls_provider), ở chỗ nó khác tên mà bảng giá dùng
const PROVIDERS = {
  google_genai: 'google', google_vertexai: 'google', 'google-genai': 'google', vertexai: 'google',
  amazon_bedrock: 'bedrock', bedrock_converse: 'bedrock', aws: 'bedrock',
  mistralai: 'mistral', azure: 'openai', azure_openai: 'openai', together: 'togetherai',
}

const int = (v) => (Number.isInteger(v) && v >= 0 ? v : null)
const dict = (v) => (v && typeof v === 'object' && !Array.isArray(v) ? v : {})
const text = (v) => (typeof v === 'string' && v ? v : undefined)
const providerOf = (name) => { const p = String(name || '').trim().toLowerCase(); return PROVIDERS[p] || p || undefined }
const guess = (model) => { try { return readUsage({ model }).provider } catch { return 'other' } }

// The meter's counts from LangChain's usage_metadata, each input token counted once; null when it cannot be told.
// Số đếm của bộ đo từ usage_metadata của LangChain, mỗi token đầu vào chỉ đếm một lần; null khi không xác định được.
// input_tokens is the sum of every kind of input, cache reads and writes included; input_token_details splits them.
// input_tokens là tổng mọi loại đầu vào, gồm cả đọc và ghi cache; input_token_details tách chúng ra.
function usageCounts(usage) {
  if (!usage || typeof usage !== 'object') return null
  const det = dict(usage.input_token_details)
  const total = int(usage.input_tokens), out = int(usage.output_tokens)
  const read = int(det.cache_read ?? 0)
  let write = int(det.cache_creation ?? 0)
  // Anthropic through LangChain may split the cache writes by how long they are kept
  // Anthropic qua LangChain có thể tách phần ghi cache theo thời gian giữ
  const short = int(det.ephemeral_5m_input_tokens ?? 0), long = int(det.ephemeral_1h_input_tokens ?? 0)
  if ([total, out, read, write, short, long].includes(null)) return null
  if (write === 0) write = short + long
  if (long > write || read + write > total) return null
  return { input: total - read - write, output: out, cacheRead: read, cacheWrite: write, cacheWriteLong: long }
}

// Pass one of these, made for the turn, in { callbacks: [...] }: every model call under it is counted.
// Truyền một cái này, tạo cho lượt đó, vào { callbacks: [...] }: mọi lần gọi model bên dưới đều được đếm.
function meterCallback(turn) {
  // what each running call said about itself when it started: [provider, model]
  // điều mỗi lần gọi đang chạy tự khai khi bắt đầu: [hãng, model]
  const runs = new Map()
  const start = (runId, extraParams, metadata) => {
    try {
      const meta = dict(metadata), params = dict(dict(extraParams).invocation_params)
      runs.set(runId, [providerOf(meta.ls_provider), text(meta.ls_model_name) || text(params.model) || text(params.model_name) || text(params.modelName)])
    } catch {}
  }
  const taken = (runId) => { const r = runs.get(runId) || []; runs.delete(runId); return r }
  return {
    name: 'ai-meter',
    handleChatModelStart(llm, messages, runId, parentRunId, extraParams, tags, metadata) { start(runId, extraParams, metadata) },
    handleLLMStart(llm, prompts, runId, parentRunId, extraParams, tags, metadata) { start(runId, extraParams, metadata) },
    handleLLMNewToken() { try { turn.firstToken() } catch {} },
    handleLLMEnd(output, runId) {
      try {
        const [provider, model] = taken(runId)
        const llmOutput = dict(output && output.llmOutput)
        const rows = output && Array.isArray(output.generations) && output.generations.length ? output.generations : [[null]]
        for (const row of rows) {
          // one call per prompt of the batch; several candidates of one prompt share that call's usage
          // mỗi câu hỏi trong lô là một lần gọi; nhiều phương án của một câu hỏi dùng chung usage của lần gọi đó
          const message = row && row[0] && row[0].message
          const info = dict(message && message.response_metadata)
          let name = text(info.model_name) || text(info.model) || text(llmOutput.model_name) || text(llmOutput.model) || model
          // pieces of a streamed answer that each carried the name are joined into the name written several times over
          // các mẩu của câu trả lời streaming, mẩu nào cũng mang tên, bị nối lại thành cái tên viết lặp nhiều lần
          if (model && name && name !== model && name.split(model).join('') === '') name = model
          const who = provider || providerOf(info.model_provider)
          const counts = usageCounts(message && message.usage_metadata)
          if (counts) turn.count(who || guess(name), name, counts)
          else {
            // an older integration or a plain LLM: the provider's own usage, as the meter already reads it
            // tích hợp cũ hoặc LLM thường: usage của chính hãng, đúng dạng bộ đo vốn đã đọc
            const raw = info.usage || info.tokenUsage || info.token_usage || llmOutput.tokenUsage || llmOutput.token_usage || llmOutput.usage
            // LangChain.js writes its older usage in its own spelling: promptTokens and completionTokens, cache included in the first
            // LangChain.js ghi usage kiểu cũ theo cách viết riêng: promptTokens và completionTokens, cái đầu đã gồm cache
            if (raw && typeof raw === 'object' && int(raw.promptTokens) !== null && int(raw.completionTokens) !== null) {
              turn.count(who || guess(name), name, { input: raw.promptTokens, output: raw.completionTokens })
            } else turn.record(raw && typeof raw === 'object' ? raw : {}, { provider: who || guess(name), model: name })
          }
        }
      } catch {}
    },
    // only that it failed: the error's text is never read
    // chỉ ghi là nó lỗi: chữ của lỗi không bao giờ được đọc
    handleLLMError(err, runId) {
      try {
        const [provider, model] = taken(runId)
        turn.fail(provider || guess(model), model)
      } catch {}
    },
  }
}

module.exports = { meterCallback, usageCounts }
