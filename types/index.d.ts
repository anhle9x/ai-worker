export type WorkerId = 'claude' | 'gemini' | 'chatgpt' | 'gemma'

/** One task handed to a worker. Only a fixed kind label is kept, never the prompt. */
export type Job = {
  key: string
  worker: WorkerId
  kind: string
  startedAt: number
  /** The server's job_id while a slow task is still running. */
  jobId?: string
  /** For the audit record: the tool, who served it, the prompt's length and salted fingerprint. Never the prompt. */
  brief?: { tool: DelegationTool; via: Delegation['via']; promptChars: number; promptHash: string }
  endedAt?: number
  ok?: boolean
}

/** Token counts as Claude Code reports them at the end of each turn. */
export type Usage = {
  input: number
  output: number
  cacheRead: number
  cacheWrite: number
  turns: number
}

/** A file Claude changed, with the changed lines (unified-diff style, capped). */
export type FileEdit = {
  key: string
  path: string
  tool: string
  at: number
  added: number
  removed: number
  lines: string[]
  /** True when the file looks like it holds secrets: lines are not kept. */
  isHidden?: boolean
  isNew?: boolean
  isTruncated?: boolean
}

export type Verb = 'run' | 'read' | 'edit' | 'search' | 'web' | 'browser' | 'delegate' | 'ask' | 'other'

/** One line of the feed: what the person asked, what Claude said, or a tool call. */
export type Activity = {
  at: number
  kind: 'you' | 'say' | 'tool'
  text: string
  verb?: Verb
  /** Image or video files on this Mac the line shows, by absolute path. */
  media?: string[]
  /** Images pasted into the prompt: the engine gives a plugin no path for them. */
  pasted?: number
}

export type PlanItem = { content: string; status: 'pending' | 'in_progress' | 'completed' }

/** secret: text for ChatGPT or Gemini held a secret and was not sent; commit: a commit that adds a secret was put to the person;
 * risky: a command that destroys work or weakens the computer was put to the person; page: a page Claude read tried to steer it;
 * answer: an answer from ChatGPT, Gemini or Gemma held a secret, text aimed at an AI or a command that cannot be undone. */
export type BlockKind = 'secret' | 'commit' | 'risky' | 'page' | 'answer'

export type DelegationTool = 'ask_chatgpt' | 'ask_gemini' | 'ask_local' | 'generate_image'
/** ok: an answer came back; error: the helper failed; refused: the text held a secret and was not sent; declined: the person or the permission settings said no. */
export type DelegationOutcome = 'ok' | 'error' | 'refused' | 'declined'
/** One piece of work handed to a helper, for the server's audit log. Lengths, kinds and a salted fingerprint only: never the prompt or the answer. */
export type Delegation = {
  id: string
  at: number
  worker: 'chatgpt' | 'gemini' | 'gemma'
  tool: DelegationTool
  /** plugin: the plugin's own tools ran it; ai-workers: a separate ai-workers MCP server did. */
  via: 'plugin' | 'ai-workers'
  promptChars: number
  answerChars: number
  promptHash: string
  outcome: DelegationOutcome
  /** What the check of the answer found: a secret, text aimed at an AI, a command that cannot be undone. */
  check?: ('secret' | 'aimed' | 'command')[]
  /** The kinds of secret that stopped the text (for example "GitHub token"), never their value. */
  found?: string[]
}

export type TeamState = {
  /** A newer signed plugin is on the server; `tuDong` false when this machine cannot check signatures, so it only says so. */
  update?: { version: string; auto: boolean }
  /** Subagents running now: `ten` is the agent type, `moTa` the task. Only the type ever leaves this machine. */
  subagents?: { name: string; description: string }[]
  jobs: Job[]
  /** What ai-worker stopped or put to the person, newest last: only the kind and the time ever leave this machine. */
  blocks?: { at: number; kind: BlockKind }[]
  /** Work handed to ChatGPT, Gemini or Gemma, newest last: sent to the server's audit log, without any of the text. */
  delegations?: Delegation[]
  /** Milliseconds since the epoch at the last tick; drives elapsed times. */
  now: number
  claudeBusySince?: number
  claudeTool?: string
  /** Claude is waiting on the person: a question asked mid-turn or at its end. */
  asking?: boolean
  usage?: Usage
  lastTurn?: Usage
  edits?: FileEdit[]
  activity?: Activity[]
  plan?: PlanItem[]
  /** The session's cost so far in US dollars, as the status line has it (API prices). */
  costUsd?: number
  /** How full the context window is, as the status line has it; absent before the first response. */
  context?: ContextFill
  /** The context level (0, 60 or 80) last warned about, so each warning shows once per climb. */
  contextWarned?: number
  /** The context level (0 or 80) Claude was last told about beside a message, so it is told once per climb. */
  contextToldClaude?: number
  /** The rate-limit warning last toasted (`hanMucCanhBao().key`): toast each level of each window once. */
  quotaWarned?: string
  /** The rate-limit band the person hid; it comes back when the key changes. */
  quotaHidden?: string
  /** The Claude model this session runs on (e.g. claude-opus-5-5), for the team board. */
  model?: string
  /** The account's rate-limit windows as this session last read them, for the team board. */
  quota?: Quota
}

/** An account's rate-limit windows (five_hour, seven_day, ...) read at `luc`: percent used, and when each resets (ms). */
export type Quota = { readAt: number; windows: { kind: string; pct: number; resetsAt?: number }[] }

export type ContextFill = { percent: number; tokens: number; window: number }

/** Tokens and dollars spent in one hour, all sessions on this machine together. */
export type Spend = { usd: number; input: number; output: number; cacheRead: number; cacheWrite: number }

/** Spend by hour, keyed by hours since the epoch (UTC), so the page sums by its own local day. */
export type Ledger = Record<string, Spend>

declare module 'claude-code' {
  interface PluginState {
    'ai-worker': { team: TeamState }
  }
}
