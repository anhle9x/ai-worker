// Updating the plugin from the company server: the signed manifest is what is trusted, never the server.
// Cập nhật plugin từ máy chủ công ty: manifest có chữ ký là thứ được tin, không bao giờ là máy chủ.

export type Manifest = { version: string; name: string; sha256: string; date: number }

/** A manifest in exactly the shape the release script writes; anything else is no manifest. */
/** Một manifest đúng dạng mà script phát hành ghi; bất cứ thứ gì khác đều không phải manifest. */
export function parseManifest(text: string): Manifest | undefined {
  try {
    const m = JSON.parse(text) as Record<string, unknown>
    const { version, name, sha256, date } = m
    if (typeof version !== 'string' || !/^[0-9A-Za-z.-]{1,20}$/.test(version)) return undefined
    if (typeof name !== 'string' || name !== `ai-worker-${version}.zip`) return undefined
    if (typeof sha256 !== 'string' || !/^[0-9a-f]{64}$/.test(sha256)) return undefined
    if (typeof date !== 'number' || !Number.isInteger(date) || date <= 0) return undefined
    return { version, name, sha256, date }
  } catch {
    return undefined
  }
}

/** Offer it if it differs (an older version is how IT rolls back) and is no older than the last one accepted, so an old signed file cannot be replayed. */
/** Đưa ra nếu nó khác (bản cũ hơn là cách người quản trị quay lui) và không cũ hơn bản đã nhận lần trước, để file cũ có chữ ký không bị phát lại. */
export function shouldOfferUpdate(m: Manifest, current: string | undefined, lastAcceptedDate: number): boolean {
  return m.version !== current && m.date >= lastAcceptedDate
}

export type SignatureResult = 'valid' | 'invalid' | 'unsupported'

/** What ssh-keygen -Y verify said. An OpenSSH too old for -Y refuses the option: not the same as a bad signature. */
/** Kết quả của ssh-keygen -Y verify. OpenSSH quá cũ không hỗ trợ -Y sẽ từ chối tuỳ chọn đó: không giống một chữ ký sai. */
export function parseSignatureResult(r: { exitCode: number; stdout: string; stderr?: string }): SignatureResult {
  if (r.exitCode === 0) return 'valid'
  return /unknown option|illegal option|usage:/i.test(`${r.stdout}\n${r.stderr ?? ''}`) ? 'unsupported' : 'invalid'
}

/** Whether an allowed_signers file holds a key; a file of comments alone verifies nothing. */
/** Một file allowed_signers có chứa khoá hay không; file chỉ toàn dòng chú thích thì không xác minh được gì. */
export function hasSigningKeys(text: string): boolean {
  return text.split(/\r?\n/).some(line => line.trim() && !line.trim().startsWith('#'))
}

/** The hash in shasum, sha256sum or certutil output; certutil may space its bytes. */
/** Mã băm trong kết quả của shasum, sha256sum hoặc certutil; certutil có thể chèn dấu cách giữa các byte. */
export function parseHash(out: string): string | undefined {
  for (const line of out.split(/\r?\n/)) {
    const m = /^([0-9a-fA-F]{2} ?){32}/.exec(line.trim())
    if (m) return m[0].replace(/ /g, '').toLowerCase()
  }
  return undefined
}
