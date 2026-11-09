// Pure drawing of the pixel office: team state in, SVG markup out.
// Ambient motion (typing, blinking, clouds, clock) is SMIL, so the frame only
// changes when someone's status does.
// Vẽ thuần túy văn phòng pixel: trạng thái nhóm vào, mã SVG ra.
// Chuyển động nền (gõ phím, chớp mắt, mây, đồng hồ) là SMIL, nên khung hình chỉ
// đổi khi trạng thái của ai đó đổi.
import type { Job, TeamState, WorkerId } from '../types'
import { getLang, tx } from './lang'

/** How long a finished task keeps its ✓ / ! badge. */
/** Huy hiệu ✓ / ! của một việc đã xong được giữ bao lâu. */
export const BADGE_MS = 8000
/** How long the paper hand-off animation stays in the drawing. */
/** Hoạt cảnh chuyển giấy được giữ bao lâu trong hình vẽ. */
export const FX_MS = 1600

export type Worker = {
  id: WorkerId
  name: string
  role: string
  shirt: string
  shirtDark: string
  hair: string
  skin: string
}

export const WORKERS: Worker[] = [
  { id: 'claude', name: 'Claude', get role() { return tx('Team lead') }, shirt: '#d97757', shirtDark: '#b45d40', hair: '#5a3825', skin: '#f1c7a5' },
  { id: 'gemini', name: 'Gemini', get role() { return tx('Research, drawing images') }, shirt: '#4f7df3', shirtDark: '#3a5fc4', hair: '#2b2b3a', skin: '#e9b48f' },
  { id: 'chatgpt', name: 'ChatGPT', get role() { return tx('Code review') }, shirt: '#10a37f', shirtDark: '#0b7a5f', hair: '#1f1f1f', skin: '#d39a75' },
  { id: 'gemma', name: 'Gemma', get role() { return tx('Data on this computer') }, shirt: '#8b5cf6', shirtDark: '#6b3fd4', hair: '#7a4a2a', skin: '#f3cfb3' },
]

/** The words the office shows that a team may change (see web/config.js). */
/** Các chữ mà văn phòng hiện và nhóm có thể đổi (xem web/config.js). */
const brandDefaults = () => ({ title: tx('AI Worker Office'), sign: 'AI WORKER', subtitle: tx('AI OFFICE'), water: 'H2O' })
export const BRAND = brandDefaults()
/** Members a team has switched off (no account for them): no desk, no status row. */
/** Các thành viên mà nhóm đã tắt (không có tài khoản): không có bàn, không có dòng trạng thái. */
export const ABSENT = new Set<WorkerId>()

export type OfficeConfig = {
  officeName?: string
  signText?: string
  subtitle?: string
  waterLabel?: string
  workers?: Partial<Record<WorkerId, boolean>>
  workerNames?: Partial<Record<WorkerId, string>>
}

/** Takes a team's own words: office name, sign, water brand, and what each member is called. */
/** Lấy chữ riêng của nhóm: tên văn phòng, biển hiệu, nhãn nước, và tên gọi từng thành viên. */
export function applyConfig(cfg: OfficeConfig | undefined) {
  if (!cfg) return
  const pick = (v: unknown, d: string) => (typeof v === 'string' && v.trim() ? v.trim() : d)
  const d = brandDefaults()
  BRAND.title = pick(cfg.officeName, d.title)
  BRAND.sign = pick(cfg.signText, d.sign)
  BRAND.subtitle = pick(cfg.subtitle, d.subtitle)
  BRAND.water = pick(cfg.waterLabel, d.water)
  for (const w of WORKERS) w.name = pick(cfg.workerNames?.[w.id], w.name)
  shown = cfg.workers ?? {}
  hideAbsent()
}

let shown: Partial<Record<WorkerId, boolean>> = {}
let installed: Partial<Record<WorkerId, boolean>> | null = null

/** A member is off when config.js says false, or when this machine has nothing behind its desk (true in config.js still shows it). */
/** Một thành viên bị tắt khi config.js ghi false, hoặc khi máy này không có gì sau bàn đó (true trong config.js vẫn hiện bàn). */
function hideAbsent() {
  ABSENT.clear()
  for (const id of ['gemini', 'chatgpt', 'gemma'] as WorkerId[]) {
    if (shown[id] === false || (shown[id] !== true && installed && installed[id] === false)) ABSENT.add(id)
  }
}

/** Which helpers this machine has; null when the ai-workers server delegates (every desk stays). */
/** Máy này có những trợ lý nào; null khi máy chủ ai-workers giao việc (mọi bàn đều ở lại). */
export function setInstalled(present: Partial<Record<WorkerId, boolean>> | null) {
  installed = present
  hideAbsent()
}

/**
 * Where everything stands. `wide` puts the three workers in a row for a broad
 * pane; `tall` stacks them two by two with bigger sprites for a narrow one.
 * Positions are office pixels; props are drawn at the origin and scaled.
 */
/** Mọi thứ nằm ở đâu. `wide` xếp ba trợ lý thành một hàng cho khung rộng; `tall` xếp chúng thành hai hàng hai cột với hình lớn hơn cho khung hẹp. Vị trí tính bằng điểm ảnh văn phòng; đồ vật được vẽ ở gốc rồi co giãn. */
type Layout = {
  w: number
  h: number
  scale: number
  wallH: number
  /** Head centre x and head top y of each person. */
  /** Tâm đầu theo x và đỉnh đầu theo y của từng người. */
  seat: Record<WorkerId, [number, number]>
  sign: [number, number]
  window: [number, number]
  /** Wall clock centre; the tall wall has no room for it beside the TV. */
  /** Tâm đồng hồ treo tường; tường của kiểu tall không đủ chỗ cho nó bên cạnh TV. */
  clock?: [number, number]
  /** Wall TV: left, top, width, height. */
  /** TV treo tường: trái, trên, rộng, cao. */
  tv: [number, number, number, number]
  rug: [number, number, number, number]
  plant: [number, number]
  cooler: [number, number]
  easel: [number, number]
}

const LAYOUTS: Record<'wide' | 'tall', Layout> = {
  wide: {
    w: 320, h: 200, scale: 1.5, wallH: 70,
    seat: { gemini: [72, 66], chatgpt: [160, 66], gemma: [248, 66], claude: [160, 142] },
    sign: [10, 10], window: [126, 8], clock: [288, 26], tv: [199, 4, 70, 46], rug: [104, 176, 112, 22],
    plant: [293, 142], cooler: [10, 136], easel: [4, 82],
  },
  tall: {
    w: 220, h: 318, scale: 2, wallH: 56,
    seat: { gemini: [58, 62], chatgpt: [162, 62], gemma: [162, 152], claude: [110, 248] },
    sign: [6, 8], window: [96, 6], tv: [168, 4, 48, 36], rug: [44, 288, 132, 28],
    plant: [186, 262], cooler: [8, 232], easel: [10, 136],
  },
}

export type LayoutName = keyof typeof LAYOUTS

export type View = {
  state: 'idle' | 'working' | 'asking' | 'done' | 'error'
  kind?: string
  secs?: number
}

const secsBetween = (from: number, to: number) => Math.max(0, Math.round((to - from) / 1000))

export function workerView(s: TeamState, id: WorkerId, now: number): View {
  if (id === 'claude') {
    if (s.asking) return { state: 'asking', kind: tx('Waiting for your answer') }
    return s.claudeBusySince === undefined
      ? { state: 'idle' }
      : { state: 'working', kind: s.claudeTool ?? tx('Thinking'), secs: secsBetween(s.claudeBusySince, now) }
  }
  const running = s.jobs.filter(j => j.worker === id && j.endedAt === undefined)
  const newest = running[running.length - 1]
  if (newest) {
    const more = running.length > 1 ? ` +${running.length - 1}` : ''
    return { state: 'working', kind: newest.kind + more, secs: secsBetween(newest.startedAt, now) }
  }
  const last = [...s.jobs].reverse().find(j => j.worker === id)
  if (last?.endedAt !== undefined && now - last.endedAt < BADGE_MS) {
    return { state: last.ok ? 'done' : 'error', kind: last.kind, secs: secsBetween(last.startedAt, last.endedAt) }
  }
  return { state: 'idle' }
}

export function formatSecs(secs: number): string {
  if (secs < 60) return tx('{n} sec', { n: secs })
  const m = Math.floor(secs / 60)
  const r = secs % 60
  return r === 0 ? tx('{n} min', { n: m }) : tx('{m} min {s} sec', { m, s: r })
}

const pad2 = (n: number) => String(n).padStart(2, '0')

// "14:24", local time
// "14:24", giờ địa phương
export function clockLabel(ms: number): string {
  const d = new Date(ms)
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`
}

// day heading for a list of jobs: "Today", "Yesterday" or "10/29/2026" (local time)
// tiêu đề ngày cho một danh sách việc: "Hôm nay", "Hôm qua" hoặc "29/10/2026" (giờ địa phương)
export function dayLabel(ms: number, now: number): string {
  const d = new Date(ms)
  const t = new Date(now)
  if (d.toDateString() === t.toDateString()) return tx('Today')
  t.setDate(t.getDate() - 1)
  if (d.toDateString() === t.toDateString()) return tx('Yesterday')
  if (getLang() === 'en') return d.toLocaleDateString('en-US', { day: '2-digit', month: '2-digit', year: 'numeric' })
  return `${pad2(d.getDate())}/${pad2(d.getMonth() + 1)}/${d.getFullYear()}`
}

// ---- drawing ---------------------------------------------------------------
// ---- vẽ ---------------------------------------------------------------

const esc = (t: string) => t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
const r = (x: number, y: number, w: number, h: number, fill: string, extra = '') =>
  `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${fill}"${extra}/>`
const text = (x: number, y: number, size: number, fill: string, t: string, extra = '') =>
  `<text x="${x}" y="${y}" font-size="${size}" fill="${fill}" text-anchor="middle"${extra}>${esc(t)}</text>`
const place = ([x, y]: [number, number], scale: number, body: string) =>
  `<g transform="translate(${x} ${y}) scale(${scale})">${body}</g>`

/** Hand angles in degrees for a local time: hour, minute, second. */
/** Góc các kim tính bằng độ cho một giờ địa phương: kim giờ, phút, giây. */
export function clockAngles(now: number): [number, number, number] {
  const d = new Date(now)
  const sec = d.getSeconds()
  const min = d.getMinutes() + sec / 60
  return [((d.getHours() % 12) + min / 60) * 30, min * 6, sec * 6]
}

/**
 * A wall clock on local time. The hands carry ids so the browser view can
 * turn them every second without redrawing; elsewhere the second hand sweeps.
 */
/** Đồng hồ treo tường theo giờ địa phương. Các kim có id để trang trình duyệt có thể quay chúng mỗi giây mà không vẽ lại; ở nơi khác kim giây quét liên tục. */
/** The potted plant, a little shorter than a person: where it stands and how big. */
/** Chậu cây, thấp hơn một người một chút: đứng ở đâu và to cỡ nào. */
function plantBox(L: Layout): { x: number; y: number; k: number; w: number; h: number } {
  const k = L.scale * 0.5
  // keep it centred and standing on the same floor spot it always had
  // giữ nó ở giữa và đứng đúng chỗ sàn như trước nay
  return { x: L.plant[0] + 3 * L.scale, y: L.plant[1] + 32 * L.scale * 0.3, k, w: 20 * k, h: 32 * k }
}

function wallClock([cx, cy]: [number, number], now: number): string {
  const [h, m, sec] = clockAngles(now)
  const hand = (id: string, angle: number, len: number, w: number, fill: string, extra = '') =>
    `<g id="${id}" transform="rotate(${angle.toFixed(1)} ${cx} ${cy})">${r(cx - w / 2, cy - len, w, len + 1, fill)}${extra}</g>`
  const ticks = [0, 90, 180, 270].map(a => `<g transform="rotate(${a} ${cx} ${cy})">${r(cx - 0.4, cy - 8.4, 0.8, 1.6, '#8a7a6a')}</g>`).join('')
  return [
    `<circle cx="${cx}" cy="${cy}" r="11" fill="#5a4636"/><circle cx="${cx}" cy="${cy}" r="9" fill="#fffaf0"/>`,
    ticks,
    hand('clk-h', h, 4.6, 1.3, '#3a2a20'),
    hand('clk-m', m, 7, 0.9, '#3a2a20'),
    hand('clk-s', sec, 7.8, 0.45, '#c4553f',
      `<animateTransform attributeName="transform" type="rotate" additive="sum" from="0 ${cx} ${cy}" to="360 ${cx} ${cy}" dur="60s" repeatCount="indefinite"/>`),
    `<circle cx="${cx}" cy="${cy}" r="0.9" fill="#3a2a20"/>`,
  ].join('')
}

const BAR: Record<View['state'], string> = { working: '#69db7c', done: '#69db7c', asking: '#ffd43b', error: '#ff6b6b', idle: '#3b4652' }
const blink = (dur: string) => `<animate attributeName="opacity" values="1;0.35;1" dur="${dur}" repeatCount="indefinite"/>`

/** `m:ss` for the TV, which has no room for words. */
/** `m:ss` cho TV, vì TV không có chỗ cho chữ. */
const clockText = (secs: number) => `${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, '0')}`

/** A tiny face for the TV: hair, skin, two eyes, the shirt's collar. */
/** Một khuôn mặt nhỏ cho TV: tóc, da, hai mắt, cổ áo. */
function miniHead(w: Worker, x: number, y: number, u: number): string {
  return [
    r(x, y, 6 * u, 2 * u, w.hair), r(x, y + 2 * u, u, 2 * u, w.hair), r(x + 5 * u, y + 2 * u, u, 2 * u, w.hair),
    r(x + u, y + 2 * u, 4 * u, 3 * u, w.skin),
    r(x + 2 * u, y + 3 * u, 0.6 * u, 0.8 * u, '#2b2118'), r(x + 3.4 * u, y + 3 * u, 0.6 * u, 0.8 * u, '#2b2118'),
    r(x, y + 5 * u, 6 * u, 1.4 * u, w.shirt),
  ].join('')
}

/**
 * The wall TV: a slim flat screen. `status` shows each member as a small face
 * with a light under it (green working, yellow waiting on you, red failed),
 * then the plan's step and how long Claude has been at it, never what the
 * work is; `logo` is the idle screen, for when the side column shows it all.
 */
/** TV treo tường: màn hình phẳng mỏng. `status` hiện từng thành viên bằng một khuôn mặt nhỏ với một đèn bên dưới (xanh đang làm, vàng chờ bạn, đỏ thất bại), rồi bước của kế hoạch và Claude đã làm bao lâu, không bao giờ hiện việc là gì; `logo` là màn hình lúc rảnh, khi cột bên cạnh đã hiện đủ. */
function tv(L: Layout, s: TeamState, now: number, screen: TvScreen): string {
  const [x, y, w, h] = L.tv
  const sx = x + 1.5
  const sy = y + 1.5
  const sw = w - 3
  const sh = h - 3
  // power cord hanging from under the screen to a wall socket; it fades with the room
  // dây điện thõng từ dưới màn hình xuống ổ cắm tường; nó mờ dần cùng căn phòng
  const px = x + w - 9
  const ox = x + w - 6
  const oy = y + h + 7
  const cord = `<g class="fade">${[
    `<path d="M${px} ${y + h} C${px} ${y + h + 5} ${ox - 2} ${oy - 4} ${ox + 2} ${oy + 1}" fill="none" stroke="#2a2522" stroke-width="0.8" stroke-linecap="round" shape-rendering="auto"/>`,
    r(px - 1, y + h - 0.2, 2, 1.2, '#2a2522'),
    `<rect x="${ox - 0.5}" y="${oy}" width="5" height="6" rx="0.6" fill="#f7f3ea" stroke="#cbbfae" stroke-width="0.4"/>`,
    r(ox + 0.9, oy + 1.6, 0.6, 1.2, '#6f655a'), r(ox + 2.5, oy + 1.6, 0.6, 1.2, '#6f655a'),
    r(ox + 1.2, oy + 0.6, 1.6, 1.4, '#2a2522'),
  ].join('')}</g>`
  const out = [
    cord,
    // wall bracket shadow, slim bezel, screen with a soft glow and a glare streak
    // bóng của giá treo tường, viền mỏng, màn hình có ánh sáng dịu và một vệt phản chiếu
    r(x + 1, y + h, w - 2, 1, 'rgba(60,40,25,.18)'),
    `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="1.2" fill="#1b1d22"/>`,
    `<defs><linearGradient id="tvscr" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#16263a"/><stop offset="1" stop-color="#0b1420"/></linearGradient></defs>`,
    `<rect id="tv-scr" x="${sx}" y="${sy}" width="${sw}" height="${sh}" fill="url(#tvscr)"/>`,
    `<polygon points="${sx + sw * 0.55},${sy} ${sx + sw * 0.7},${sy} ${sx + sw * 0.42},${sy + sh} ${sx + sw * 0.27},${sy + sh}" fill="#ffffff" opacity="0.035"/>`,
    r(x + w / 2 - 1, y + h - 1, 2, 0.6, screen === 'logo' ? '#7a8696' : '#69db7c'),
  ]
  // the browser view lays its own screen over this one
  // trang trình duyệt tự phủ màn hình của nó lên trên cái này
  if (screen === 'blank') return `<g class="tv">${out.join('')}</g>`
  if (screen === 'logo') {
    out.push(text(sx + sw / 2, sy + sh / 2 + 2.2, Math.min(7, sw / 7), '#8fb8de', BRAND.sign, ' font-weight="700" letter-spacing="0.6"'))
    return `<g class="tv">${out.join('')}</g>`
  }
  const views = WORKERS.map(wk => ({ wk, v: workerView(s, wk.id, now) }))
  const u = Math.min(sw / views.length / 9, sh / 16)
  const gap = sw / views.length
  const top = sy + sh * 0.14
  views.forEach(({ wk, v }, i) => {
    const hx = sx + gap * (i + 0.5) - 3 * u
    const lively = v.state === 'working' || v.state === 'asking'
    out.push(`<g opacity="${v.state === 'idle' ? 0.45 : 1}">${miniHead(wk, hx, top, u)}</g>`)
    out.push(`<rect x="${hx}" y="${top + 7.6 * u}" width="${6 * u}" height="${u}" fill="${BAR[v.state]}">${lively ? blink(v.state === 'asking' ? '0.8s' : '1.4s') : ''}</rect>`)
  })
  const claude = views[0]!.v
  const plan = s.plan ?? []
  const done = plan.filter(p => p.status === 'completed').length
  const step = Math.min(plan.length, done + (plan.some(p => p.status === 'in_progress') ? 1 : 0))
  const busy = claude.state === 'working' || claude.state === 'asking'
  const line = claude.state === 'asking' ? tx('WAITING FOR YOU') : claude.secs !== undefined ? clockText(claude.secs) : tx('idle')
  const full = busy && plan.length ? `${step}/${plan.length}  ${line}` : line
  const ty = sy + sh - sh * 0.16
  out.push(claude.state === 'asking'
    ? `<g>${text(sx + sw / 2, ty, Math.min(4.4, sh / 6.5), '#ffd43b', full, ' font-weight="700"')}${blink('0.8s')}</g>`
    : text(sx + sw / 2, ty, Math.min(4.4, sh / 6.5), busy ? '#cfe3f2' : '#6f8297', full))
  return `<g class="tv">${out.join('')}</g>`
}

function room(L: Layout, now: number): string {
  const planks: string[] = []
  for (let y = L.wallH; y < L.h; y += 10) {
    planks.push(r(0, y, L.w, 1, '#c0935f'))
    const off = ((y - L.wallH) / 10) % 2 === 0 ? 0 : 20
    for (let x = off; x < L.w; x += 40) planks.push(r(x, y + 1, 1, 9, '#c0935f'))
  }
  const [sx, sy] = L.sign
  const [wx, wy] = L.window
  const [rx, ry, rw, rh] = L.rug
  return [
    r(0, 0, L.w, L.wallH, '#efe3cf'),
    r(0, L.wallH - 18, L.w, 18, '#c9a27e'),
    r(0, L.wallH - 19, L.w, 2, '#a47c5a'),
    r(0, L.wallH, L.w, L.h - L.wallH, '#d2a679'),
    planks.join(''),
    // chalkboard sign
    // bảng phấn làm biển hiệu
    r(sx, sy, 58, 20, '#6b4a33'),
    r(sx + 1.5, sy + 1.5, 55, 17, '#3d5a40'),
    text(sx + 29, sy + 13, 7.5, '#f8f4e3', BRAND.sign, ` font-weight="700" letter-spacing="0.4"${BRAND.sign.length > 7 ? ' textLength="50" lengthAdjust="spacingAndGlyphs"' : ''}`),
    // window with drifting clouds
    // cửa sổ có mây trôi
    r(wx, wy, 68, 38, '#8b6a4f'),
    r(wx + 3, wy + 3, 62, 32, '#a9dcff'),
    `<clipPath id="win"><rect x="${wx + 3}" y="${wy + 3}" width="62" height="32"/></clipPath>`,
    `<g clip-path="url(#win)"><g>`,
    r(wx - 16, wy + 8, 14, 4, '#ffffff'), r(wx - 13, wy + 5, 8, 3, '#ffffff'),
    r(wx + 24, wy + 20, 18, 4, '#ffffff'), r(wx + 28, wy + 17, 9, 3, '#ffffff'),
    `<animateTransform attributeName="transform" type="translate" values="-30 0;90 0" dur="40s" repeatCount="indefinite"/></g></g>`,
    r(wx + 33, wy + 3, 2, 32, '#8b6a4f'), r(wx + 3, wy + 18, 62, 2, '#8b6a4f'),
    // wall clock
    // to the minute, so the drawing itself changes at most once a minute
    // đồng hồ treo tường
    // tính theo phút, nên hình vẽ tự nó đổi nhiều nhất mỗi phút một lần
    L.clock ? wallClock(L.clock, Math.floor(now / 60_000) * 60_000) : '',
    // rug under the lead desk
    // thảm dưới bàn của trưởng nhóm
    r(rx, ry, rw, rh, '#b6503c'), r(rx + 4, ry + 3, rw - 8, rh - 6, '#c96a52'), r(rx + 8, ry + 6, rw - 16, rh - 12, '#b6503c'),
    // plant and water cooler, drawn at the origin
    // cây và bình nước, vẽ ở gốc
    place([plantBox(L).x, plantBox(L).y], plantBox(L).k, [
      r(3, 18, 14, 14, '#a65e3a'), r(1, 16, 18, 3, '#8a4b2c'),
      r(5, 4, 4, 12, '#3f8f4e'), r(10, 0, 4, 16, '#4fa35d'), r(0, 8, 5, 6, '#4fa35d'), r(15, 6, 5, 8, '#3f8f4e'),
    ].join('')),
    // standing water dispenser (silver, black frame) with a water bottle on top
    // bình nước đứng (bạc, khung đen) có một chai nước ở trên
    place(L.cooler, L.scale * 0.8, [
      // bottle: clear blue, ridged, navy label with the brand in white italic
      // chai: xanh trong, có gân, nhãn xanh navy với tên hãng chữ nghiêng trắng
      r(3, 0, 14, 18, '#9fd4f2'), r(3, 3, 14, 1, '#7fbfe6'), r(3, 15, 14, 1, '#7fbfe6'),
      r(4, 1, 2, 15, '#d2ecfb'), r(16, 1, 1, 16, '#86c3e8'),
      r(3, 6, 14, 7, '#1f3a93'), r(3, 12, 14, 1, '#2f56c4'),
      `<text x="10" y="11.2" font-size="4.2" textLength="11.5" lengthAdjust="spacingAndGlyphs" font-weight="700" font-style="italic" font-family="Georgia, 'Times New Roman', serif" fill="#ffffff" text-anchor="middle" shape-rendering="auto">${esc(BRAND.water)}</text>`,
      r(8, 18, 4, 2, '#7fbfe6'), r(7, 20, 6, 1, '#1c1c1c'),
      // machine: black frame, control panel, two doors, base
      // máy: khung đen, bảng điều khiển, hai cánh cửa, đế
      r(2, 21, 16, 31, '#1f1f22'),
      r(3, 22, 14, 6, '#dcdee3'), r(7, 23, 6, 1, '#9aa0a8'),
      r(6, 26, 1, 1, '#4a4f57'), r(9.5, 26, 1, 1, '#4a4f57'), r(13, 26, 1, 1, '#4a4f57'),
      r(3, 29, 14, 11, '#c9ccd2'), r(4, 29, 1, 11, '#e4e6ea'),
      r(3, 41, 14, 10, '#c9ccd2'), r(4, 41, 1, 10, '#e4e6ea'),
      r(2, 51, 16, 1, '#111113'), r(3, 52, 2, 1, '#111113'), r(15, 52, 2, 1, '#111113'),
    ].join('')),
  ].join('')
}

function easel(L: Layout, painting: boolean): string {
  const strokes = painting
    ? [
        `<rect x="4" y="8" width="0" height="2" fill="#4f7df3"><animate attributeName="width" values="0;12;12" dur="1.6s" repeatCount="indefinite"/></rect>`,
        `<rect x="4" y="12" width="0" height="2" fill="#f59f00"><animate attributeName="width" values="0;0;9;9" dur="1.6s" repeatCount="indefinite"/></rect>`,
        `<rect x="4" y="16" width="0" height="2" fill="#e8590c"><animate attributeName="width" values="0;0;0;14" dur="1.6s" repeatCount="indefinite"/></rect>`,
      ].join('')
    : r(6, 11, 8, 6, '#dfe7d0')
  return place(L.easel, L.scale * 0.8, [
    r(2, 22, 2, 18, '#7a4a2b'), r(18, 22, 2, 18, '#7a4a2b'), r(10, 0, 2, 40, '#8d5a3b'),
    r(0, 4, 22, 18, '#5a3a24'), r(1, 5, 20, 16, '#fbf8f1'), strokes,
  ].join(''))
}

function bubble(cx: number, top: number, label: string, minX: number, maxX: number, fill = '#ffffff'): string {
  const w = Math.min(96, Math.round(label.length * 3.1) + 16)
  // centred over the head, but kept inside the room
  // ở giữa phía trên đầu, nhưng giữ trong phòng
  const x = Math.round(Math.max(minX, Math.min(maxX - w, cx - w / 2)))
  const dots = [0, 1, 2]
    .map(i => `<rect x="${x + w - 9 + i * 2}" y="${top + 6}" width="1" height="1" fill="#555"><animate attributeName="opacity" values="0;1;1;0" dur="1.2s" begin="${i * 0.2}s" repeatCount="indefinite"/></rect>`)
    .join('')
  return [
    r(x, top, w, 10, '#2b2b2b'), r(x + 1, top + 1, w - 2, 8, fill),
    r(cx - 1, top + 10, 3, 2, '#2b2b2b'), r(cx, top + 9, 1, 2, fill),
    `<text x="${x + 4}" y="${top + 7}" font-size="5" fill="#2b2b2b">${esc(label)}</text>`,
    dots,
  ].join('')
}

function badge(x: number, y: number, ok: boolean): string {
  return [
    `<g>`,
    r(x, y, 10, 10, '#2b2b2b'), r(x + 1, y + 1, 8, 8, ok ? '#2f9e44' : '#e03131'),
    text(x + 5, y + 8, 7, '#ffffff', ok ? '✓' : '!', ' font-weight="700"'),
    `<animate attributeName="opacity" values="0;1" dur="0.25s" fill="freeze"/></g>`,
  ].join('')
}

/** One person at a desk, drawn around the origin (head centre x, head top y). */
/** Một người ngồi ở bàn, vẽ quanh gốc (tâm đầu x, đỉnh đầu y). */
/**
 * An idle routine's timing: one cycle of `dur` seconds; within it (as
 * fractions) a sip at the desk, a stretch, and the trips away from the desk.
 */
/** Nhịp của một thói quen lúc rảnh: một chu kỳ `dur` giây; trong đó (theo tỉ lệ) một lần nhấp nước ở bàn, một lần vươn vai, và các chuyến đi xa bàn. */
type Stroll = { dur: number; begin: number; sip: [number, number]; stretch: [number, number]; trips: [number, number][] }

/**
 * `look` turns an idle person's gaze toward the wall TV: -1 left .. 1 right,
 * and up, since the TV hangs above them.
 */
/** `look` xoay ánh nhìn của người đang rảnh về phía TV treo tường: -1 trái .. 1 phải, và nhìn lên, vì TV treo cao hơn họ. */
function person(w: Worker, v: View, i: number, minX: number, maxX: number, stroll?: Stroll, look?: number): string {
  const x = 0
  const y = 0
  const working = v.state === 'working'
  const lx = look === undefined ? 0 : Math.round(look * 10) / 10
  const ly = look === undefined ? 0 : 1
  const eyes = (dx: number) =>
    `<rect x="${x + dx + lx}" y="${y + 5 - ly}" width="1" height="1" fill="#2a1f1a"><animate attributeName="height" values="1;1;0;1" keyTimes="0;0.92;0.96;1" dur="${4 + i * 0.7}s" repeatCount="indefinite" calcMode="discrete"/></rect>`
  const mouth = v.state === 'asking' ? r(x - 1, y + 6, 2, 2, '#9c4a33') : v.state === 'done' ? r(x - 2, y + 7, 4, 1, '#9c4a33') : v.state === 'error' ? r(x - 1, y + 7, 2, 1, '#6b2a1a') : r(x - 1, y + 7, 2, 1, '#b5654a')
  const glow = working
    ? `<rect x="${x - 4}" y="${y + 3}" width="8" height="5" fill="#bfe3ff" opacity="0.2"><animate attributeName="opacity" values="0.1;0.3;0.15;0.25;0.1" dur="1.4s" repeatCount="indefinite"/></rect>`
    : ''
  const idleBob = working
    ? ''
    : `<animateTransform attributeName="transform" type="translate" values="0 0;0 1;0 0" dur="${3 + i * 0.5}s" repeatCount="indefinite" calcMode="discrete"/>`
  // turned toward the TV: the hair shows a little more on the far side
  // quay về phía TV: tóc lộ ra nhiều hơn một chút ở phía xa
  const turn = look === undefined ? '' : r(lx > 0 ? x - 4 : x + 3, y + 3, 1, 2, w.hair)
  const head = [
    r(x - 4, y, 8, 1, w.hair), r(x - 5, y + 1, 10, 2, w.hair),
    r(x - 4, y + 3, 8, 5, w.skin), r(x - 5, y + 3, 1, 3, w.hair), r(x + 4, y + 3, 1, 3, w.hair),
    eyes(-2), eyes(1), turn, mouth, glow,
  ].join('')
  const body = [r(x - 6, y + 8, 12, 9, w.shirt), r(x - 6, y + 8, 1, 9, w.shirtDark), r(x + 5, y + 8, 1, 9, w.shirtDark), r(x - 1, y + 8, 2, 1, '#ffffff', ' opacity="0.6"')].join('')
  const hand = (hx: number, delay: number) =>
    working
      ? `<rect x="${hx}" y="${y + 16}" width="3" height="2" fill="${w.skin}"><animate attributeName="y" values="${y + 16};${y + 15};${y + 16}" dur="0.32s" begin="${delay}s" repeatCount="indefinite" calcMode="discrete"/></rect>`
      : ''
  const laptop = [r(x - 8, y + 10, 16, 8, '#aeb5c0'), r(x - 7, y + 11, 14, 6, '#c9ced6'), r(x - 1, y + 13, 2, 2, w.shirt)].join('')
  // a 500 ml water bottle on every desk; between tasks each person takes a sip now and then
  // một chai nước 500 ml trên mỗi bàn; giữa các việc, mỗi người thỉnh thoảng nhấp một ngụm
  const bx = x + 14
  const by = y + 5.2
  const clear = '#e3eef7'
  const ridge = '#cfdfec'
  const bottle = [
    // short, wide ribbed cap, then a short clear neck
    // nắp ngắn, rộng, có gân, rồi một cổ chai ngắn trong suốt
    r(bx + 1.6, by, 2.8, 1.1, '#f4f5f7'), r(bx + 1.6, by + 0.35, 2.8, 0.2, '#d6dade'), r(bx + 1.6, by + 0.75, 2.8, 0.2, '#d6dade'),
    r(bx + 1.4, by + 1.1, 3.2, 0.35, '#e9ecef'),
    r(bx + 2, by + 1.45, 2, 0.6, '#eef5fb'),
    // rounded shoulder down to the body
    // vai tròn đổ xuống thân chai
    r(bx + 1.4, by + 2.05, 3.2, 0.5, clear), r(bx + 0.8, by + 2.55, 4.4, 0.5, clear), r(bx + 0.3, by + 3.05, 5.4, 0.55, clear),
    r(bx, by + 3.6, 6, 8.4, clear), r(bx + 0.5, by + 4, 0.6, 7.6, '#f7fbfe'),
    r(bx, by + 4.2, 6, 0.25, ridge), r(bx, by + 11, 6, 0.25, ridge),
    // navy label with the light-blue wave at its foot
    // nhãn xanh navy với làn sóng xanh nhạt ở chân nhãn
    r(bx, by + 4.8, 6, 5.4, '#1f3a93'), r(bx, by + 9.7, 6, 0.5, '#5fa8e0'),
    // the brand runs up the label, as on the real 500 ml bottle
    // tên hãng chạy dọc nhãn, như chai 500 ml thật
    `<text transform="translate(${bx + 3.9} ${by + 7.25}) rotate(-90)" font-size="2.4" textLength="4.2" lengthAdjust="spacingAndGlyphs" text-anchor="middle" font-weight="700" font-style="italic" font-family="Georgia, 'Times New Roman', serif" fill="#ffffff" shape-rendering="auto">${esc(BRAND.water)}</text>`,
    // petaloid feet
    // chân hình cánh hoa
    r(bx + 0.3, by + 12, 1.6, 0.8, '#d5e5f2'), r(bx + 2.2, by + 12, 1.6, 0.8, '#d5e5f2'), r(bx + 4.1, by + 12, 1.6, 0.8, '#d5e5f2'),
  ].join('')
  const sipping = v.state === 'idle' || v.state === 'done'
  const sipDur = stroll ? stroll.dur : 9 + i * 2.3
  const sipBegin = stroll ? stroll.begin : 1.5 + i * 1.7
  // with a stroll in the cycle, the sip comes early, while still at the desk
  // khi chu kỳ có đi dạo, ngụm nước đến sớm, lúc còn ngồi ở bàn
  const sipTimes = stroll
    ? `0;${stroll.sip[0]};${+(stroll.sip[0] + 0.01).toFixed(3)};${+(stroll.sip[1] - 0.01).toFixed(3)};${stroll.sip[1]};1`
    : '0;0.72;0.78;0.9;0.96;1'
  const sip = sipping
    ? `<animateTransform attributeName="transform" type="translate" values="0 0;0 0;-15 -3;-15 -3;0 0;0 0" keyTimes="${sipTimes}" dur="${sipDur}s" begin="${sipBegin}s" repeatCount="indefinite" calcMode="discrete"/>`
    : ''
  const sipHand = sipping
    ? `<rect x="${bx}" y="${by + 8}" width="2" height="2" fill="${w.skin}" opacity="0"><animate attributeName="opacity" values="0;0;1;1;0;0" keyTimes="${sipTimes}" dur="${sipDur}s" begin="${sipBegin}s" repeatCount="indefinite" calcMode="discrete"/></rect>`
    : ''
  // drawn at full size and shrunk around its base: as small as it goes while the brand stays legible
  // vẽ kích thước đầy đủ rồi thu nhỏ quanh đáy: nhỏ hết mức mà tên hãng vẫn đọc được
  const BOTTLE_SCALE = 0.72
  const baseX = bx + 3
  const baseY = by + 12.8
  // a touch narrower than tall, like the real 500 ml bottle
  // hơi hẹp hơn chiều cao, như chai 500 ml thật
  const BOTTLE_WIDTH = 0.82
  const small = `<g transform="translate(${baseX} ${baseY}) scale(${BOTTLE_SCALE * BOTTLE_WIDTH} ${BOTTLE_SCALE}) translate(${-baseX} ${-baseY})">${bottle}</g>`
  const mug = `<g>${small}${sipHand}${sip}</g>`
  const desk = [
    r(x - 24, y + 18, 48, 3, '#a0673f'), r(x - 24, y + 18, 48, 1, '#b97b4f'),
    r(x - 22, y + 21, 44, 12, '#7a4a2b'), r(x - 22, y + 32, 44, 1, '#5e3820'),
    r(x - 16, y + 23, 32, 8, '#f3e3c3'),
    text(x, y + 28.6, 4.6, '#4a3020', w.name, ' font-weight="700"'),
  ].join('')
  const chair = r(x - 8, y + 2, 16, 16, '#4a3b33') + r(x - 8, y + 2, 16, 1, '#5e4b40')
  const raisedHand =
    v.state === 'asking'
      ? `<g>${r(x + 6, y + 1, 2, 9, w.shirt)}${r(x + 5, y - 2, 4, 3, w.skin)}<animateTransform attributeName="transform" type="rotate" values="0 ${x + 7} ${y + 9};-12 ${x + 7} ${y + 9};0 ${x + 7} ${y + 9}" dur="0.8s" repeatCount="indefinite"/></g>`
      : ''
  const top =
    v.state === 'asking'
      ? bubble(x, y - 16, `${v.kind ?? tx('Waiting for you')} ?`, minX, maxX, '#fff3bf')
      : v.state === 'working' && v.kind
      ? bubble(x, y - 14, v.kind, minX, maxX)
      : v.state === 'done' || v.state === 'error'
        ? badge(x + 6, y - 11, v.state === 'done')
        : ''
  // out for a stroll: the chair is empty while the standing figure walks the room
  // đi dạo: ghế trống trong khi bóng người đứng đi quanh phòng
  const cyc = stroll ? `dur="${stroll.dur}s" begin="${stroll.begin}s" repeatCount="indefinite" calcMode="discrete"` : ''
  const away = stroll
    ? `<animate attributeName="opacity" values="1;${stroll.trips.map(() => '0;1').join(';')}" keyTimes="0;${stroll.trips.flat().join(';')}" ${cyc}/>`
    : ''
  // a stretch at the desk: both arms straight up, the body lifting a little
  // vươn vai ở bàn: hai tay giơ thẳng lên, thân nhấc lên một chút
  const stretch = stroll
    ? `<g opacity="0">${[
        r(x - 8, y - 5, 2, 13, w.shirt), r(x + 6, y - 5, 2, 13, w.shirt),
        r(x - 8, y - 7, 2, 2, w.skin), r(x + 6, y - 7, 2, 2, w.skin),
      ].join('')}<animate attributeName="opacity" values="0;1;0" keyTimes="0;${stroll.stretch[0]};${stroll.stretch[1]}" ${cyc}/></g>`
    : ''
  const lift = stroll
    ? `<animateTransform attributeName="transform" type="translate" values="0 0;0 -1;0 0" keyTimes="0;${stroll.stretch[0]};${stroll.stretch[1]}" ${cyc} additive="sum"/>`
    : ''
  return `${chair}<g><g>${head}${body}${idleBob}</g>${stretch}${lift}${away}</g>${raisedHand}${laptop}${hand(x - 11, 0)}${hand(x + 8, 0.16)}${mug}${desk}${top}`
}

function paper(L: Layout, from: WorkerId, to: WorkerId): string {
  const [sx, sy0] = L.seat[from]
  const [ex, ey0] = L.seat[to]
  const sy = sy0 + 14 * L.scale
  const ey = ey0 + 14 * L.scale
  const midX = (sx + ex) / 2
  const midY = Math.min(sy, ey) - 26
  return [
    `<g opacity="1">`,
    r(-2, -3, 5, 6, '#2b2b2b'), r(-1, -2, 3, 4, '#ffffff'),
    `<animateMotion dur="0.9s" fill="freeze" path="M${sx} ${sy} Q${midX} ${midY} ${ex} ${ey}"/>`,
    `<animate attributeName="opacity" values="1;1;0" keyTimes="0;0.8;1" dur="1.1s" fill="freeze"/>`,
    `</g>`,
  ].join('')
}

function handoffs(L: Layout, jobs: Job[], now: number): string {
  return jobs
    .map(j => {
      if (j.worker === 'claude') return ''
      if (j.endedAt === undefined && now - j.startedAt < FX_MS) return paper(L, 'claude', j.worker)
      if (j.endedAt !== undefined && now - j.endedAt < FX_MS) return paper(L, j.worker, 'claude')
      return ''
    })
    .join('')
}

/** A drink on the way: the cup's timing within the stroll cycle. */
/** Uống nước trên đường: nhịp của chiếc cốc trong chu kỳ đi dạo. */
type CupTiming = { dur: number; begin: number; keyTimes: string }
/** What a stroller carries: a cup to the cooler, a watering can to the plant. */
/** Thứ người đi dạo mang theo: cốc tới chỗ bình nước, bình tưới tới chỗ cây. */
type Carry = 'cup' | 'can'
/** Where a trip goes and what the person does there. */
/** Chuyến đi tới đâu và người đó làm gì ở đó. */
type Errand = 'cooler' | 'plant' | 'window' | 'chat'

/**
 * A standing figure, feet at the origin, facing us. With `cup`, the right hand
 * holds a paper cup and lifts it to drink while standing at the cooler.
 */
/** Một người đứng, chân ở gốc, quay mặt về phía ta. Với `cup`, tay phải cầm một cốc giấy và nâng lên uống khi đứng ở chỗ bình nước. */
/** Seen from behind, looking out of the window: hair where the face was. */
/** Nhìn từ phía sau, nhìn ra cửa sổ: tóc ở chỗ khuôn mặt. */
function backView(w: Worker): string {
  return [
    `<ellipse cx="0" cy="0" rx="6" ry="1.3" fill="#000" opacity="0.15"/>`,
    r(-3, -8, 2.5, 7, '#3b3f4a'), r(0.5, -8, 2.5, 7, '#3b3f4a'),
    r(-3.5, -1.2, 3.2, 1.2, '#2a2522'), r(0.3, -1.2, 3.2, 1.2, '#2a2522'),
    r(-5, -17, 10, 9, w.shirt), r(-5, -17, 10, 1, w.shirtDark),
    r(-7, -16, 2, 7, w.shirt), r(5, -16, 2, 7, w.shirt), r(-7, -9.5, 2, 1.8, w.skin), r(5, -9.5, 2, 1.8, w.skin),
    r(-3, -18, 6, 1.2, w.skin),
    r(-4, -26, 8, 1, w.hair), r(-5, -25, 10, 7, w.hair), r(-4, -18.6, 8, 0.8, w.hair),
  ].join('')
}

/** A small speech bubble with dots that come and go, for a chat at a colleague's desk. */
/** Một bong bóng thoại nhỏ có các chấm hiện rồi mất, cho cuộc trò chuyện ở bàn đồng nghiệp. */
function chatBubble(): string {
  const dot = (dx: number, delay: number) =>
    `<rect x="${dx}" y="-33.4" width="1.2" height="1.2" fill="#4a3020"><animate attributeName="opacity" values="0.2;1;0.2" dur="1.2s" begin="${delay}s" repeatCount="indefinite"/></rect>`
  return [
    `<rect x="1" y="-37" width="11" height="6" rx="1.5" fill="#ffffff" stroke="#2b2b2b" stroke-width="0.5"/>`,
    r(3, -31.2, 1.6, 1.6, '#ffffff'),
    dot(3.2, 0), dot(5.9, 0.2), dot(8.6, 0.4),
  ].join('')
}

function stander(w: Worker, carry?: Carry, cup?: CupTiming): string {
  const eyes = (dx: number) => r(dx, -22, 1, 1, '#2a1f1a')
  return [
    `<ellipse cx="0" cy="0" rx="6" ry="1.3" fill="#000" opacity="0.15"/>`,
    r(-3, -8, 2.5, 7, '#3b3f4a'), r(0.5, -8, 2.5, 7, '#3b3f4a'),
    r(-3.5, -1.2, 3.2, 1.2, '#2a2522'), r(0.3, -1.2, 3.2, 1.2, '#2a2522'),
    r(-5, -17, 10, 9, w.shirt), r(-5, -17, 1, 9, w.shirtDark), r(4, -17, 1, 9, w.shirtDark),
    r(-7, -16, 2, 7, w.shirt), r(5, -16, 2, 7, w.shirt), r(-7, -9.5, 2, 1.8, w.skin),
    r(-4, -26, 8, 1, w.hair), r(-5, -25, 10, 2, w.hair), r(-4, -23, 8, 5, w.skin), r(-5, -23, 1, 3, w.hair), r(4, -23, 1, 3, w.hair),
    eyes(-2), eyes(1), r(-1, -20, 2, 1, '#b5654a'),
    // the cup (or bare hand) last, so a sip shows over the face
    // cốc (hoặc bàn tay trần) vẽ sau cùng, để ngụm nước hiện đè lên mặt
    carry === 'can' && cup
      ? wateringCan(w, cup)
      : cup
      ? `<g>${[
          r(5.2, -13, 3, 3.6, '#fbfbf8'), r(5.2, -13, 3, 0.5, '#dfe3e6'), r(5.2, -11.4, 3, 0.8, '#4a8fd6'),
          r(5, -9.5, 2, 1.8, w.skin),
        ].join('')}<animateTransform attributeName="transform" type="translate" values="0 0;0 0;-6 -7.6;-6 -7.6;0 0;0 0;-6 -7.6;-6 -7.6;0 0;0 0" keyTimes="${cup.keyTimes}" dur="${cup.dur}s" begin="${cup.begin}s" repeatCount="indefinite" calcMode="discrete"/></g>`
      : r(5, -9.5, 2, 1.8, w.skin),
  ].join('')
}

/**
 * A green watering can in the right hand, spout toward the plant. While
 * standing there it tips twice, and water drips from the spout.
 */
/** Một bình tưới xanh lá ở tay phải, vòi hướng về cây. Khi đứng đó nó nghiêng hai lần, và nước nhỏ giọt từ vòi. */
function wateringCan(w: Worker, timing: CupTiming): string {
  const pour = (a: string, b: string) =>
    `values="${a};${a};${b};${b};${a};${a};${b};${b};${a};${a}" keyTimes="${timing.keyTimes}" dur="${timing.dur}s" begin="${timing.begin}s" repeatCount="indefinite" calcMode="discrete"`
  const drop = (dx: number, delay: number) =>
    `<rect x="${12.4 + dx}" y="-11" width="0.7" height="1.2" fill="#6fb6ef"><animate attributeName="y" values="-11;-7.5;-4" dur="0.45s" begin="${delay}s" repeatCount="indefinite"/><animate attributeName="opacity" values="1;1;0" dur="0.45s" begin="${delay}s" repeatCount="indefinite"/></rect>`
  // the can: body, rim, handle, long spout with a rose at its tip; it tips over to pour
  // bình tưới: thân, miệng, quai, vòi dài có đầu sen ở mút; nó nghiêng để rót
  const can = `<g>${[
    r(5.5, -12, 5, 4, '#5f9e6e'), r(5.5, -12, 5, 0.7, '#77b585'), r(5.5, -8.6, 5, 0.6, '#4a7f57'),
    r(6.5, -14, 3, 0.8, '#4a7f57'), r(6.5, -14, 0.8, 2.2, '#4a7f57'), r(8.7, -14, 0.8, 2.2, '#4a7f57'),
    r(10.5, -11.5, 2.2, 0.8, '#5f9e6e'), r(12.2, -12.6, 1, 2, '#4a7f57'),
    r(5, -9.5, 2, 1.8, w.skin),
  ].join('')}<animateTransform attributeName="transform" type="rotate" ${pour('0 6 -9', '32 6 -9')}/></g>`
  // water dripping from the spout while it is tipped
  // nước nhỏ giọt từ vòi khi bình nghiêng
  const water = `<g opacity="0">${drop(1.5, 0)}${drop(2.3, 0.15)}${drop(1.8, 0.3)}<animate attributeName="opacity" ${pour('0', '1')}/></g>`
  // the arm lifts the can up to the plant while pouring
  // tay nhấc bình lên cây khi rót
  return `<g>${can}<animateTransform attributeName="transform" type="translate" ${pour('0 0', '0 -5')}/></g>${water}`
}

/** Step cycle: four frames, legs scissoring, the arm swinging against them. */
/** Chu kỳ bước: bốn khung hình, chân bắt chéo, tay đung đưa ngược lại. */
const STEP = 0.56
const frames = (values: string, begin: number) =>
  `<animateTransform attributeName="transform" type="translate" values="${values}" dur="${STEP}s" begin="${begin}s" repeatCount="indefinite" calcMode="discrete"/>`

/**
 * A figure seen from the side, walking toward +x, feet at the origin: the legs
 * pass each other with the lifted foot off the floor, the arm swings opposite
 * the near leg and the body rises a little as a leg passes under it.
 */
/** Một người nhìn nghiêng, đi về phía +x, chân ở gốc: hai chân qua nhau với chân nhấc khỏi sàn, tay đung đưa ngược với chân gần và thân nhô lên một chút khi một chân đi qua dưới nó. */
function strider(w: Worker, i: number, carry?: Carry): string {
  const d = i * 0.07
  const leg = (fill: string, shoe: string, values: string) =>
    `<g>${r(-1.2, -8, 2.4, 7.2, fill)}${r(-1.2, -1.2, 3.6, 1.2, shoe)}${frames(values, d)}</g>`
  return [
    `<ellipse cx="0" cy="0" rx="5" ry="1.2" fill="#000" opacity="0.15"/>`,
    // far leg (darker) then near leg
    // chân xa (tối hơn) rồi chân gần
    leg('#2f333d', '#1f1b19', '-2.2 0;0 -1;2.2 0;0 0'),
    leg('#3b3f4a', '#2a2522', '2.2 0;0 0;-2.2 0;0 -1'),
    `<g>${[
      // body, narrower in profile, darker on the back
      // thân, hẹp hơn khi nhìn nghiêng, tối hơn ở lưng
      r(-3.5, -17, 7, 9.2, w.shirt), r(-3.5, -17, 1.2, 9.2, w.shirtDark),
      // head in profile: hair at the back, eye and nose to the front
      // đầu nhìn nghiêng: tóc ở phía sau, mắt và mũi ở phía trước
      r(-4, -26, 7.5, 1, w.hair), r(-4.5, -25, 8.5, 2, w.hair),
      r(-3, -23, 6.5, 5, w.skin), r(-4.5, -23, 2, 4, w.hair), r(3.5, -21.5, 0.9, 1.2, w.skin),
      r(1.6, -22, 1, 1, '#2a1f1a'), r(2, -19.6, 1.4, 0.7, '#b5654a'),
      // near arm, swinging against the near leg; the cup rides in its hand
      // tay gần, đung đưa ngược với chân gần; cốc nằm trong tay
      `<g>${r(-1, -16, 2, 7, w.shirtDark)}${r(-1, -9.5, 2, 1.8, w.skin)}${
        carry === 'cup'
          ? r(-0.9, -12.6, 2.6, 3.2, '#fbfbf8') + r(-0.9, -11.2, 2.6, 0.7, '#4a8fd6')
          : carry === 'can'
          ? r(-1.2, -9.4, 4, 3, '#5f9e6e') + r(-1.2, -9.4, 4, 0.6, '#77b585') + r(2.8, -9, 2.2, 0.6, '#5f9e6e')
          : ''
      }${frames('-1.6 0;0 0;1.6 0;0 0', d)}</g>`,
    ].join('')}${frames('0 0;0 -0.6;0 0;0 -0.6', d)}</g>`,
  ].join('')
}

const polyLength = (pts: [number, number][]) =>
  pts.slice(1).reduce((n, p, k) => n + Math.hypot(p[0] - pts[k]![0], p[1] - pts[k]![1]), 0)

/**
 * An idle person's routine. Each cycle they sip at the desk, stretch, then
 * make two trips: to the water cooler (with a cup) or the plant (with a
 * watering can), whichever is on their side, and either to the window to look
 * at the sky or to a colleague's desk for a chat. Back at the desk in between.
 */
/** Thói quen của một người đang rảnh. Mỗi chu kỳ họ nhấp nước ở bàn, vươn vai, rồi đi hai chuyến: tới bình nước (cầm cốc) hoặc tới cây (cầm bình tưới), tuỳ bên nào ở phía họ, và hoặc tới cửa sổ nhìn trời hoặc tới bàn đồng nghiệp trò chuyện. Ở giữa thì về lại bàn. */
function routineFor(L: Layout, id: WorkerId, i: number): { stroll: Stroll; svg: (w: Worker) => string } {
  const [sx, sy] = L.seat[id]
  const s = L.scale
  const k = +(s * 0.9).toFixed(3)
  const t = (n: number) => +n.toFixed(3)
  // leave by the side of the desk that faces the room's middle
  // rời đi từ phía của bàn quay về giữa phòng
  const side = sx > L.w / 2 ? -1 : 1
  const out: [number, number] = [sx + side * 27 * s, Math.min(L.h - 3, sy + 34 * s)]
  const aisle = Math.min(L.h - 3, out[1] + 6)
  const floor = (y: number) => Math.min(L.h - 2, y)

  const spot = (errand: Errand): [number, number] => {
    if (errand === 'cooler') return [L.cooler[0] + 20 * s * 0.8 + 6, floor(L.cooler[1] + 52 * s * 0.8)]
    if (errand === 'plant') return [plantBox(L).x - 8 * k, floor(plantBox(L).y + plantBox(L).h)]
    if (errand === 'window') {
      // the gap between back-row desks nearest the window
      // khoảng giữa các bàn hàng sau gần cửa sổ nhất
      const backY = Math.min(...Object.values(L.seat).map(p => p[1]))
      const back = Object.values(L.seat).filter(p => p[1] === backY).map(p => p[0]).sort((m, n) => m - n)
      const gaps = back.slice(1).map((x, j) => (x + back[j]!) / 2)
      const wx = L.window[0] + 34
      const gx = gaps.reduce((best, g) => (Math.abs(g - wx) < Math.abs(best - wx) ? g : best), gaps[0] ?? wx)
      return [gx, backY + 26 * s]
    }
    // beside the next colleague's desk, on the side they would leave by
    // bên cạnh bàn đồng nghiệp kế tiếp, ở phía họ sẽ rời đi
    const ids: WorkerId[] = ['gemini', 'chatgpt', 'gemma', 'claude']
    const mate = ids[(ids.indexOf(id) + 1) % ids.length]!
    const [mx, my] = L.seat[mate]
    const mside = mx > L.w / 2 ? -1 : 1
    return [mx + mside * 30 * s, floor(my + 30 * s)]
  }
  const route = (to: [number, number]): [number, number][] => [out, [out[0], aisle], [to[0], aisle], to]

  const first: Errand = sx <= L.w / 2 ? 'cooler' : 'plant'
  const second: Errand = i % 2 === 0 ? 'window' : 'chat'
  const r1 = route(spot(first))
  const r2 = route(spot(second))
  // one path for both trips: the first route backwards, then the second
  // một đường đi cho cả hai chuyến: tuyến thứ nhất đi ngược lại, rồi tuyến thứ hai
  const pts = [...r1].reverse().concat(r2.slice(1))
  const path = 'M' + pts.map(p => `${t(p[0])} ${t(p[1])}`).join(' L')
  const f0 = t(polyLength(r1) / Math.max(1, polyLength(r1) + polyLength(r2)))

  const walk = 0.06
  const stroll: Stroll = {
    dur: 70 + i * 9,
    begin: 2 + i * 13,
    sip: [0.05, 0.1],
    stretch: [0.14, 0.18],
    trips: [[0.24, 0.48], [0.58, 0.82]],
  }
  const cyc = `dur="${stroll.dur}s" begin="${stroll.begin}s" repeatCount="indefinite"`
  const [[a1, b1], [a2, b2]] = stroll.trips as [[number, number], [number, number]]
  const keyTimes = [0, a1, a1 + walk, b1 - walk, b1, a2, a2 + walk, b2 - walk, b2, 1].map(t).join(';')
  const keyPoints = [f0, f0, 0, 0, f0, f0, 1, 1, f0, f0].join(';')

  // two sips (or two pours) while standing at the spot
  // hai ngụm nước (hoặc hai lần rót) khi đứng tại chỗ
  const actTimes = (st: number, end: number): CupTiming => {
    const span = end - st
    return {
      dur: stroll.dur,
      begin: stroll.begin,
      keyTimes: [0, st, st + span * 0.15, st + span * 0.35, st + span * 0.4, st + span * 0.6, st + span * 0.65, st + span * 0.85, st + span * 0.9, 1]
        .map(t).join(';'),
    }
  }
  const shown = (from: number, to: number) =>
    `<animate attributeName="opacity" values="0;1;0" keyTimes="0;${t(from)};${t(to)}" ${cyc} calcMode="discrete"/>`
  const facing = (to: [number, number]) => (to[0] >= out[0] ? 1 : -1)

  const trip = (w: Worker, errand: Errand, a: number, b: number, to: [number, number]) => {
    const dir = facing(to)
    const carry: Carry | undefined = errand === 'cooler' ? 'cup' : errand === 'plant' ? 'can' : undefined
    const there =
      errand === 'window' ? backView(w)
        : errand === 'chat' ? stander(w) + chatBubble()
        : stander(w, carry, actTimes(a + walk, b - walk))
    return (
      `<g opacity="0"><g transform="scale(${k * dir} ${k})">${strider(w, i, carry)}</g>${shown(a, a + walk)}</g>` +
      `<g opacity="0"><g transform="scale(${k})">${there}</g>${shown(a + walk, b - walk)}</g>` +
      `<g opacity="0"><g transform="scale(${-k * dir} ${k})">${strider(w, i, carry)}</g>${shown(b - walk, b)}</g>`
    )
  }
  const svg = (w: Worker) =>
    `<g opacity="0">` +
    trip(w, first, a1, b1, spot(first)) +
    trip(w, second, a2, b2, spot(second)) +
    `<animateMotion path="${path}" keyPoints="${keyPoints}" keyTimes="${keyTimes}" calcMode="linear" ${cyc}/>` +
    `<animate attributeName="opacity" values="0;1;0;1;0" keyTimes="0;${a1};${b1};${a2};${b2}" ${cyc} calcMode="discrete"/>` +
    `</g>`
  return { stroll, svg }
}

/**
 * What the wall TV shows: the team's state, just the logo, or nothing
 * (`blank`) for a page that draws the screen itself over the drawing.
 */
/** Thứ mà TV treo tường hiện: trạng thái của nhóm, chỉ có logo, hoặc không có gì (`blank`) cho trang tự vẽ màn hình đè lên hình vẽ. */
export type TvScreen = 'logo' | 'status' | 'blank'

export function buildOfficeSvg(s: TeamState, now: number, layout: LayoutName = 'tall', screen: TvScreen = 'logo'): string {
  const L = LAYOUTS[layout]
  const painting = s.jobs.some(j => j.worker === 'gemini' && j.endedAt === undefined && j.kind === tx('Drawing an image'))
  // back row first, the lead's desk last so it sits in front
  // hàng sau trước, bàn của trưởng nhóm sau cùng để nó nằm phía trước
  const order: WorkerId[] = ['gemini', 'chatgpt', 'gemma', 'claude']
  const walkers: string[] = []
  const people = order
    .map((id, i) => {
      const w = WORKERS.find(x => x.id === id)
      if (!w || ABSENT.has(id)) return ''
      // the room's edges in this person's own units, so a bubble never spills out
      // mép phòng theo đơn vị của riêng người này, để bong bóng không bao giờ tràn ra ngoài
      const [sx] = L.seat[id]
      const minX = (2 - sx) / L.scale
      const maxX = (L.w - 2 - sx) / L.scale
      const v = workerView(s, id, now)
      if (v.state !== 'idle') return place(L.seat[id], L.scale, person(w, v, i, minX, maxX))
      const walk = routineFor(L, id, i)
      walkers.push(walk.svg(w))
      // sitting idle, they watch the wall TV
      // ngồi rảnh thì họ xem TV treo tường
      const tvX = L.tv[0] + L.tv[2] / 2
      const look = Math.max(-1, Math.min(1, (tvX - sx) / 40))
      return place(L.seat[id], L.scale, person(w, v, i, minX, maxX, walk.stroll, look))
    })
    .join('')
  // A large intrinsic size: the pane scales the drawing down to fit its width.
  // Kích thước gốc lớn: khung co hình vẽ nhỏ lại cho vừa chiều rộng.
  return [
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${L.w} ${L.h}" width="${L.w * 5}" height="${L.h * 5}" shape-rendering="crispEdges" font-family="ui-monospace, Menlo, Consolas, monospace">`,
    // The room fades for privacy in the browser view; the TV stays lit.
    // Căn phòng mờ đi để giữ riêng tư trong trang trình duyệt; TV vẫn sáng.
    `<g class="fade">${room(L, now)}</g>`,
    tv(L, s, now, screen),
    `<g class="fade">${easel(L, painting)}${people}${walkers.join('')}${handoffs(L, s.jobs, now)}</g>`,
    `</svg>`,
  ].join('')
}

// in the browser view, the page's config.js has set this before this file loads
// trong trang trình duyệt, config.js của trang đã đặt giá trị này trước khi file này tải
applyConfig((globalThis as { __aiWorkerConfig?: OfficeConfig }).__aiWorkerConfig)
