// 2D style of the branch map: a radar room. Drawn with canvas, needs no WebGL, so it is the fallback for weak machines.
// Kiểu 2D của bản đồ chi nhánh: phòng radar. Vẽ bằng canvas, không cần WebGL, nên là phương án dự phòng cho máy yếu.
;(function () {
  'use strict'
  function create(host, api) {
    const C = window.MapCommon
    api = { ...api, hud: api.wall ? null : C.createHud(host, api) }
    const cv = document.createElement('canvas'), g = cv.getContext('2d'), backdropLayer = document.createElement('canvas'), backCtx = backdropLayer.getContext('2d')
    cv.className = 'bd-canvas'
    host.append(cv)
    const pin = C.createPinLayer(host, api)
    let W = 0, H = 0, dpr = 1, landData = null, needsBackdrop = true
    const HOME = { lon: 108.2, lat: 15.8, s: 0 }, v = { ...HOME }
    const X = lon => W / 2 + (lon - v.lon) * v.s, Y = lat => H / 2 + (v.lat - lat) * v.s
    function fitCanvas() {
      W = host.clientWidth; H = host.clientHeight; dpr = C.LOW_POWER ? 1 : Math.min(2, devicePixelRatio || 1)
      for (const c of [cv, backdropLayer]) { c.width = W * dpr; c.height = H * dpr }
      const homeScale = HOME.s
      HOME.s = Math.max(4, Math.min(H / 20, W / 25))
      if (!v.s || v.s === homeScale) v.s = HOME.s
      needsBackdrop = true
    }
    function drawBackdrop() {
      needsBackdrop = false
      const b = backCtx
      b.setTransform(dpr, 0, 0, dpr, 0, 0)
      const bg = b.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, Math.max(W, H) * .72)
      bg.addColorStop(0, '#07305e'); bg.addColorStop(.55, '#03183a'); bg.addColorStop(1, '#010713')
      b.fillStyle = bg; b.fillRect(0, 0, W, H)
      b.font = '10px ui-monospace,Menlo,monospace'
      const step = v.s > HOME.s * 3 ? 1 : 2
      for (let lon = 90; lon <= 130; lon += step) { const x = X(lon); b.strokeStyle = 'rgba(94,214,232,.09)'; b.lineWidth = 1; b.beginPath(); b.moveTo(x, 0); b.lineTo(x, H); b.stroke(); b.fillStyle = 'rgba(143,220,240,.65)'; b.fillText(lon + '°E', x + 3, H - 6); b.fillRect(x, H - 4, 1, 4) }
      for (let lat = -2; lat <= 34; lat += step) { const y = Y(lat); b.strokeStyle = 'rgba(94,214,232,.09)'; b.beginPath(); b.moveTo(0, y); b.lineTo(W, y); b.stroke(); b.fillStyle = 'rgba(143,220,240,.65)'; b.fillText(lat + '°N', W - 40, y - 3); b.fillRect(W - 4, y, 4, 1) }
      if (!landData) return
      const attach = v.s > HOME.s * 2.2
      for (const [lon, lat, inVN] of attach ? landData.day : landData.pointOf) {
        const x = X(lon), y = Y(lat)
        if (x < -3 || y < -3 || x > W + 3 || y > H + 3) continue
        b.fillStyle = inVN ? 'rgba(110,218,255,.98)' : 'rgba(60,150,220,.5)'
        const c = attach ? (inVN ? 1.7 : 1.1) : Math.max(1, Math.min(3, (v.s / HOME.s) * (inVN ? 2.1 : 1.35)))
        b.fillRect(x - c / 2, y - c / 2, c, c)
      }
      b.strokeStyle = 'rgba(127,238,255,.62)'; b.lineWidth = 1; b.beginPath()
      for (const r of landData.keepPolys) r.forEach(([lon, lat], i) => { const x = X(lon), y = Y(lat); i ? b.lineTo(x, y) : b.moveTo(x, y) })
      b.stroke()
      // Hoang Sa and Truong Sa islands
      // Hoàng Sa, Trường Sa
      for (const [name, islands, labelLon, labelLat] of C.VN_ISLANDS) {
        b.fillStyle = '#bdf6ff'
        for (const [lon, lat] of islands) { b.beginPath(); b.arc(X(lon), Y(lat), 1.9, 0, 6.3); b.fill() }
        b.font = '11px ui-monospace,Menlo,monospace'; b.fillStyle = '#9fe6f7'; b.textAlign = 'center'; b.fillText(name, X(labelLon), Y(labelLat)); b.textAlign = 'left'
      }
    }
    C.loadJson('land.json').then(land => {
      const W2 = 2200, H2 = 2200, m = document.createElement('canvas')
      m.width = W2; m.height = H2
      const c = m.getContext('2d', { willReadFrequently: true })
      c.fillStyle = '#fff'
      const LON_MIN = 92, LON_MAX = 126, LAT_MIN = 0, LAT_MAX = 32, mx = l => ((l - LON_MIN) / (LON_MAX - LON_MIN)) * W2, my = p => ((LAT_MAX - p) / (LAT_MAX - LAT_MIN)) * H2, keepPolys = []
      C.forEachRing(land, poly => {
        c.beginPath()
        for (const r of poly) r.forEach(([a, b], i) => (i ? c.lineTo(mx(a), my(b)) : c.moveTo(mx(a), my(b))))
        c.fill('evenodd')
        for (const r of poly) if (r.some(([a, b]) => a > LON_MIN && a < LON_MAX && b > LAT_MIN && b < LAT_MAX)) keepPolys.push(r)
      })
      const px = c.getImageData(0, 0, W2, H2).data, isLand = (lon, lat) => px[(Math.floor(my(lat)) * W2 + Math.floor(mx(lon))) * 4 + 3] > 128
      const pointOf = [], day = []
      for (let lat = 1; lat < 31; lat += .14) for (let lon = 93; lon < 125; lon += .14) if (isLand(lon, lat)) pointOf.push([lon, lat, C.insideVN(lon, lat)])
      const step = C.LOW_POWER ? .09 : .045
      for (let lat = 6; lat < 25; lat += step) for (let lon = 100; lon < 118; lon += step) if (isLand(lon, lat)) day.push([lon, lat, C.insideVN(lon, lat)])
      landData = { pointOf, day, keepPolys }; needsBackdrop = true
    }).catch(() => {})

    let flight = null, drag = null, pinList = [], visible = false, frameId = 0, previous = 0
    const flyTo = (d, ms = 1200) => (flight = { from: { ...v }, d, t0: performance.now(), ms })
    const pointerPos = e => { const r = cv.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top] }
    cv.addEventListener('wheel', e => {
      e.preventDefault(); flight = null
      const [mx, my] = pointerPos(e), lon = v.lon + (mx - W / 2) / v.s, lat = v.lat - (my - H / 2) / v.s
      const s = Math.max(HOME.s * .8, Math.min(HOME.s * 14, v.s * (e.deltaY < 0 ? 1.18 : .85)))
      v.lon = lon - (mx - W / 2) / s; v.lat = lat + (my - H / 2) / s; v.s = s; needsBackdrop = true
    }, { passive: false })
    cv.addEventListener('pointerdown', e => { drag = { x: e.clientX, y: e.clientY, lon: v.lon, lat: v.lat }; flight = null; cv.setPointerCapture(e.pointerId) })
    cv.addEventListener('pointermove', e => { if (!drag) return; v.lon = drag.lon - (e.clientX - drag.x) / v.s; v.lat = drag.lat + (e.clientY - drag.y) / v.s; needsBackdrop = true })
    cv.addEventListener('pointerup', () => (drag = null))
    cv.addEventListener('pointercancel', () => (drag = null))
    cv.addEventListener('dblclick', () => flyTo(HOME))

    const SPEED = 0.8
    function draw(ms) {
      if (!visible) return
      frameId = requestAnimationFrame(draw)
      if (ms - previous < 30) return
      previous = ms
      const t = ms / 1000
      if (host.clientWidth !== W || host.clientHeight !== H) fitCanvas()
      if (!W || !H) return
      if (flight) {
        const q = Math.min(1, (performance.now() - flight.t0) / flight.ms), e = q < .5 ? 4 * q * q * q : 1 - Math.pow(-2 * q + 2, 3) / 2
        for (const k of ['lon', 'lat', 's']) v[k] = flight.from[k] + (flight.d[k] - flight.from[k]) * e
        needsBackdrop = true
        if (q >= 1) flight = null
      }
      if (needsBackdrop) drawBackdrop()
      g.setTransform(1, 0, 0, 1, 0, 0); g.drawImage(backdropLayer, 0, 0); g.setTransform(dpr, 0, 0, dpr, 0, 0)
      const ts = pinList.find(r => r.n.b.isHq) || pinList[0]
      const cx = ts ? X(ts.n.b.lon) : X(HOME.lon), cy = ts ? Y(ts.n.b.lat) : Y(HOME.lat), R = Math.hypot(W, H) * 1.3, angle = C.REDUCED_MOTION ? -1 : (t * SPEED) % 6.28319
      g.strokeStyle = 'rgba(107,230,255,.17)'; g.lineWidth = 1
      for (let i = 1; i < 9; i++) { g.beginPath(); g.arc(cx, cy, i * v.s * 3, 0, 6.3); g.stroke() }
      const sweep = g.createConicGradient(angle - 1.15, cx, cy)
      sweep.addColorStop(0, 'rgba(70,215,255,0)'); sweep.addColorStop(1.15 / 6.28319, 'rgba(70,215,255,.2)'); sweep.addColorStop(1.1501 / 6.28319, 'rgba(70,215,255,0)'); sweep.addColorStop(1, 'rgba(70,215,255,0)')
      g.fillStyle = sweep; g.beginPath(); g.moveTo(cx, cy); g.arc(cx, cy, R, angle - 1.15, angle); g.closePath(); g.fill()
      g.strokeStyle = 'rgba(190,248,255,.85)'; g.lineWidth = 1.4; g.beginPath(); g.moveTo(cx, cy); g.lineTo(cx + Math.cos(angle) * R, cy + Math.sin(angle) * R); g.stroke()
      for (const r of pinList) {
        const n = r.n, x = X(n.b.lon), y = Y(n.b.lat)
        r.sx = x; r.sy = y; r.hidden = x > -40 && y > -10 && x < W + 40 && y < H + 50
        const working = n.working + n.waiting > 0, isCritical = n.critical > 0
        if (r !== ts) {
          g.strokeStyle = working ? 'rgba(143,240,255,.75)' : 'rgba(143,240,255,.22)'; g.lineWidth = 1.3
          g.setLineDash(working ? [] : [3, 5]); g.beginPath(); g.moveTo(x, y); g.lineTo(cx, cy); g.stroke(); g.setLineDash([])
          if (working) for (let i = 0; i < 2; i++) {
            const q = (t * .25 + i / 2) % 1
            g.fillStyle = '#fff'; g.shadowColor = '#6be6ff'; g.shadowBlur = 10; g.beginPath(); g.arc(x + (cx - x) * q, y + (cy - y) * q, 2.3, 0, 6.3); g.fill(); g.shadowBlur = 0
          }
        }
        const color = isCritical ? '255,85,96' : working ? '107,230,255' : '140,165,180', phase = (t * (isCritical ? 1.5 : .6) + n.b.lon) % 1
        g.strokeStyle = `rgba(${color},.9)`; g.lineWidth = 1.5; g.beginPath(); g.arc(x, y, 9, 0, 6.3); g.stroke()
        if (working || isCritical) { g.strokeStyle = `rgba(${color},${(1 - phase) * .8})`; g.beginPath(); g.arc(x, y, 9 + phase * (isCritical ? 34 : 22), 0, 6.3); g.stroke() }
        // when the radar sweep passes over a pin, the pin lights up
        // vệt radar quét qua thì ghim sáng lên
        let offset = (Math.atan2(y - cy, x - cx) - angle) % 6.28319
        if (offset < 0) offset += 6.28319
        r.pin.classList.toggle('scan', !isCritical && r !== ts && offset > 5.75)
      }
      pin.place(true, W)
      if (api.hud) api.hud.place()
    }
    return {
      update(group) { pinList = pin.syncPins(group, () => {}, () => {}, () => {}) },
      flyTo(id) { const r = pin.fetchFn(id); if (r) flyTo({ lon: r.n.b.lon, lat: r.n.b.lat, s: HOME.s * 5 }) },
      zoom(factor) { flyTo({ ...v, s: Math.max(HOME.s * .8, Math.min(HOME.s * 14, v.s * factor)) }, 300) },
      fit() { flyTo(HOME) },
      // the argument must not carry the name of the flag it sets: it hid the flag, nothing was set and the map stayed blank
      // tham số không được trùng tên với cờ nó gán: nó che mất cờ, không gì được gán và bản đồ cứ trống
      show(on) { visible = on; cancelAnimationFrame(frameId); if (on) { needsBackdrop = true; frameId = requestAnimationFrame(draw) } },
    }
  }
  window.Map2D = { create }
})()
