// The TypeScript types of ai-meter-langchain.cjs; copy both, side by side, under these names, next to ai-meter.cjs and ai-meter.d.cts.
// Kiểu TypeScript của ai-meter-langchain.cjs; chép cả hai, cạnh nhau, đúng các tên này, cạnh ai-meter.cjs và ai-meter.d.cts.
import type { Turn } from './ai-meter.cjs'

/** The counts `turn.count()` takes, read from LangChain's `usage_metadata`; null when they cannot be told. */
/** Số đếm mà `turn.count()` nhận, đọc từ `usage_metadata` của LangChain; null khi không xác định được. */
export function usageCounts(usage: unknown): { input: number; output: number; cacheRead: number; cacheWrite: number; cacheWriteLong: number } | null

/** Callbacks for `{ callbacks: [meterCallback(t)] }`: every model call under them is counted in the turn. */
/** Các callback cho `{ callbacks: [meterCallback(t)] }`: mọi lần gọi model bên dưới đều được đếm vào lượt đó. */
export function meterCallback(turn: Turn): {
  name: string
  handleChatModelStart(...args: unknown[]): void
  handleLLMStart(...args: unknown[]): void
  handleLLMNewToken(...args: unknown[]): void
  handleLLMEnd(...args: unknown[]): void
  handleLLMError(...args: unknown[]): void
}
