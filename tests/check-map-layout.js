#!/usr/bin/env node
// Checks where the maps put the office cards: node tests/check-map-layout.js
// Loads server/static/map-common.js with a stand-in for the browser and calls layoutCards with plain numbers.
// Kiểm chỗ các bản đồ đặt thẻ văn phòng: node tests/check-map-layout.js
// Nạp server/static/map-common.js với một trình duyệt giả rồi gọi layoutCards bằng các con số thuần.
'use strict'
const fs = require('fs')
const path = require('path')
const vm = require('vm')

const file = path.join(__dirname, '..', 'server', 'static', 'map-common.js')
const window = {}
const browser = {
  window, tx: s => s, navigator: {}, matchMedia: () => ({ matches: false }), fetch: () => Promise.reject(new Error('no network in this check')),
  document: { currentScript: { src: 'ops.js' }, createElement: () => ({ style: {}, append() {} }), querySelector: () => null },
}
vm.runInNewContext(fs.readFileSync(file, 'utf8'), browser, { filename: file })
const layoutCards = window.MapCommon.layoutCards

const GAP = 4, PIN = { width: 34, height: 44 }
const touches = (a, b) => a.x0 < b.x0 + b.width && b.x0 < a.x0 + a.width && a.y0 < b.y0 + b.height && b.y0 < a.y0 + a.height
const pinOf = c => ({ x0: c.sx - PIN.width / 2, y0: c.sy - PIN.height, width: PIN.width, height: PIN.height })
const card = (name, sx, sy, last) => ({ name, sx, sy, width: 206, height: 52, last })
let failed = 0, passed = 0
function check(name, ok, detail) {
  if (ok) passed++
  else { failed++; console.error('FAIL  ' + name + (detail ? '\n      ' + detail : '')) }
}
// every rule a placed set of cards must keep, as a list of the ones it breaks
// mọi quy tắc một bộ thẻ đã đặt phải giữ, trả về danh sách các quy tắc bị phạm
function broken(cards, blocks, w, h) {
  const bad = []
  cards.forEach((a, i) => {
    for (const b of cards.slice(i + 1)) if (touches(a, b)) bad.push(a.name + ' covers the card of ' + b.name)
    for (const b of cards) if (b !== a && touches(a, pinOf(b))) bad.push(a.name + ' covers the pin of ' + b.name)
    for (const b of blocks) if (touches(a, b)) bad.push(a.name + ' covers a blocked area')
    if (a.x0 < 0 || a.x0 + a.width > w || a.y0 < 0 || a.y0 + a.height > h) bad.push(a.name + ' is outside the frame')
  })
  return bad
}

// 1. the small panel of the board: four offices close together and the branch list floating over the right side
// 1. khung nhỏ của bảng: bốn văn phòng sát nhau và danh sách chi nhánh nổi bên phải
{
  const w = 938, h = 300, list = [{ x0: 680, y0: 8, width: 250, height: 284 }]
  const views = {
    globe: [card('Hanoi', 640, 118), card('Da Nang', 662, 150), card('Head office', 650, 196), card('Can Tho', 644, 204)],
    flat: [card('Hanoi', 447, 72), card('Da Nang', 487, 146), card('Head office', 460, 225), card('Can Tho', 433, 237)],
    tilted: [card('Hanoi', 458, 4), card('Da Nang', 484, 62), card('Head office', 444, 133), card('Can Tho', 418, 142)],
  }
  for (const [view, cards] of Object.entries(views)) {
    const bad = broken(layoutCards(cards, list, w, h), list, w, h)
    check('small panel, ' + view + ': nothing is covered and nothing is cut off', bad.length === 0, bad.join('; '))
  }
}

// 2. an office on its own: the card sits to the right of the pin, level with it
// 2. một văn phòng đứng riêng: thẻ nằm bên phải ghim, ngang với ghim
{
  const [c] = layoutCards([card('Alone', 300, 200)], [], 900, 400)
  check('alone: right of the pin', c.x0 === 319 && c.y0 === 158 && c.slot === 'right-up', JSON.stringify(c))
}

// 3. a pin near the right edge: the card moves to the left of the pin instead of leaving the frame
// 3. ghim sát mép phải: thẻ sang bên trái ghim thay vì ra khỏi khung
{
  const [c] = layoutCards([card('Edge', 860, 200)], [], 900, 400)
  check('right edge: left of the pin', c.x0 + c.width === 841 && c.y0 === 158, JSON.stringify(c))
}

// 4. the card stays on the side it had while that side is nearly as good, so it does not jump while the map turns,
//    and leaves it once that side is clearly worse
// 4. thẻ ở lại bên đang dùng khi bên đó còn gần tốt bằng, để không nhảy qua lại khi bản đồ xoay,
//    và rời đi khi bên đó kém hẳn
{
  const nudge = [{ x0: 330, y0: 205, width: 50, height: 10 }], wall = [{ x0: 330, y0: 170, width: 50, height: 30 }]
  const fresh = layoutCards([card('Steady', 300, 200)], nudge, 900, 400)[0]
  const kept = layoutCards([card('Steady', 300, 200, 'right-up')], nudge, 900, 400)[0]
  const left = layoutCards([card('Steady', 300, 200, 'right-up')], wall, 900, 400)[0]
  check('fresh card: takes the free side', fresh.slot === 'left-up' && fresh.y0 === 158, JSON.stringify(fresh))
  check('small push: the card keeps its side', kept.slot === 'right-up' && kept.y0 === 149, JSON.stringify(kept))
  check('big push: the card changes side', left.slot.startsWith('left') && left.y0 === 158, JSON.stringify(left))
}

// 5. a frame with no free place: every card still gets a place inside the frame's height and nothing throws
// 5. khung không còn chỗ trống: thẻ nào cũng vẫn có chỗ trong chiều cao khung và không lỗi
{
  const h = 120, cards = layoutCards([card('A', 100, 60), card('B', 104, 64), card('C', 108, 68), card('D', 112, 72)], [], 260, h)
  check('no room: cards stay within the height of the frame', cards.every(c => Number.isFinite(c.x0) && c.y0 >= GAP && c.y0 + c.height <= h - GAP), JSON.stringify(cards.map(c => [c.x0, c.y0])))
}

// 6. many offices spread over a wide map: still nothing covered
// 6. nhiều văn phòng rải trên bản đồ rộng: vẫn không gì bị đè
{
  const cards = []
  for (let i = 0; i < 12; i++) cards.push(card('Office ' + i, 200 + (i % 4) * 300, 120 + Math.floor(i / 4) * 170))
  const bad = broken(layoutCards(cards, [], 1566, 648), [], 1566, 648)
  check('twelve offices on the large map: nothing is covered', bad.length === 0, bad.join('; '))
}

// 7. pins: two offices almost on the same spot are drawn side by side, each still clickable, around their middle
// 7. ghim: hai văn phòng gần như trùng chỗ được vẽ cạnh nhau, ghim nào cũng bấm được, quanh điểm giữa của chúng
{
  const spreadPins = window.MapCommon.spreadPins
  const near = spreadPins([{ sx: 402, sy: 257 }, { sx: 386, sy: 270 }], 900)
  check('two pins on one spot: 28 apart, around their middle', Math.abs(near[0] - near[1] - 28) < .1 && Math.abs((near[0] + near[1]) / 2 - 394) < .1, JSON.stringify(near))
  const far = spreadPins([{ sx: 100, sy: 200 }, { sx: 180, sy: 205 }, { sx: 104, sy: 320 }], 900)
  check('pins with room, or one above the other: not moved', far.join() === '100,180,104', JSON.stringify(far))
  const three = spreadPins([{ sx: 300, sy: 200 }, { sx: 300, sy: 204 }, { sx: 301, sy: 198 }], 900).slice().sort((a, b) => a - b)
  check('three pins on one spot: all 28 apart', three[1] - three[0] > 27.9 && three[2] - three[1] > 27.9, JSON.stringify(three))
  const small = spreadPins([{ sx: 300, sy: 200 }, { sx: 302, sy: 200 }], 900, 28 * .62)
  check('small pins of the far view: a smaller gap', Math.abs(small[1] - small[0] - 28 * .62) < .1, JSON.stringify(small))
  // pin B has drifted 3 px to the left of pin A, but it was drawn on the right last time: it stays on the right
  // ghim B đã trôi sang trái ghim A 3 px, nhưng lần trước nó được vẽ bên phải: nó ở lại bên phải
  const kept = spreadPins([{ sx: 300, sy: 200, lean: -14 }, { sx: 297, sy: 200, lean: 14 }], 900)
  check('pins passing each other: no swap of sides', kept[1] > kept[0], JSON.stringify(kept))
  const edge = spreadPins([{ sx: 4, sy: 200 }, { sx: 6, sy: 200 }], 900)
  check('at the left edge: pins stay inside the frame', edge.every(v => v >= 17), JSON.stringify(edge))
}

if (failed) { console.error(failed + ' of ' + (failed + passed) + ' checks failed'); process.exit(1) }
console.log(passed + ' checks passed')
