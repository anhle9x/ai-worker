// 2.5D style of the branch map: a floating sand table. The glass plate rotates, the radar base stays still, light columns compare the branches.
// Kiểu 2.5D của bản đồ chi nhánh: sa bàn nổi. Tấm kính xoay được, đáy radar đứng yên, cột sáng để so sánh các chi nhánh.
;(function () {
  'use strict'
  const LON0 = 108.6, LAT0 = 15.2, HALF = 11.2
  const X = len => len - LON0, Z = p => LAT0 - p
  function create(host, api) {
    const C = window.MapCommon, T = window.THREE
    api = { ...api, hud: api.wall ? null : C.createHud(host, api) }
    const ren = new T.WebGLRenderer({ antialias: true })
    ren.setPixelRatio(C.LOW_POWER ? 1 : Math.min(2, devicePixelRatio || 1))
    const cv = ren.domElement
    cv.className = 'bd-canvas'
    host.append(cv)
    const scene = new T.Scene(), cam = new T.PerspectiveCamera(36, 1, .1, 200)
    scene.background = C.starBackdrop(T, 340)
    const BLEND = { blending: T.AdditiveBlending, transparent: true, depthWrite: false }
    const U = { t: { value: 0 }, away: { value: 1 } }
    const day = C.createBeam(T, U, ren, BLEND, false)
    day.beam.position.y = -7.6; day.beam.scale.setScalar(7.2)
    scene.add(day.beam)

    const pivot = new T.Group()
    scene.add(pivot)
    const boxGeo = new T.BoxGeometry(HALF * 2, .1, HALF * 2)
    const glass = new T.Mesh(boxGeo, new T.ShaderMaterial({ ...BLEND, uniforms: U,
      vertexShader: 'varying vec3 p; void main(){ p = position; gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.); }',
      fragmentShader: `uniform float t; varying vec3 p; void main(){ float m = max(abs(p.x),abs(p.z))/${HALF.toFixed(1)}; float c = .03 + smoothstep(.86,1.,m)*.12; float q = smoothstep(.45,0.,abs(fract(p.z*.035+t*.05)-.5)-.47)*.03; gl_FragColor = vec4(vec3(.15,.6,1.)*(c+q),1.); }` }))
    glass.position.y = -.06
    const edge = new T.LineSegments(new T.EdgesGeometry(boxGeo), new T.LineBasicMaterial({ color: 0x7feeff, ...BLEND, opacity: .8 }))
    edge.position.y = -.06
    pivot.add(glass, edge)
    for (const [sx, sz] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) {
      const p = [[0, 1.8], [0, 0], [1.8, 0]].map(([a, c]) => new T.Vector3(sx * (HALF + .22 - a), .02, sz * (HALF + .22 - c)))
      pivot.add(new T.Line(new T.BufferGeometry().setFromPoints(p), new T.LineBasicMaterial({ color: 0xc8f8ff, ...BLEND })))
    }
    C.loadJson('land.json').then(land => {
      const W2 = C.LOW_POWER ? 1400 : 2200, c0 = document.createElement('canvas')
      c0.width = c0.height = W2
      const c = c0.getContext('2d', { willReadFrequently: true })
      c.fillStyle = '#fff'
      const LON_MIN = LON0 - HALF, LON_MAX = LON0 + HALF, LAT_MIN = LAT0 - HALF, LAT_MAX = LAT0 + HALF, mx = len => ((len - LON_MIN) / (LON_MAX - LON_MIN)) * W2, my = p => ((LAT_MAX - p) / (LAT_MAX - LAT_MIN)) * W2, borderPts = []
      const inside = (a, b) => a > LON_MIN + .15 && a < LON_MAX - .15 && b > LAT_MIN + .15 && b < LAT_MAX - .15
      C.forEachRing(land, poly => {
        c.beginPath()
        for (const r of poly) r.forEach(([a, b], i) => (i ? c.lineTo(mx(a), my(b)) : c.moveTo(mx(a), my(b))))
        c.fill('evenodd')
        for (const r of poly) for (let i = 1; i < r.length; i++) if (inside(...r[i - 1]) && inside(...r[i])) borderPts.push(X(r[i - 1][0]), .012, Z(r[i - 1][1]), X(r[i][0]), .012, Z(r[i][1]))
      })
      const px = c.getImageData(0, 0, W2, W2).data, pos = [], k = [], step = C.LOW_POWER ? .2 : .13
      for (let lat = LAT_MIN + .2; lat < LAT_MAX - .2; lat += step) for (let lon = LON_MIN + .2; lon < LON_MAX - .2; lon += step) if (px[(Math.floor(my(lat)) * W2 + Math.floor(mx(lon))) * 4 + 3] > 128) { pos.push(X(lon), .01, Z(lat)); k.push(C.insideVN(lon, lat) ? 1 : .3) }
      const g = new T.BufferGeometry()
      g.setAttribute('position', new T.Float32BufferAttribute(pos, 3)); g.setAttribute('k', new T.Float32BufferAttribute(k, 1))
      pivot.add(new T.Points(g, new T.ShaderMaterial({ ...BLEND, uniforms: { pr: { value: ren.getPixelRatio() } },
        vertexShader: 'attribute float k; varying float m; uniform float pr; void main(){ m = k; vec4 mv = modelViewMatrix*vec4(position,1.); gl_PointSize = pr*(k>.7?1.9:1.3)*clamp(30./-mv.z,.8,1.8); gl_Position = projectionMatrix*mv; }',
        fragmentShader: 'varying float m; void main(){ gl_FragColor = vec4(vec3(.25,.75,1.)*m,1.); }' })))
      const borderGeo = new T.BufferGeometry()
      borderGeo.setAttribute('position', new T.Float32BufferAttribute(borderPts, 3))
      pivot.add(new T.LineSegments(borderGeo, new T.LineBasicMaterial({ color: 0x8cf0ff, ...BLEND, opacity: .62 })))
    }).catch(() => {})
    const pin = C.createPinLayer(host, api)
    const islandLabels = [], islandPts = []
    for (const [name, islands, labelLon, labelLat] of C.VN_ISLANDS) {
      for (const [len, p] of islands) islandPts.push(X(len), .03, Z(p))
      const e = document.createElement('div')
      e.className = 'bd-island'; e.textContent = name; e.style.opacity = 0
      pin.cls.append(e)
      islandLabels.push({ e, p: new T.Vector3(X(labelLon), .05, Z(labelLat)) })
    }
    const islandGeo = new T.BufferGeometry()
    islandGeo.setAttribute('position', new T.Float32BufferAttribute(islandPts, 3))
    pivot.add(new T.Points(islandGeo, new T.PointsMaterial({ color: 0xbdf6ff, size: .13, ...BLEND })))

    // buttons that change the column height
    // nút đổi chiều cao cột
    let heightMetric = 'usd'
    const metricBox = document.createElement('div')
    metricBox.className = 'bd-metric'
    metricBox.append(tx('Column height') + ': ')
    for (const [m, name] of [['usd', tx('Cost')], ['nguoi', tx('People')], ['hm', tx('Quota')]]) {
      const b = document.createElement('button')
      b.type = 'button'; b.textContent = name
      b.className = m === heightMetric ? 'on' : ''
      b.setAttribute('aria-pressed', String(m === heightMetric))
      b.addEventListener('click', () => {
        heightMetric = m
        for (const n of metricBox.querySelectorAll('button')) { n.classList.toggle('on', n === b); n.setAttribute('aria-pressed', String(n === b)) }
      })
      metricBox.append(b)
    }
    if (!api.wall) host.append(metricBox)

    const columnGeo = new T.CylinderGeometry(.13, .17, 1, 28).translate(0, .5, 0)
    const haloGeo = new T.CylinderGeometry(.3, .38, 1, 28, 1, true).translate(0, .5, 0)
    const capGeo = new T.SphereGeometry(.17, 16, 12), ringGeo = new T.RingGeometry(.3, .38, 48).rotateX(-Math.PI / 2), particleGeo = new T.SphereGeometry(.07, 10, 10)
    const add = r => {
      r.group = new T.Group()
      r.column = new T.Mesh(columnGeo, new T.MeshBasicMaterial({ ...BLEND, opacity: .9 }))
      r.halo = new T.Mesh(haloGeo, new T.MeshBasicMaterial({ ...BLEND, opacity: .22, side: T.DoubleSide }))
      r.cap = new T.Mesh(capGeo, new T.MeshBasicMaterial({ color: 0xffffff, ...BLEND }))
      r.ring1 = new T.Mesh(ringGeo, new T.MeshBasicMaterial({ ...BLEND, side: T.DoubleSide }))
      r.ring2 = new T.Mesh(ringGeo, new T.MeshBasicMaterial({ ...BLEND, side: T.DoubleSide }))
      r.group.add(r.column, r.halo, r.cap, r.ring1, r.ring2)
      pivot.add(r.group)
      r.height = .2
      r.path = new T.Line(new T.BufferGeometry(), new T.LineBasicMaterial({ color: 0xaaf4ff, ...BLEND }))
      pivot.add(r.path)
      r.particles = [0, 1, 2].map(() => { const h = new T.Mesh(particleGeo, new T.MeshBasicMaterial({ color: 0xffffff, ...BLEND })); pivot.add(h); return h })
    }
    const removeOne = r => { pivot.remove(r.group, r.path, ...r.particles); r.path.geometry.dispose() }
    let pinList = [], toiDa = { usd: 1, people: 1 }
    function update(group) {
      toiDa = { usd: Math.max(...group.map(n => n.usd), 1e-9), people: Math.max(...group.map(n => n.members.length), 1) }
      pinList = pin.syncPins(group, add, removeOne, r => {
        const n = r.n, color = n.critical ? 0xff5560 : n.waiting ? 0xffbd4a : n.working ? 0x62e8ff : 0x7d98a8
        r.group.position.set(X(n.b.lon), .02, Z(n.b.lat))
        for (const m of [r.column, r.halo, r.ring1, r.ring2]) m.material.color.set(color)
      })
      const ts = pinList.find(r => r.n.b.isHq) || pinList[0]
      for (const r of pinList) {
        r.arcRing = null
        r.path.visible = false
        if (!ts || r === ts) continue
        const a = new T.Vector3(X(r.n.b.lon), .05, Z(r.n.b.lat)), b = new T.Vector3(X(ts.n.b.lon), .05, Z(ts.n.b.lat)), g = a.clone().lerp(b, .5)
        g.y += 1 + a.distanceTo(b) * .32
        r.arcRing = new T.QuadraticBezierCurve3(a, g, b)
        r.path.geometry.setFromPoints(r.arcRing.getPoints(60))
        r.path.visible = true
        r.path.material.color.set(r.n.critical ? 0xff8a8a : 0xaaf4ff)
        r.path.material.opacity = r.n.working + r.n.waiting ? .85 : .25
      }
    }
    const targetHeight = n => {
      if (heightMetric === 'hm') return .35 + 5.2 * Math.min(1, Math.max(0, ...n.members.flatMap(p => ((p.quota && p.quota.windows) || []).map(c => c.pct))) / 100)
      if (heightMetric === 'nguoi') return .35 + 5.2 * (n.members.length / toiDa.people)
      return .35 + 5.2 * Math.sqrt(n.usd / toiDa.usd)
    }

    // drag sideways to rotate the glass, drag up and down to change the tilt, scroll to zoom in
    // kéo ngang xoay tấm kính, kéo dọc đổi độ nghiêng, lăn chuột lại gần
    const HOME = { spin: -.14, tilt: .92, distance: 40, panX: 0, panZ: 0 }, v = { ...HOME }
    let flight = null, drag = null, from = 0
    const flyTo = (d, ms = 1500) => { flight = { from: { ...v }, d, t0: performance.now(), ms }; from = performance.now() }
    cv.addEventListener('pointerdown', e => { drag = { x: e.clientX, y: e.clientY, spin: v.spin, tilt: v.tilt }; flight = null; cv.setPointerCapture(e.pointerId) })
    cv.addEventListener('pointermove', e => { if (!drag) return; v.spin = drag.spin + (e.clientX - drag.x) * .005; v.tilt = Math.max(.45, Math.min(1.3, drag.tilt + (e.clientY - drag.y) * .004)); from = performance.now() })
    cv.addEventListener('pointerup', () => (drag = null))
    cv.addEventListener('pointercancel', () => (drag = null))
    cv.addEventListener('wheel', e => { e.preventDefault(); flight = null; v.distance = Math.max(7, Math.min(60, v.distance * (e.deltaY < 0 ? .88 : 1.13))); from = performance.now() }, { passive: false })
    cv.addEventListener('dblclick', () => flyTo(HOME))

    const target = new T.Vector3(), v3 = new T.Vector3(), governor = C.loadGovernor(ren)
    let visible = false, frameId = 0
    function draw(ms) {
      if (!visible) return
      frameId = requestAnimationFrame(draw)
      governor()
      const t = ms / 1000, w = host.clientWidth, h = host.clientHeight
      if (!w || !h) return
      if (cv.width !== Math.round(w * ren.getPixelRatio()) || cv.height !== Math.round(h * ren.getPixelRatio())) { ren.setSize(w, h, false); cam.aspect = w / h; cam.updateProjectionMatrix() }
      U.t.value = t
      if (flight) {
        const q = Math.min(1, (performance.now() - flight.t0) / flight.ms), e = q < .5 ? 4 * q * q * q : 1 - Math.pow(-2 * q + 2, 3) / 2
        for (const k of ['spin', 'tilt', 'distance', 'panX', 'panZ']) v[k] = flight.from[k] + (flight.d[k] - flight.from[k]) * e
        if (q >= 1) flight = null
      }
      const attach = Math.max(0, Math.min(1, (30 - v.distance) / 14))
      U.away.value = 1 - attach
      const current = api.hud && api.hud.viewing()
      pivot.rotation.y = v.spin + (C.REDUCED_MOTION || drag || current || performance.now() - from < 5000 ? 0 : Math.sin(t * .13) * .08)
      pivot.position.y = C.REDUCED_MOTION ? 0 : Math.sin(t * .7) * .1
      target.set(v.panX, 0, v.panZ).applyEuler(pivot.rotation)
      target.y = -3.2 * (1 - attach)
      cam.position.set(target.x, target.y + Math.sin(v.tilt) * v.distance, target.z + Math.cos(v.tilt) * v.distance)
      cam.lookAt(target)
      day.update(t, attach)
      pivot.updateMatrixWorld()
      for (const r of pinList) {
        const n = r.n
        r.height += (targetHeight(n) - r.height) * .09
        // when zoomed in the columns and dots shrink and get lower so they do not hide the map
        // nhìn gần thì cột và chấm nhỏ lại, thấp bớt để không che bản đồ
        const size = Math.min(1, .22 + v.distance / 34), scaleY = r.height * Math.min(1, .3 + v.distance / 40)
        r.column.scale.set(size, scaleY, size); r.halo.scale.set(size, scaleY, size); r.cap.scale.setScalar(size); r.cap.position.y = scaleY; r.ring1.scale.setScalar(size)
        const song = n.working + n.waiting + n.critical > 0, phase = (t * (n.critical ? 1.3 : .55) + n.b.lon) % 1
        r.ring2.scale.setScalar(size * (song ? 1 + phase * (n.critical ? 3 : 2) : 1)); r.ring2.material.opacity = song ? (1 - phase) * .9 : 0
        r.particles.forEach((x, i) => { x.visible = !!r.arcRing && n.working + n.waiting > 0; if (x.visible) x.position.copy(r.arcRing.getPoint((t * .22 + i / 3) % 1)) })
        v3.set(0, scaleY + .2 * size, 0); r.group.localToWorld(v3); v3.project(cam)
        r.sx = ((v3.x + 1) / 2) * w; r.sy = ((1 - v3.y) / 2) * h; r.hidden = v3.z < 1
      }
      pin.place(true, w)
      for (const d of islandLabels) { v3.copy(d.p); pivot.localToWorld(v3); v3.project(cam); d.e.style.opacity = 1; d.e.style.transform = `translate(-50%,-100%) translate(${((v3.x + 1) / 2) * w}px,${((1 - v3.y) / 2) * h}px)` }
      if (api.hud) api.hud.place()
      ren.render(scene, cam)
    }
    return {
      update,
      flyTo(id) { const r = pin.fetchFn(id); if (r) flyTo({ ...v, distance: 13, tilt: .8, panX: X(r.n.b.lon), panZ: Z(r.n.b.lat) }) },
      zoom(factor) { flyTo({ ...v, distance: Math.max(7, Math.min(60, v.distance / factor)) }, 300) },
      fit() { flyTo(HOME) },
      show(size) { visible = size; cancelAnimationFrame(frameId); if (size) frameId = requestAnimationFrame(draw); else if (api.hud) api.hud.hide() },
    }
  }
  window.Map25D = { create }
})()
