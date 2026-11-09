// 3D style of the branch map: a hologram globe. The base and orbit rings stay still, only the globe turns.
// Click a pin to fly to the branch; drag to rotate, scroll to zoom in, double-click to return to the full view.
// Kiểu 3D của bản đồ chi nhánh: địa cầu hologram. Đáy và vòng quỹ đạo đứng yên, chỉ quả cầu quay.
// Bấm ghim thì bay tới chi nhánh; kéo để xoay, lăn chuột để lại gần, bấm đúp về toàn cảnh.
;(function () {
  'use strict'
  function create(host, api) {
    const C = window.MapCommon, T = window.THREE
    api = { ...api, hud: api.wall ? null : C.createHud(host, api) }
    const ren = new T.WebGLRenderer({ antialias: true })
    ren.setPixelRatio(C.LOW_POWER ? 1 : Math.min(2, devicePixelRatio || 1))
    const cv = ren.domElement
    cv.className = 'bd-canvas'
    host.append(cv)
    const scene = new T.Scene(), cam = new T.PerspectiveCamera(35, 1, .01, 60)
    scene.background = C.starBackdrop(T, 300)
    const toVec = (lon, lat, r = 1) => {
      const a = (lon * Math.PI) / 180, b = (lat * Math.PI) / 180
      return new T.Vector3(Math.cos(b) * Math.sin(a) * r, Math.sin(b) * r, Math.cos(b) * Math.cos(a) * r)
    }
    const U = { t: { value: 0 }, away: { value: 1 } }
    const BLEND = { blending: T.AdditiveBlending, transparent: true, depthWrite: false }
    const VERT = `uniform float size; attribute float k; varying float a; varying float m; varying float y;
      void main(){ vec4 mv = modelViewMatrix * vec4(position,1.); vec3 n = normalize(normalMatrix * position); vec3 v = normalize(-mv.xyz);
        a = smoothstep(-.3,.28,dot(n,v)); m = k; y = normalize(position).y;
        gl_PointSize = size * (1.1 + min(2.6/(-mv.z), 1.1)); gl_Position = projectionMatrix * mv; }`
    const FRAG = `uniform float t; uniform float away; uniform vec3 color; uniform float bright; varying float a; varying float m; varying float y;
      void main(){ float mat = max(.2*away, .03); float s = .78 + .22*sin(y*90.-t*2.4);
        float sweep = smoothstep(.035,0.,abs(y-sin(t*.45)))*1.6*away;
        float o = mix(mat,1.,a)*s + sweep*a;
    #ifdef POINTS
        float d = length(gl_PointCoord-.5); if(d>.5) discard; o *= 1.-smoothstep(.15,.5,d);
    #endif
        gl_FragColor = vec4(color*bright*m*o,1.); }`
    const makeMaterial = (isPoints, color, bright, size = 2) => new T.ShaderMaterial({ ...BLEND, defines: isPoints ? { POINTS: 1 } : {}, uniforms: { ...U, color: { value: new T.Color(color) }, bright: { value: bright }, size: { value: size * ren.getPixelRatio() } }, vertexShader: VERT, fragmentShader: FRAG })
    const toLines = (array, k) => {
      const g = new T.BufferGeometry()
      g.setAttribute('position', new T.Float32BufferAttribute(array, 3))
      g.setAttribute('k', k ? new T.Float32BufferAttribute(k, 1) : new T.BufferAttribute(new Float32Array(array.length / 3).fill(1), 1))
      return g
    }
    // inner core of the sphere, with a rim that gets brighter toward the outside
    // lõi cầu trong, viền sáng dần ra ngoài
    scene.add(new T.Mesh(new T.SphereGeometry(.995, 96, 64), new T.ShaderMaterial({ ...BLEND, uniforms: U,
      vertexShader: 'varying vec3 n; varying vec3 v; void main(){ vec4 mv = modelViewMatrix*vec4(position,1.); n = normalize(normalMatrix*position); v = normalize(-mv.xyz); gl_Position = projectionMatrix*mv; }',
      fragmentShader: 'uniform float away; varying vec3 n; varying vec3 v; void main(){ float f = pow(1.-max(dot(n,v),0.),2.6); vec3 c = mix(vec3(.01,.06,.16), vec3(.3,.85,1.), f); gl_FragColor = vec4(c*(.34+1.15*f)*(.5+.5*away),1.); }' })))
    // glow around the rim
    // vầng sáng quanh viền
    const c = document.createElement('canvas')
    c.width = c.height = 512
    const ctx2 = c.getContext('2d'), gr = ctx2.createRadialGradient(256, 256, 0, 256, 256, 256)
    gr.addColorStop(0, 'rgba(0,0,0,0)'); gr.addColorStop(.58, 'rgba(30,120,255,0)'); gr.addColorStop(.635, 'rgba(90,220,255,.5)'); gr.addColorStop(.8, 'rgba(50,170,255,.12)'); gr.addColorStop(1, 'rgba(30,120,255,0)')
    ctx2.fillStyle = gr; ctx2.fillRect(0, 0, 512, 512)
    const glow = new T.Sprite(new T.SpriteMaterial({ map: new T.CanvasTexture(c), ...BLEND }))
    glow.scale.setScalar(3.45)
    scene.add(glow)
    // the stand follows the camera so the base and orbit rings stay still on the screen
    // giá đỡ đi theo camera nên đáy và vòng quỹ đạo đứng yên trên màn hình
    const group = new T.Group()
    scene.add(group)
    const day = C.createBeam(T, U, ren, BLEND, true)
    day.beam.position.y = -1.43; day.beam.rotation.x = .3
    group.add(day.beam)
    const orbit = new T.Group()
    group.add(orbit)
    for (const [r, x, z, open] of [[1.3, 1.25, .25, .55], [1.42, 1.72, -.5, .32], [1.56, .95, .7, .2]]) {
      const v = new T.Mesh(new T.TorusGeometry(r, .0018, 6, 200), new T.MeshBasicMaterial({ color: 0x7fe9ff, opacity: open, ...BLEND }))
      v.rotation.set(x, 0, z); v.userData.open = open
      const h = new T.Mesh(new T.SphereGeometry(.012, 10, 10), new T.MeshBasicMaterial({ color: 0xffffff, ...BLEND }))
      h.position.x = r; v.add(h); orbit.add(v)
    }
    const pin = C.createPinLayer(host, api)
    const islandLabels = [], islandPts = []
    for (const [name, islands, labelLon, labelLat] of C.VN_ISLANDS) {
      for (const [lon, lat] of islands) { const p = toVec(lon, lat, 1.002); islandPts.push(p.x, p.y, p.z) }
      const e = document.createElement('div')
      e.className = 'bd-island'; e.textContent = name; e.style.opacity = 0
      pin.cls.append(e)
      islandLabels.push({ e, p: toVec(labelLon, labelLat, 1.004) })
    }
    scene.add(new T.Points(toLines(islandPts), makeMaterial(true, '#bdf6ff', 1.3, 3.2)))
    const shell = new T.Group()
    scene.add(shell)
    const gridMat = makeMaterial(false, '#59cfff', .5), nodeMat = makeMaterial(true, '#bff3ff', .9, 3.2), dotMat = makeMaterial(true, '#2fa8f5', 0, .9)
    // land.json is Natural Earth (see THIRD-PARTY.md); globe-grid.json and globe-nodes.json are made for this project: random points joined into a decorative network for the outer shell
    // land.json là Natural Earth (xem THIRD-PARTY.md); globe-grid.json và globe-nodes.json làm riêng cho dự án: các điểm ngẫu nhiên nối thành mạng trang trí cho lớp vỏ ngoài
    Promise.all(['land.json', 'globe-grid.json', 'globe-nodes.json'].map(C.loadJson)).then(([land, grid, button]) => {
      // draw the continents on a canvas to know which points are land
      // vẽ lục địa lên canvas để biết điểm nào là đất
      const W = C.LOW_POWER ? 2048 : 4096, H = W / 2, canvas = document.createElement('canvas')
      canvas.width = W; canvas.height = H
      const m = canvas.getContext('2d', { willReadFrequently: true }), borderPts = []
      m.fillStyle = '#fff'
      C.forEachRing(land, poly => {
        m.beginPath()
        for (const r of poly) {
          r.forEach(([lon, lat], i) => { const x = ((lon + 180) / 360) * W, y = ((90 - lat) / 180) * H; i ? m.lineTo(x, y) : m.moveTo(x, y) })
          for (let i = 1; i < r.length; i++) { const a = toVec(r[i - 1][0], r[i - 1][1], 1.0015), b = toVec(r[i][0], r[i][1], 1.0015); borderPts.push(a.x, a.y, a.z, b.x, b.y, b.z) }
        }
        m.fill('evenodd')
      })
      const px = m.getImageData(0, 0, W, H).data
      const isLand = (lon, lat) => px[(Math.min(H - 1, Math.floor(((90 - lat) / 180) * H)) * W + Math.min(W - 1, Math.floor(((lon + 180) / 360) * W))) * 4 + 3] > 128
      const isPoints = [], N = C.LOW_POWER ? 40000 : 90000, goldenAngle = Math.PI * (3 - Math.sqrt(5))
      for (let i = 0; i < N; i++) {
        const y = 1 - (2 * (i + .5)) / N, lat = (Math.asin(y) * 180) / Math.PI, lon = (((i * goldenAngle * 180) / Math.PI) % 360) - 180
        if (isLand(lon, lat)) { const p = toVec(lon, lat, 1.001); isPoints.push(p.x, p.y, p.z) }
      }
      const vnDots = [], otherDots = [], step = C.LOW_POWER ? .2 : .11
      for (let lat = 5; lat < 25; lat += step) for (let lon = 100; lon < 118; lon += step) if (isLand(lon, lat)) { const p = toVec(lon, lat, 1.001); vnDots.push(p.x, p.y, p.z); otherDots.push(Math.max(0, 1 - Math.hypot((lon - 107) / 9, (lat - 15.5) / 10)) ** .8) }
      scene.add(new T.Points(toLines(isPoints), makeMaterial(true, '#2fa8f5', .6, 1.3)))
      scene.add(new T.Points(toLines(vnDots, otherDots), dotMat))
      scene.add(new T.LineSegments(toLines(borderPts), makeMaterial(false, '#7feeff', .7)))
      const edges = []
      for (const f of grid.features) {
        const [a, b] = f.geometry.coordinates, pointA = toVec(a[0], a[1]), pointB = toVec(b[0], b[1])
        for (let i = 0; i < 10; i++) { const p = pointA.clone().lerp(pointB, i / 10).normalize().multiplyScalar(1.085), q = pointA.clone().lerp(pointB, (i + 1) / 10).normalize().multiplyScalar(1.085); edges.push(p.x, p.y, p.z, q.x, q.y, q.z) }
      }
      shell.add(new T.LineSegments(toLines(edges), gridMat))
      const nodes = []
      for (const f of button.features) { const p = toVec(...f.geometry.coordinates, 1.085); nodes.push(p.x, p.y, p.z) }
      shell.add(new T.Points(toLines(nodes), nodeMat))
    }).catch(() => {})

    const ringGeo = new T.RingGeometry(.8, 1, 48).rotateX(-Math.PI / 2), particleGeo = new T.SphereGeometry(1, 10, 10), Y0 = new T.Vector3(0, 1, 0)
    const add = r => {
      r.group = new T.Group()
      r.ring1 = new T.Mesh(ringGeo, new T.MeshBasicMaterial({ ...BLEND, side: T.DoubleSide }))
      r.ring2 = new T.Mesh(ringGeo, new T.MeshBasicMaterial({ ...BLEND, side: T.DoubleSide }))
      r.group.add(r.ring1, r.ring2)
      scene.add(r.group)
      r.path = new T.Line(new T.BufferGeometry(), new T.LineBasicMaterial({ color: 0xaaf4ff, ...BLEND }))
      scene.add(r.path)
      r.particles = [0, 1, 2].map(() => { const h = new T.Mesh(particleGeo, new T.MeshBasicMaterial({ color: 0xffffff, ...BLEND })); scene.add(h); return h })
    }
    const removeOne = r => { scene.remove(r.group, r.path, ...r.particles); r.path.geometry.dispose() }
    let pinList = []
    function update(group) {
      pinList = pin.syncPins(group, add, removeOne, r => {
        const n = r.n, color = n.critical ? 0xff5560 : n.waiting ? 0xffbd4a : n.working ? 0x8ff2ff : 0x6d93a8
        r.position = toVec(n.b.lon, n.b.lat)
        r.group.position.copy(r.position).multiplyScalar(1.002)
        r.group.quaternion.setFromUnitVectors(Y0, r.position)
        r.ring1.material.color.set(color); r.ring2.material.color.set(color)
      })
      const ts = pinList.find(r => r.n.b.isHq) || pinList[0]
      for (const r of pinList) {
        r.arcRing = null
        r.path.visible = false
        if (!ts || r === ts) continue
        const a = r.position, b = ts.position
        r.arcRing = new T.QuadraticBezierCurve3(a.clone().multiplyScalar(1.002), a.clone().add(b).normalize().multiplyScalar(1.002 + a.angleTo(b) * .62), b.clone().multiplyScalar(1.002))
        r.path.geometry.setFromPoints(r.arcRing.getPoints(60))
        r.path.visible = true
        r.path.material.color.set(r.n.critical ? 0xff9a9a : 0xaaf4ff)
        r.path.material.opacity = r.n.working + r.n.waiting ? .95 : .3
      }
    }

    const VIEWS = { globe: { lon: 107, lat: 12, distance: 5.5, tilt: 0 }, inVN: { lon: 107.6, lat: 15.4, distance: 1.92, tilt: 20 } }
    const v = { ...VIEWS.globe, lon: 40 }
    let flight = null, from = 0, drag = null, head = true
    const flyTo = (d, ms = 3000) => { flight = { from: { ...v }, d, t0: performance.now(), ms }; from = performance.now() }
    cv.addEventListener('pointerdown', e => { drag = { x: e.clientX, y: e.clientY, lon: v.lon, lat: v.lat }; flight = null; cv.setPointerCapture(e.pointerId) })
    cv.addEventListener('pointermove', e => { if (!drag) return; const s = 22 * (v.distance - .98); v.lon = drag.lon - ((e.clientX - drag.x) * s) / 180; v.lat = Math.max(-75, Math.min(75, drag.lat + ((e.clientY - drag.y) * s) / 180)); from = performance.now() })
    cv.addEventListener('pointerup', () => (drag = null))
    cv.addEventListener('pointercancel', () => (drag = null))
    cv.addEventListener('wheel', e => { e.preventDefault(); flight = null; v.distance = Math.max(1.1, Math.min(7, 1 + (v.distance - 1) * (e.deltaY < 0 ? .88 : 1.14))); from = performance.now() }, { passive: false })
    cv.addEventListener('dblclick', () => flyTo(VIEWS.globe, 1800))

    const pivot = new T.Vector3(), v3 = new T.Vector3(), governor = C.loadGovernor(ren)
    let visible = false, frameId = 0, previous = 0
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
        for (const k of ['lon', 'lat', 'distance', 'tilt']) v[k] = flight.from[k] + (flight.d[k] - flight.from[k]) * e
        if (q >= 1) flight = null
      } else if (!C.REDUCED_MOTION && !drag && !(api.hud && api.hud.viewing()) && performance.now() - from > 4000 && v.distance > 3.6) v.lon += Math.min(.05, t - previous) * 2.1
      previous = t
      const attach = Math.min(1, Math.max(0, (3.4 - v.distance) / 1.5)), k = attach * attach * (3 - 2 * attach)
      U.away.value = 1 - k
      cam.position.copy(toVec(v.lon, v.lat - v.tilt * k, v.distance))
      pivot.copy(toVec(v.lon, v.lat, k))
      cam.lookAt(pivot)
      group.quaternion.copy(cam.quaternion)
      glow.material.opacity = 1 - k
      day.update(t, k)
      orbit.visible = k < .98
      orbit.rotation.y = t * .06
      orbit.children.forEach((r, i) => { r.material.opacity = r.userData.open * (1 - k); r.children[0].material.opacity = 1 - k; r.rotation.z = t * .07 * (i + 1) })
      shell.rotation.y = t * .012
      dotMat.uniforms.bright.value = .55 * k
      gridMat.uniforms.bright.value = .5 * (.02 + .98 * (1 - k)); nodeMat.uniforms.bright.value = .9 * (.02 + .98 * (1 - k))
      const zoomClose = Math.max(.1, v.distance - 1), c1 = Math.min(1, .42 + zoomClose * .38), R = (.0016 * c1 / .9) * (1 + zoomClose * .3), s = .0085 * c1 * (1 + zoomClose * .3)
      for (const r of pinList) {
        const n = r.n, song = n.working + n.waiting + n.critical > 0, phase = (t * (n.critical ? 1.3 : .55) + n.b.lon) % 1
        r.ring1.scale.setScalar(s); r.ring1.material.opacity = .9
        r.ring2.scale.setScalar(song ? s * (1 + phase * 2.2) : s); r.ring2.material.opacity = song ? .8 * (1 - phase) : 0
        r.particles.forEach((x, i) => { x.visible = !!r.arcRing && n.working + n.waiting > 0; if (x.visible) { x.position.copy(r.arcRing.getPoint((t * .22 + i / 3) % 1)); x.scale.setScalar(R * 1.9) } })
        pivot.copy(r.position).multiplyScalar(1.002)
        v3.copy(cam.position).sub(pivot).normalize()
        r.hidden = r.position.dot(v3) > .05
        v3.copy(pivot).project(cam)
        r.sx = ((v3.x + 1) / 2) * w; r.sy = ((1 - v3.y) / 2) * h
      }
      pin.place(v.distance < 4.2, w)
      for (const d of islandLabels) {
        v3.copy(cam.position).sub(d.p).normalize()
        const show = v.distance < 3.2 && d.p.dot(v3) > .1
        d.e.style.opacity = show ? 1 : 0
        if (show) { v3.copy(d.p).project(cam); d.e.style.transform = `translate(-50%,-100%) translate(${((v3.x + 1) / 2) * w}px,${((1 - v3.y) / 2) * h}px)` }
      }
      if (api.hud) api.hud.place()
      ren.render(scene, cam)
    }
    return {
      update,
      flyTo(id) { const r = pin.fetchFn(id); if (r) flyTo({ lon: r.n.b.lon, lat: r.n.b.lat - .4, distance: 1.22, tilt: 12 }, 1900) },
      zoom(factor) { flyTo({ ...v, distance: Math.max(1.1, Math.min(7, 1 + (v.distance - 1) / factor)) }, 300) },
      fit() { flyTo(VIEWS.globe, 1800) },
      show(size) {
        visible = size
        cancelAnimationFrame(frameId)
        if (size) {
          frameId = requestAnimationFrame(draw)
          // first open: turn gently, then fly down to Vietnam
          // lần đầu mở: quay nhẹ rồi bay xuống Việt Nam
          if (head) { head = false; flyTo({ ...VIEWS.globe }, 1400); setTimeout(() => flyTo(VIEWS.inVN, 3400), 1800) }
        } else if (api.hud) api.hud.hide()
      },
    }
  }
  window.Map3D = { create }
})()
