// Shared part of the three branch map styles: pins, cards, HUD panel, continent data, radar base.
// Drawn from /data numbers grouped by branch; no chat content. No outside services are called.
// Boundaries: Natural Earth, used only to light up the land, not drawn as border lines.
// Phần dùng chung của ba kiểu bản đồ chi nhánh: ghim, thẻ, bảng HUD, dữ liệu lục địa, đáy radar.
// Vẽ từ số liệu /data đã gộp theo chi nhánh; không có nội dung chat. Không gọi dịch vụ ngoài.
// Ranh giới: Natural Earth, chỉ để làm sáng phần đất liền, không vẽ thành đường biên giới.
;(function () {
  'use strict'
  const VN_ISLANDS = [
    [tx('Hoang Sa (Paracel)'), [[111.6,16.5],[111.9,16.7],[112.3,16.9],[112.1,16.4],[111.7,16.2],[112.5,16.5]], 112.05, 15.8],
    [tx('Truong Sa (Spratly)'), [[114.3,11.4],[114.9,10.9],[113.9,10.2],[114.6,9.8],[115.3,10.5],[113.5,9],[114.3,8.6],[115,9.3]], 114.4, 8.1],
  ]
  const VN_OUTLINE = [[107.973,21.508],[107.926,21.499],[107.809,21.497],[107.707,21.406],[107.637,21.368],[107.527,21.336],[107.41,21.285],[107.376,21.194],[107.373,21.128],[107.354,21.055],[107.165,20.949],[107.112,20.96],[107.075,20.999],[107.019,20.991],[106.981,20.971],[106.936,20.974],[106.886,20.95],[106.821,20.958],[106.76,20.991],[106.725,21.0],[106.683,21.0],[106.675,20.96],[106.737,20.806],[106.753,20.735],[106.551,20.527],[106.573,20.392],[106.518,20.289],[106.396,20.206],[106.166,19.992],[106.062,19.987],[105.984,19.939],[105.814,19.587],[105.812,19.467],[105.785,19.379],[105.791,19.294],[105.716,19.128],[105.639,19.057],[105.622,18.966],[105.732,18.779],[105.744,18.746],[105.808,18.646],[105.839,18.574],[105.888,18.502],[106.066,18.316],[106.145,18.259],[106.24,18.221],[106.412,18.053],[106.499,17.946],[106.459,17.874],[106.479,17.72],[106.356,17.765],[106.371,17.747],[106.517,17.663],[106.736,17.367],[106.926,17.221],[107.12,17.056],[107.18,16.898],[107.355,16.794],[107.549,16.643],[107.541,16.609],[107.593,16.568],[107.724,16.488],[107.803,16.403],[107.834,16.322],[107.882,16.31],[107.936,16.329],[107.991,16.337],[108.029,16.331],[108.088,16.243],[108.17,16.164],[108.209,16.091],[108.241,16.101],[108.267,16.09],[108.274,16.029],[108.286,15.989],[108.395,15.872],[108.447,15.763],[108.578,15.585],[108.674,15.484],[108.743,15.427],[108.821,15.378],[108.898,15.181],[108.94,15.001],[109.022,14.803],[109.085,14.716],[109.087,14.553],[109.137,14.384],[109.191,14.27],[109.207,14.154],[109.224,14.097],[109.245,14.053],[109.303,13.856],[109.288,13.765],[109.247,13.855],[109.252,13.591],[109.288,13.451],[109.272,13.279],[109.31,13.219],[109.377,13.025],[109.424,12.956],[109.42,12.719],[109.445,12.6],[109.381,12.671],[109.336,12.752],[109.274,12.709],[109.219,12.646],[109.305,12.391],[109.207,12.415],[109.216,12.073],[109.256,11.993],[109.259,11.955],[109.247,11.909],[109.22,11.959],[109.215,12.01],[109.199,11.999],[109.2,11.972],[109.167,11.912],[109.158,11.837],[109.193,11.773],[109.199,11.725],[109.173,11.665],[109.133,11.601],[109.04,11.593],[109.018,11.468],[108.987,11.336],[108.821,11.315],[108.7,11.199],[108.551,11.156],[108.419,11.041],[108.272,10.934],[108.176,10.92],[108.095,10.897],[108.001,10.72],[107.845,10.7],[107.564,10.555],[107.47,10.486],[107.384,10.459],[107.262,10.398],[107.235,10.42],[107.194,10.472],[107.088,10.498],[107.036,10.556],[107.021,10.631],[107.007,10.661],[106.984,10.618],[106.966,10.441],[106.947,10.4],[106.902,10.383],[106.813,10.433],[106.727,10.536],[106.606,10.465],[106.643,10.456],[106.698,10.462],[106.741,10.444],[106.778,10.376],[106.776,10.339],[106.757,10.296],[106.644,10.289],[106.492,10.304],[106.464,10.298],[106.602,10.232],[106.729,10.193],[106.785,10.151],[106.785,10.116],[106.714,10.06],[106.659,9.991],[106.658,9.949],[106.657,9.901],[106.596,9.86],[106.557,9.868],[106.449,9.94],[106.136,10.222],[106.184,10.142],[106.507,9.821],[106.564,9.716],[106.572,9.641],[106.539,9.604],[106.484,9.559],[106.378,9.556],[106.204,9.675],[105.926,9.962],[105.831,10.001],[106.112,9.674],[106.159,9.594],[106.206,9.502],[106.193,9.448],[106.168,9.397],[105.501,9.093],[105.401,8.962],[105.322,8.801],[105.191,8.711],[105.114,8.629],[104.892,8.583],[104.77,8.598],[104.896,8.747],[104.819,8.802],[104.815,9.185],[104.845,9.606],[104.903,9.816],[104.987,9.869],[105.093,9.901],[105.095,9.945],[105.084,9.996],[105.028,10.067],[104.966,10.101],[104.873,10.115],[104.802,10.203],[104.748,10.199],[104.663,10.17],[104.613,10.208],[104.594,10.267],[104.516,10.34],[104.426,10.411],[104.467,10.422],[104.514,10.463],[104.564,10.516],[104.69,10.523],[104.815,10.521],[104.851,10.534],[104.901,10.59],[104.984,10.662],[105.046,10.702],[105.061,10.734],[105.036,10.809],[105.022,10.887],[105.046,10.911],[105.159,10.898],[105.284,10.861],[105.315,10.845],[105.387,10.94],[105.406,10.952],[105.453,10.951],[105.577,10.969],[105.698,10.994],[105.755,10.99],[105.811,10.926],[105.853,10.864],[105.875,10.858],[105.938,10.885],[105.99,10.852],[106.099,10.797],[106.164,10.795],[106.132,10.922],[106.168,11.012],[106.161,11.037],[106.1,11.079],[105.892,11.245],[105.856,11.294],[105.861,11.372],[105.854,11.487],[105.835,11.559],[105.838,11.601],[105.851,11.635],[105.89,11.648],[105.927,11.653],[105.956,11.682],[106.006,11.758],[106.103,11.751],[106.239,11.708],[106.34,11.682],[106.399,11.687],[106.412,11.698],[106.411,11.738],[106.418,11.912],[106.414,11.948],[106.5,11.966],[106.631,11.969],[106.7,11.979],[106.765,12.052],[106.931,12.077],[107.051,12.176],[107.159,12.277],[107.212,12.304],[107.28,12.322],[107.33,12.319],[107.393,12.26],[107.446,12.296],[107.506,12.365],[107.538,12.432],[107.555,12.54],[107.544,12.706],[107.512,12.836],[107.482,12.933],[107.475,13.03],[107.546,13.225],[107.605,13.438],[107.594,13.522],[107.529,13.654],[107.462,13.816],[107.389,13.993],[107.362,14.019],[107.343,14.069],[107.331,14.127],[107.36,14.308],[107.364,14.369],[107.448,14.451],[107.493,14.546],[107.535,14.65],[107.519,14.705],[107.514,14.817],[107.525,14.872],[107.505,14.916],[107.48,14.98],[107.496,15.021],[107.555,15.057],[107.59,15.118],[107.634,15.19],[107.653,15.255],[107.622,15.31],[107.564,15.392],[107.46,15.466],[107.339,15.56],[107.279,15.619],[107.233,15.678],[107.19,15.747],[107.166,15.802],[107.189,15.839],[107.361,15.922],[107.392,15.952],[107.41,15.998],[107.396,16.043],[107.35,16.067],[107.296,16.084],[107.217,16.136],[107.07,16.28],[107.002,16.312],[106.931,16.353],[106.893,16.397],[106.851,16.516],[106.832,16.526],[106.792,16.49],[106.74,16.453],[106.696,16.459],[106.656,16.493],[106.638,16.538],[106.594,16.6],[106.546,16.651],[106.534,16.821],[106.526,16.877],[106.502,16.954],[106.465,16.982],[106.426,17.003],[106.333,17.144],[106.27,17.217],[106.006,17.415],[105.974,17.447],[105.903,17.529],[105.779,17.644],[105.691,17.738],[105.627,17.834],[105.598,17.918],[105.588,17.984],[105.519,18.077],[105.458,18.154],[105.4,18.179],[105.333,18.19],[105.273,18.235],[105.163,18.339],[105.115,18.405],[105.086,18.45],[105.087,18.496],[105.113,18.573],[105.145,18.617],[105.146,18.651],[105.115,18.679],[104.993,18.728],[104.717,18.803],[104.613,18.861],[104.518,18.934],[104.446,18.984],[104.109,19.196],[104.006,19.231],[103.918,19.269],[103.892,19.305],[103.896,19.34],[103.932,19.366],[104.028,19.42],[104.063,19.483],[104.052,19.564],[104.013,19.646],[104.032,19.675],[104.063,19.678],[104.127,19.681],[104.26,19.685],[104.546,19.611],[104.588,19.619],[104.743,19.755],[104.802,19.836],[104.815,19.904],[104.846,19.947],[104.928,20.018],[104.929,20.083],[104.889,20.169],[104.848,20.202],[104.813,20.217],[104.699,20.205],[104.677,20.225],[104.662,20.289],[104.656,20.329],[104.619,20.375],[104.496,20.414],[104.392,20.425],[104.368,20.441],[104.408,20.486],[104.479,20.53],[104.533,20.555],[104.575,20.6],[104.583,20.647],[104.53,20.688],[104.461,20.734],[104.35,20.821],[104.195,20.914],[104.101,20.946],[104.052,20.941],[103.882,20.861],[103.791,20.81],[103.714,20.717],[103.635,20.697],[103.555,20.738],[103.464,20.78],[103.211,20.841],[103.104,20.892],[102.884,21.203],[102.851,21.266],[102.872,21.337],[102.888,21.44],[102.91,21.506],[102.949,21.57],[102.959,21.626],[102.95,21.681],[102.918,21.713],[102.876,21.722],[102.845,21.735],[102.816,21.807],[102.798,21.798],[102.771,21.71],[102.739,21.678],[102.695,21.662],[102.662,21.676],[102.641,21.711],[102.631,21.771],[102.61,21.852],[102.583,21.904],[102.487,21.958],[102.443,22.027],[102.301,22.178],[102.183,22.284],[102.127,22.379],[102.176,22.415],[102.237,22.466],[102.302,22.546],[102.376,22.647],[102.406,22.708],[102.428,22.733],[102.471,22.751],[102.517,22.741],[102.599,22.7],[102.721,22.648],[102.83,22.587],[102.874,22.525],[102.935,22.466],[102.982,22.448],[103.005,22.453],[103.076,22.498],[103.136,22.542],[103.138,22.593],[103.193,22.639],[103.266,22.714],[103.301,22.764],[103.327,22.77],[103.356,22.755],[103.471,22.597],[103.493,22.588],[103.525,22.612],[103.571,22.734],[103.62,22.782],[103.637,22.77],[103.915,22.538],[103.942,22.54],[103.971,22.55],[103.991,22.586],[104.013,22.666],[104.054,22.752],[104.143,22.8],[104.213,22.809],[104.238,22.769],[104.298,22.712],[104.372,22.704],[104.527,22.804],[104.578,22.82],[104.632,22.818],[104.687,22.822],[104.74,22.86],[104.796,22.911],[104.815,23.011],[104.827,23.1],[104.865,23.136],[104.91,23.161],[104.996,23.194],[105.189,23.281],[105.239,23.322],[105.275,23.345],[105.35,23.308],[105.44,23.235],[105.495,23.181],[105.531,23.122],[105.548,23.073],[105.691,23.03],[105.782,22.969],[105.843,22.923],[105.903,22.925],[105.962,22.937],[106.001,22.975],[106.068,22.976],[106.148,22.97],[106.184,22.955],[106.249,22.869],[106.279,22.857],[106.338,22.863],[106.451,22.894],[106.542,22.908],[106.624,22.874],[106.78,22.779],[106.736,22.711],[106.702,22.638],[106.633,22.586],[106.582,22.573],[106.55,22.501],[106.536,22.395],[106.554,22.342],[106.593,22.325],[106.637,22.289],[106.654,22.241],[106.66,22.136],[106.658,22.018],[106.664,21.979],[106.698,21.986],[106.729,22.0],[106.794,21.982],[106.875,21.951],[106.925,21.92],[106.971,21.924],[107.006,21.893],[107.02,21.835],[107.062,21.794],[107.179,21.717],[107.272,21.711],[107.351,21.609],[107.433,21.642],[107.471,21.598],[107.641,21.614],[107.759,21.655],[107.802,21.645],[107.908,21.56],[107.973,21.508]]
  const insideVN = (lon, lat) => {
    let t = false
    for (let i = 0, j = VN_OUTLINE.length - 1; i < VN_OUTLINE.length; j = i++) {
      const [a, b] = VN_OUTLINE[i], [c, d] = VN_OUTLINE[j]
      if ((b > lat) !== (d > lat) && lon < ((c - a) * (lat - b)) / (d - b) + a) t = !t
    }
    return t
  }
  const scriptSrc = (document.querySelector('script[src*="ops.js"]') || {}).src || 'ops.js'
  const loadJson = name => fetch(scriptSrc.replace(/ops\.js.*$/, name), { credentials: 'same-origin' }).then(r => {
    if (!r.ok) throw new Error(name + ': ' + r.status)
    return r.json()
  })
  // a machine with few cores draws fewer points
  // máy ít lõi thì vẽ ít điểm hơn
  const countPeople = n => (n === 1 ? tx('{n} person', { n }) : tx('{n} people', { n }))
  const LOW_POWER = (navigator.hardwareConcurrency || 8) <= 4
  const REDUCED_MOTION = matchMedia('(prefers-reduced-motion: reduce)').matches

  function forEachRing(land, ham) {
    for (const f of land.features) for (const poly of f.geometry.type === 'Polygon' ? [f.geometry.coordinates] : f.geometry.coordinates) ham(poly)
  }

  // numbers for one branch, added up from each person
  // số liệu một chi nhánh, gộp từ từng người
  function summarize(n) {
    const height = kind => Math.round(Math.max(0, ...n.members.flatMap(p => ((p.quota && p.quota.windows) || []).filter(c => c.kind === kind).map(c => c.pct))))
    const sum = ham => n.members.reduce((a, p) => a + (ham(p) || 0), 0)
    const tasks = i => sum(p => (p.tasks || [])[i])
    const sessionsCount = sum(p => p.openSessions)
    const running = i => sum(p => (p.delegating || [])[i])
    const members = []
    if (sessionsCount) members.push('Claude')
    if (tasks(1) || running(1)) members.push('ChatGPT')
    if (tasks(0) || running(0)) members.push('Gemini')
    if (tasks(2) || running(2)) members.push('Gemma')
    return {
      h5: height('five_hour'), h7: height('seven_day'), usd7d: sum(p => p.usd7d), members,
      hours: Array.from({ length: 24 }, (_, i) => sum(p => (p.hourly24 || [])[i])),
      tasks: [[tx('Claude · sessions'), sessionsCount], ['ChatGPT', tasks(1)], ['Gemini', tasks(0)], ['Gemma', tasks(2)]],
    }
  }
  const pinClass = n => (n.critical ? 'critical' : n.waiting ? 'waiting' : n.working ? 'active' : 'idle')
  // which offices keep their card first when the map is crowded: near the quota limit, then waiting, working, idle
  // văn phòng nào được giữ thẻ trước khi bản đồ chật: sắp hết hạn mức, rồi đang chờ, đang làm, rảnh
  const ATTENTION = ['critical', 'waiting', 'active', 'idle']

  const CARD_GAP = 4, PIN_WIDTH = 34, PIN_HEIGHT = 44, PIN_GAP = 28, PIN_HEAD = 30
  // Where each pin is drawn from left to right. Two offices close together on the map would put one pin right on top of
  // the other, and a click would always reach the top one. Pins whose round heads meet are moved apart sideways, by the
  // same amount each, until their centres are `gap` apart; a pin with no neighbour stays exactly on its place.
  // `lean` is how far a pin was moved last time: it keeps two pins on their sides while they pass each other.
  // Mỗi ghim được vẽ ở đâu theo chiều ngang. Hai văn phòng gần nhau trên bản đồ sẽ khiến ghim này nằm đúng lên ghim kia,
  // và cú bấm luôn trúng ghim nằm trên. Các ghim có phần đầu tròn chạm nhau được tách sang hai bên, mỗi ghim một lượng
  // bằng nhau, tới khi tâm cách nhau `gap`; ghim không có hàng xóm thì đứng đúng chỗ của nó.
  // `lean` là độ lệch của ghim ở lần trước: nó giữ hai ghim ở đúng bên của mình khi chúng đi ngang qua nhau.
  function spreadPins(points, w, gap = PIN_GAP) {
    const x = points.map(p => p.sx)
    const key = i => points[i].sx + Math.max(-6, Math.min(6, points[i].lean || 0))
    const order = points.map((_, i) => i).sort((a, b) => key(a) - key(b) || a - b)
    for (let pass = 0, moved = true; moved && pass < 12; pass++) {
      moved = false
      for (let k = 0; k < order.length; k++) {
        for (let m = k + 1; m < order.length; m++) {
          const a = order[k], b = order[m]
          if (Math.abs(points[a].sy - points[b].sy) >= PIN_HEAD) continue
          const short = gap - (x[b] - x[a])
          if (short > .01) { x[a] -= short / 2; x[b] += short / 2; moved = true }
        }
      }
    }
    return x.map(v => Math.max(PIN_WIDTH / 2, Math.min(v, w - PIN_WIDTH / 2)))
  }
  const overlaps = (x0, y0, width, height, o) => x0 < o.x0 + o.width + CARD_GAP && o.x0 < x0 + width + CARD_GAP && y0 < o.y0 + o.height + CARD_GAP && o.y0 < y0 + height + CARD_GAP
  // Where each office card goes, and which cards are shown at all. A card sits beside its own pin, to the right or the
  // left, and slides up or down until it touches nothing in `blocks`, no card placed before it and no other office's pin.
  // A card is shown only in a place like that, inside the w by h frame and within LABEL_REACH of its pin: with many
  // offices there is not room for every card, and one that would cover something or sit far from its pin is hidden
  // (its pin stays, and the pin still opens the office). Cards are placed in order of `rank` (lowest first: the offices
  // that need attention), then `size` (largest first), so those keep their card when room runs out.
  // The place nearest the pin wins, and the side used last time (`last`) wins a near tie, so a card does not jump between
  // sides while the map turns; a hidden card must fit a little better before it comes back, so it does not flicker.
  // Returns the cards with hidden and slot, and x0, y0 for the shown ones.
  // Mỗi thẻ văn phòng nằm ở đâu, và thẻ nào được hiện. Thẻ nằm cạnh ghim của chính nó, bên phải hoặc bên trái, và trượt
  // lên hay xuống tới khi không chạm thứ gì trong `blocks`, không chạm thẻ đã đặt trước và không chạm ghim văn phòng khác.
  // Thẻ chỉ được hiện ở một chỗ như thế, nằm trong khung w nhân h và cách ghim của nó không quá LABEL_REACH: khi nhiều
  // văn phòng thì không đủ chỗ cho mọi thẻ, và thẻ nào sẽ đè lên thứ khác hoặc nằm xa ghim thì bị ẩn
  // (ghim vẫn còn, và bấm ghim vẫn mở văn phòng đó). Thẻ được đặt theo thứ tự `rank` (thấp trước: các văn phòng
  // cần chú ý), rồi `size` (lớn trước), để những nơi đó giữ được thẻ khi hết chỗ.
  // Chỗ gần ghim nhất được chọn, và bên đã dùng lần trước (`last`) thắng khi gần ngang nhau, để thẻ không nhảy qua lại
  // giữa hai bên khi bản đồ xoay; thẻ đang ẩn phải vừa chỗ hơn một chút mới hiện lại, để nó không chớp tắt.
  // Trả về các thẻ kèm hidden và slot, cùng x0, y0 cho thẻ được hiện.
  const LABEL_REACH = 110
  function layoutCards(cards, blocks, w, h) {
    const placed = []
    const pinOf = c => ({ x0: c.sx - PIN_WIDTH / 2, y0: c.sy - PIN_HEIGHT, width: PIN_WIDTH, height: PIN_HEIGHT })
    const order = cards.slice().sort((a, b) => (a.rank || 0) - (b.rank || 0) || (b.size || 0) - (a.size || 0) || b.sy - a.sy)
    for (const c of order) {
      const inTheWay = blocks.concat(placed, cards.filter(o => o !== c).map(pinOf))
      const home = c.sy - 42
      // a pin at the top or bottom edge has its level spot outside the frame: the search starts from the nearest spot inside
      // ghim sát mép trên hoặc mép dưới thì chỗ ngang ghim nằm ngoài khung: việc tìm chỗ bắt đầu từ chỗ gần nhất bên trong
      const start = Math.max(CARD_GAP, Math.min(home, Math.max(CARD_GAP, h - CARD_GAP - c.height)))
      const reach = LABEL_REACH + (c.last === 'hidden' ? -15 : c.last ? 15 : 0)
      let best = null
      for (const side of ['right', 'left']) {
        const x0 = side === 'right' ? c.sx + 19 : c.sx - 19 - c.width
        // a card that does not fit beside its pin on this side would have to cover the pin: not a place
        // thẻ không nằm vừa cạnh ghim ở bên này thì sẽ phải đè lên ghim: không tính là một chỗ
        if (x0 < CARD_GAP || x0 + c.width > w - 6) continue
        for (const way of ['up', 'down']) {
          let y0 = start, moved = true
          for (let pass = 0; moved && pass < 24; pass++) {
            moved = false
            for (const o of inTheWay) if (overlaps(x0, y0, c.width, c.height, o)) { y0 = way === 'up' ? o.y0 - c.height - CARD_GAP : o.y0 + o.height + CARD_GAP; moved = true }
          }
          if (moved || y0 < CARD_GAP || y0 + c.height > h - CARD_GAP || Math.abs(y0 - start) > reach) continue
          const slot = side + '-' + way
          const cost = Math.abs(y0 - home) + (side === 'left' ? 2 : 0) - (slot === c.last ? 14 : 0)
          if (!best || cost < best.cost) best = { x0, y0, slot, cost }
        }
      }
      if (!best) { Object.assign(c, { hidden: true, slot: 'hidden' }); continue }
      placed.push({ x0: best.x0, y0: best.y0, width: c.width, height: c.height })
      Object.assign(c, { hidden: false, x0: best.x0, y0: best.y0, slot: best.slot })
    }
    return cards
  }

  // pins, cards and the text layer over the map
  // ghim, thẻ và lớp chữ phủ trên bản đồ
  function createPinLayer(host, api) {
    const cls = document.createElement('div')
    cls.className = 'bd-text'
    host.append(cls)
    const pins = new Map()
    let list = []
    const HOME_SHAPE = '<path d="M17 9l8 7h-2.2v7.5h-4v-5h-3.6v5h-4V16H9z" fill="var(--m)"/>'
    const HQ_SHAPE = '<path d="M11 24V10h8v5h4v9h-4v-3h-2v3zm2-11h2v-1h-2zm0 3h2v-1h-2zm0 3h2v-1h-2zm4-6h1v-1h-1zm0 3h1v-1h-1z" fill="var(--m)" fill-rule="evenodd"/>'
    function syncPins(group, add, remove, update) {
      const inGroup = new Set(group.map(n => n.b.id))
      for (const [id, r] of pins) {
        if (inGroup.has(id)) continue
        r.pin.remove(); r.e.remove(); remove(r); pins.delete(id)
      }
      list = group.map(n => {
        let r = pins.get(n.b.id)
        if (!r) {
          const pin = document.createElement('div'), e = document.createElement('div')
          pin.style.opacity = 0; e.style.opacity = 0
          pin.setAttribute('role', 'button'); pin.tabIndex = 0
          e.innerHTML = '<b></b><small></small><div class="ai-tag"></div>'
          cls.append(pin, e)
          r = { id: n.b.id, pin, e, sx: 0, sy: 0, hidden: false }
          pins.set(n.b.id, r)
          for (const el of [pin, e]) {
            el.addEventListener('click', () => api.selected(r.id))
            el.addEventListener('keydown', ev => { if (ev.key === 'Enter') api.selected(r.id) })
          }
          if (api.hud) api.hud.attach(r)
          r.n = n
          add(r)
        }
        r.n = n
        const pinCls = pinClass(n)
        r.pin.className = 'bd-ghim ' + pinCls
        r.e.className = 'bd-card ' + pinCls
        const kind = n.b.isHq ? 'hq' : 'home'
        if (r.kind !== kind) {
          r.kind = kind
          r.pin.innerHTML = '<svg width="34" height="44" viewBox="0 0 34 44" aria-hidden="true"><path d="M17 1C8 1 1 8 1 17c0 11 16 26 16 26s16-15 16-26C33 8 26 1 17 1z" fill="var(--m)"/><circle cx="17" cy="17" r="11.5" fill="#fff"/>' + (n.b.isHq ? HQ_SHAPE : HOME_SHAPE) + '</svg>'
        }
        r.pin.setAttribute('aria-label', n.b.name)
        r.summary = summarize(n)
        r.e.children[0].textContent = n.b.name
        r.e.children[1].textContent = n.critical ? tx('⛔ {n} people near quota limit', { n: n.critical }) : tx('{working}/{total} working · {amount}', { working: n.working, total: n.members.length, amount: api.money(n.usd) })
        r.e.children[2].replaceChildren(...r.summary.members.map(t => { const i = document.createElement('i'); i.textContent = t; return i }))
        update(r)
        return r
      })
      if (api.hud) api.hud.refresh()
      return list
    }
    // pins stay in place; each card is put where it covers no other card, no other office's pin and not the branch list, or is hidden when no such place is left
    // ghim đứng đúng chỗ; mỗi thẻ được đặt ở chỗ không đè thẻ khác, không đè ghim của văn phòng khác và không đè danh sách chi nhánh, hoặc bị ẩn khi không còn chỗ như vậy
    function place(enabled, w) {
      // r.px is where the pin is drawn: its own place, moved sideways only when another pin sits on it
      // r.px là chỗ vẽ ghim: đúng chỗ của nó, chỉ lệch ngang khi có ghim khác nằm đè lên
      const front = list.filter(r => r.hidden)
      const drawn = spreadPins(front.map(r => ({ sx: r.sx, sy: r.sy, lean: r.lean })), w, enabled ? PIN_GAP : PIN_GAP * .62)
      front.forEach((r, i) => { r.px = drawn[i]; r.lean = drawn[i] - r.sx })
      for (const r of list) {
        if (!r.hidden) { r.px = r.sx; r.lean = 0 }
        r.pin.style.opacity = r.hidden ? 1 : 0
        r.pin.style.pointerEvents = r.hidden ? '' : 'none'
        r.pin.style.transform = `translate(${r.px}px,${r.sy}px)`
        r.pin.firstChild && (r.pin.firstChild.style.transform = enabled ? '' : 'scale(.62)')
        const show = r.hidden && enabled
        r.e.style.opacity = show ? 1 : 0
        r.e.style.pointerEvents = show ? '' : 'none'
      }
      const shown = list.filter(x => x.hidden && enabled)
      if (!shown.length) return
      const box = cls.getBoundingClientRect(), blocks = []
      // things that float over the map: the branch list in the corner on a wide screen, the buttons that pick the map
      // style and zoom, the column-height buttons of the tilted map. A card under one could not be read, and a card over
      // the buttons would take their clicks
      // những thứ nổi trên bản đồ: danh sách chi nhánh ở góc trên màn hình rộng, các nút chọn kiểu bản đồ và phóng to,
      // các nút chọn chiều cao cột của bản đồ nghiêng. Thẻ nằm dưới chúng thì không đọc được, còn thẻ nằm trên
      // các nút thì nhận mất cú bấm của nút
      const map = host.closest('.o-map')
      for (const el of map ? map.querySelectorAll('.o-bd-list, .o-bd-kind, .bd-metric') : []) {
        const l = el.getBoundingClientRect()
        if (l.width && l.height && l.left < box.right && l.right > box.left && l.top < box.bottom && l.bottom > box.top) blocks.push({ x0: l.left - box.left, y0: l.top - box.top, width: l.width, height: l.height })
      }
      const cards = shown.map(r => ({ r, sx: r.px, sy: r.sy, width: r.e.offsetWidth, height: r.e.offsetHeight, last: r.slot,
        rank: ATTENTION.indexOf(pinClass(r.n)), size: r.n.members.length }))
      for (const c of layoutCards(cards, blocks, w, box.height)) {
        c.r.slot = c.slot
        if (c.hidden) { c.r.e.style.opacity = 0; c.r.e.style.pointerEvents = 'none' } else c.r.e.style.transform = `translate(${c.x0}px,${c.y0}px)`
      }
    }
    return { cls, syncPins, place, list: () => list, fetchFn: id => pins.get(id) }
  }

  // HUD panel when the mouse hovers over a pin or card; the wall display does not have it
  // bảng HUD khi rê chuột vào ghim hoặc thẻ; màn hình treo tường không có
  function createHud(host, api) {
    const hud = document.createElement('div')
    hud.className = 'bd-hud'
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
    svg.setAttribute('class', 'bd-link')
    svg.innerHTML = '<polyline fill="none" stroke="#6be6ff" stroke-width="1.3" opacity="0"/><circle r="3" fill="#fff" opacity="0"/>'
    host.append(svg, hud)
    const linePoly = svg.firstChild, lineDot = svg.lastChild
    let current = null, hideTimer = 0
    const ringChart = (label, pct) => {
      const color = pct >= 80 ? '#ff6b6b' : pct >= 60 ? '#ffbd4a' : '#6be6ff', C = 2 * Math.PI * 18
      return `<svg viewBox="0 0 44 44"><circle cx="22" cy="22" r="18" fill="none" stroke="rgba(107,230,255,.16)" stroke-width="4"/><circle cx="22" cy="22" r="18" fill="none" stroke="${color}" stroke-width="4" stroke-dasharray="${(Math.min(100, pct) / 100) * C} ${C}" transform="rotate(-90 22 22)"/><text x="22" y="23" text-anchor="middle" fill="#fff" font-size="10.5" font-weight="700" font-family="monospace">${pct}%</text><text x="22" y="32" text-anchor="middle" fill="#8fdcf0" font-size="7" font-family="monospace">${label}</text></svg>`
    }
    function draw() {
      const r = current
      if (!r) return
      const n = r.n, t = r.summary, height = Math.max(...t.hours, 1e-9), maxTasks = Math.max(1, ...t.tasks.map(v => v[1]))
      hud.innerHTML = `<span class="stripe"></span><h3></h3><div class="sub"></div><div class="trio"><div><small>${tx('WORKING')}</small><b></b></div><div><small>${tx('TODAY')}</small><b></b></div><div><small>${tx('7 DAYS')}</small><b></b></div></div><div class="caption">${tx('Cost over 24 hours')}</div><div class="bars24">${t.hours.map(g => `<i style="height:${Math.max(2, (g / height) * 100)}%"></i>`).join('')}</div><div class="two-col"><div class="rings">${ringChart(tx('5 HOURS'), t.h5)}${ringChart(tx('7 DAYS'), t.h7)}</div><div class="ai-block"><div class="caption">${tx('Tasks given today')}</div>${t.tasks.map(v => `<div><small></small><span><i style="width:${(v[1] / maxTasks) * 100}%"></i></span><b>${v[1]}</b></div>`).join('')}</div></div><div class="list"></div>`
      hud.querySelector('h3').textContent = n.b.name
      hud.querySelector('.sub').textContent = `${n.b.isHq ? tx('Headquarters') : tx('Branch')} · ${countPeople(n.members.length)}`
      const count = hud.querySelectorAll('.trio b')
      count[0].textContent = `${n.working}/${n.members.length}`; count[1].textContent = api.money(n.usd); count[2].textContent = api.money(t.usd7d)
      hud.querySelectorAll('.ai-block > div small').forEach((e, i) => (e.textContent = t.tasks[i][0]))
      const list = hud.querySelector('.list')
      for (const p of n.members.slice(0, 8)) {
        const d = document.createElement('div'), a = document.createElement('span'), b = document.createElement('small')
        a.textContent = p.name; a.style.setProperty('--c', api.TT[p.status].color); b.textContent = api.TT[p.status].name
        d.append(a, b); list.append(d)
      }
      if (n.members.length > 8) list.append(tx('… and {n} more', { n: n.members.length - 8 }))
    }
    // put the panel on the side with room, never overflowing the frame; the link line follows the pin
    // đặt bảng về phía còn chỗ, không tràn khung; đường nối chạy theo ghim
    function place() {
      const r = current
      if (!r) return
      const px = r.px === undefined ? r.sx : r.px
      const w = host.clientWidth, h = host.clientHeight, hudWidth = hud.offsetWidth, hudHeight = hud.offsetHeight, onRight = px + 250 + hudWidth < w - 8
      const hx = onRight ? px + 250 : Math.max(8, px - 60 - hudWidth), hudY = Math.max(8, Math.min(h - hudHeight - 8, r.sy - hudHeight / 2 - 34))
      hud.style.transform = `translate(${hx}px,${hudY}px)`
      const startX = onRight ? hx : hx + hudWidth, y = hudY + 30, gx = startX + (onRight ? -26 : 26), pinY = r.sy - 30
      linePoly.setAttribute('points', `${px},${pinY} ${gx},${y} ${startX},${y}`); linePoly.setAttribute('opacity', 1)
      lineDot.setAttribute('cx', px); lineDot.setAttribute('cy', pinY); lineDot.setAttribute('opacity', 1)
    }
    const lines = () => {
      hideTimer = setTimeout(() => { current = null; hud.classList.remove('open'); linePoly.setAttribute('opacity', 0); lineDot.setAttribute('opacity', 0) }, 350)
    }
    const open = r => { clearTimeout(hideTimer); current = r; draw(); hud.classList.add('open'); place() }
    hud.addEventListener('pointerenter', () => clearTimeout(hideTimer))
    hud.addEventListener('pointerleave', lines)
    return {
      attach(r) { for (const el of [r.pin, r.e]) { el.addEventListener('pointerenter', e => { if (e.pointerType !== 'touch') open(r) }); el.addEventListener('pointerleave', lines) } },
      open, place, viewing: () => current,
      refresh() { if (current) draw() },
      hide() { clearTimeout(hideTimer); current = null; hud.classList.remove('open'); linePoly.setAttribute('opacity', 0); lineDot.setAttribute('opacity', 0) },
    }
  }

  // dark starry background, shared by 2.5D and 3D
  // nền tối có sao, dùng chung cho 2.5D và 3D
  function starBackdrop(T, centerY) {
    const n = document.createElement('canvas')
    n.width = 1024; n.height = 640
    const b = n.getContext('2d'), v = b.createRadialGradient(512, centerY, 0, 512, centerY, 650)
    v.addColorStop(0, '#07305e'); v.addColorStop(.48, '#031a3a'); v.addColorStop(1, '#010713')
    b.fillStyle = v; b.fillRect(0, 0, 1024, 640)
    let x = 11
    const r = () => (x = (x * 16807) % 2147483647) / 2147483647
    for (let i = 0; i < 110; i++) { b.fillStyle = `rgba(160,235,255,${.2 + r() * .7})`; b.fillRect(r() * 1024, r() * 640, 1.4, 1.4) }
    const texture = new T.CanvasTexture(n)
    texture.colorSpace = T.SRGBColorSpace
    return texture
  }

  // fixed base: sweeping radar face, HUD rings turning in opposite directions, spreading waves, rising particles
  // đáy cố định: mặt radar quét, vòng HUD xoay ngược chiều, sóng lan, hạt bay lên
  function createBeam(T, U, ren, BLEND, burst) {
    const beam = new T.Group()
    const rings = [], spinners = []
    if (burst) {
      const material = new T.ShaderMaterial({ ...BLEND, side: T.DoubleSide, uniforms: U,
        vertexShader: 'varying float h; void main(){ h = uv.y; gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.); }',
        fragmentShader: 'uniform float t; uniform float away; varying float h; void main(){ float n = .9+.1*sin(t*11.)*sin(t*3.7); gl_FragColor = vec4(vec3(.2,.72,1.)*(1.-h)*.15*n*away,1.); }' })
      beam.add(new T.Mesh(new T.CylinderGeometry(0.78, 0.42, 0.42, 72, 1, true).translate(0, 0.21, 0), material))
    }
    beam.add(new T.Mesh(new T.CircleGeometry(1.12, 128).rotateX(-Math.PI / 2), new T.ShaderMaterial({ ...BLEND, side: T.DoubleSide, uniforms: U,
      vertexShader: 'varying vec2 p; void main(){ p = position.xz / 1.12; gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.); }',
      fragmentShader: `uniform float t; uniform float away; varying vec2 p;
        void main(){ float r = length(p), a = atan(p.y,p.x);
          float luoi = smoothstep(.86,1.,sin(r*54.))*.14 + smoothstep(.985,1.,abs(cos(a*18.)))*.18*smoothstep(.34,.5,r);
          float q = fract((a - t*1.1)/6.28318); float quet = pow(q,11.)*.42 + smoothstep(.994,1.,q)*.5;
          float loi = smoothstep(.42,.0,r)*(.34+.1*sin(t*3.));
          gl_FragColor = vec4(vec3(.16,.72,1.)*((luoi+quet)*smoothstep(1.,.86,r)*smoothstep(.2,.4,r) + loi)*away,1.); }` })))
    const arcRing = (r, day, pins, speed, open) => {
      const n = new T.Group()
      n.userData.speed = speed
      for (const [d, len] of pins) {
        const m = new T.Mesh(new T.RingGeometry(r - day, r, 96, 1, d, len).rotateX(-Math.PI / 2), new T.MeshBasicMaterial({ color: 0x8cf0ff, opacity: open, side: T.DoubleSide, ...BLEND }))
        m.userData.open = open; n.add(m); rings.push(m)
      }
      beam.add(n); spinners.push(n)
    }
    arcRing(0.5, 0.014, [[0, 1.1], [2.1, 1.1], [4.2, 1.1]], 0.7, 0.9)
    arcRing(0.67, 0.005, Array.from({ length: 48 }, (_, i) => [(i * Math.PI) / 24, 0.05]), -0.25, 0.8)
    arcRing(0.86, 0.01, [[0.3, 0.5], [1.4, 1.6], [3.8, 0.35], [4.5, 1.2]], 0.4, 0.65)
    arcRing(1.06, 0.004, Array.from({ length: 24 }, (_, i) => [(i * Math.PI) / 12, 0.14]), -0.12, 0.45)
    for (const [r, open] of [[0.42, 1], [0.58, .7], [0.76, .4], [0.98, .22]]) {
      const v = new T.Mesh(new T.RingGeometry(r - 0.005, r, 128).rotateX(-Math.PI / 2), new T.MeshBasicMaterial({ color: 0x69e4ff, opacity: open, side: T.DoubleSide, ...BLEND }))
      v.userData.open = open; beam.add(v); rings.push(v)
    }
    const song = [0, 1, 2].map(i => {
      const m = new T.Mesh(new T.RingGeometry(0.985, 1, 128).rotateX(-Math.PI / 2), new T.MeshBasicMaterial({ color: 0x8cf0ff, side: T.DoubleSide, ...BLEND }))
      m.userData.phase = i / 3; beam.add(m); return m
    })
    const n = LOW_POWER ? 60 : 170, phases = new Float32Array(n * 3)
    for (let i = 0; i < n; i++) phases.set([Math.random() * 6.283, 0.25 + Math.random() * 0.75, Math.random()], i * 3)
    const g = new T.BufferGeometry()
    g.setAttribute('position', new T.BufferAttribute(new Float32Array(n * 3), 3))
    g.setAttribute('ha', new T.BufferAttribute(phases, 3))
    const particles = new T.Points(g, new T.ShaderMaterial({ ...BLEND, uniforms: { ...U, pr: { value: ren.getPixelRatio() } },
      vertexShader: 'uniform float t; uniform float pr; attribute vec3 ha; varying float o; void main(){ float h = fract(ha.z + t*(.1+.1*ha.y)); float r = mix(.32,.82,h)*ha.y; float a = ha.x + t*.25; vec3 q = vec3(cos(a)*r, h*.72, sin(a)*r); o = sin(h*3.1416); gl_PointSize = (1.5+2.2*ha.y)*pr; gl_Position = projectionMatrix*modelViewMatrix*vec4(q,1.); }',
      fragmentShader: 'uniform float away; varying float o; void main(){ float d = length(gl_PointCoord-.5); if(d>.5) discard; gl_FragColor = vec4(vec3(.55,.92,1.)*o*(1.-d*2.)*away,1.); }' }))
    particles.frustumCulled = false
    beam.add(particles)
    return {
      beam,
      update(t, hide) {
        beam.visible = hide < .98
        for (const m of rings) m.material.opacity = m.userData.open * (1 - hide)
        for (const m of spinners) m.rotation.y = t * m.userData.speed
        for (const m of song) { const q = (t * .28 + m.userData.phase) % 1; m.scale.setScalar(.42 + q * .95); m.material.opacity = (1 - q) * .75 * (1 - hide) }
      },
    }
  }

  // if below 20 frames per second for a few seconds, lower the resolution to reduce lag
  // dưới 20 khung/giây trong vài giây thì giảm độ phân giải cho đỡ giật
  function loadGovernor(ren) {
    let n = 0, t0 = performance.now(), badFrames = 0, placed = false
    return () => {
      if (placed) return
      n++
      const now = performance.now()
      if (now - t0 < 2000) return
      if (document.visibilityState === 'visible') badFrames = (n * 1000) / (now - t0) < 20 ? badFrames + 1 : 0
      n = 0; t0 = now
      if (badFrames >= 2) { placed = true; ren.setPixelRatio(1) }
    }
  }

  window.MapCommon = { VN_ISLANDS, insideVN, loadJson, LOW_POWER, REDUCED_MOTION, forEachRing, layoutCards, spreadPins, createPinLayer, createHud, starBackdrop, createBeam, loadGovernor }
})()
