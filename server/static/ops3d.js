// "3D" view of the diagram: people, Claude and the 3 assistants in three-dimensional space (three.js, loaded when 3D is chosen).
// Drag to rotate the view, scroll to zoom in / out, click a person's card to see their numbers; left alone, it slowly rotates by itself.
// Chế độ xem "3D" của sơ đồ: người, Claude và 3 trợ lý trong không gian ba chiều (three.js, tải khi chọn 3D).
// Kéo để xoay góc nhìn, lăn chuột để lại gần / ra xa, bấm thẻ một người để xem số liệu; để yên thì tự xoay chậm.
;(function () {
  'use strict'

  function create(host, api) {
    const T = window.THREE
    const ren = new T.WebGLRenderer({ antialias: true, alpha: true })
    ren.setPixelRatio(Math.min(2, window.devicePixelRatio || 1))
    const canvas = ren.domElement
    canvas.className = 'o-3d'
    host.append(canvas)
    const scene = new T.Scene()
    scene.fog = new T.Fog(0x050c13, 16, 40)
    const cam = new T.PerspectiveCamera(45, 1, 0.1, 200)
    const stage = new T.GridHelper(80, 80, 0x1d5a66, 0x0e2a32)
    stage.position.y = -3
    scene.add(stage)

    // card: a flat plane carrying an image drawn by the 2D diagram's own card function, always facing the viewer
    // thẻ: mặt phẳng mang ảnh vẽ bằng đúng hàm thẻ của sơ đồ 2D, luôn quay về phía người xem
    const PIXEL_RATIO = 2
    const CARD_W = 196
    const CARD_H = 58
    function createCard(width) {
      const c = document.createElement('canvas')
      c.width = CARD_W * PIXEL_RATIO
      c.height = CARD_H * PIXEL_RATIO
      const tex = new T.CanvasTexture(c)
      tex.colorSpace = T.SRGBColorSpace
      const m = new T.Mesh(new T.PlaneGeometry(width, (width * CARD_H) / CARD_W), new T.MeshBasicMaterial({ map: tex, transparent: true, depthWrite: false }))
      scene.add(m)
      return { c, g: c.getContext('2d'), tex, m, key: '' }
    }
    function drawCard(card, heading, sub, color, bright, money) {
      const k = [heading, sub, color, bright, Math.round((money || 0) * 40)].join('|')
      if (k === card.key) return
      card.key = k
      card.g.setTransform(PIXEL_RATIO, 0, 0, PIXEL_RATIO, 0, 0)
      card.g.clearRect(0, 0, CARD_W, CARD_H)
      api.card(card.g, 8, 8, CARD_W - 16, CARD_H - 16, heading, sub, color, bright, money)
      card.tex.needsUpdate = true
    }

    // curved link + light dots running along it while working / asking an assistant
    // đường nối cong + hạt sáng chạy dọc đường khi đang làm / đang nhờ trợ lý
    const particleGeometry = new T.SphereGeometry(0.07, 8, 8)
    function createLink() {
      const geo = new T.BufferGeometry()
      const line = new T.Line(geo, new T.LineBasicMaterial({ transparent: true }))
      scene.add(line)
      const particles = [0, 1, 2].map(() => {
        const h = new T.Mesh(particleGeometry, new T.MeshBasicMaterial({ color: 0xffffff }))
        scene.add(h)
        return h
      })
      return { line, particles, curve: null }
    }
    function setLink(d, a, b, color, active, t, speed) {
      const center = a.clone().lerp(b, 0.5)
      center.y += 1.4
      d.curve = new T.QuadraticBezierCurve3(a, center, b)
      d.line.geometry.setFromPoints(d.curve.getPoints(32))
      d.line.material.color.set(color)
      d.line.material.opacity = active ? 0.85 : 0.18
      d.particles.forEach((h, q) => {
        h.visible = active
        if (active) h.position.copy(d.curve.getPoint((t * speed + q / 3) % 1))
      })
    }
    function removeLink(d) {
      scene.remove(d.line)
      d.line.geometry.dispose()
      for (const h of d.particles) scene.remove(h)
    }
    function removeCard(card) {
      scene.remove(card.m)
      card.m.geometry.dispose()
      card.tex.dispose()
    }

    const hub = createCard(4.4)
    hub.m.position.set(0, 0, 0)
    const helperCards = api.HELPERS.map((_, k) => {
      const card = createCard(3.9)
      card.m.position.set(7.5, 2.4 - k * 2.4, 0)
      return card
    })
    const helperLinks = api.HELPERS.map(() => createLink())
    let personCards = []
    let personLinks = []
    let personCount = -1

    // people: arranged on arcs on the left, at most 10 per ring, each ring a bit higher
    // người: xếp trên các vòng cung bên trái, mỗi tầng tối đa 10 người, tầng cao dần
    function layoutPeople(n) {
      for (const card of personCards) removeCard(card)
      for (const d of personLinks) removeLink(d)
      personCards = []
      personLinks = []
      const perRing = 10
      const ringCount = Math.max(1, Math.ceil(n / perRing))
      for (let i = 0; i < n; i++) {
        const ring = Math.floor(i / perRing)
        const inRing = Math.min(perRing, n - ring * perRing)
        const j = i % perRing
        const yaw = Math.PI * (0.62 + (0.76 * (j + 0.5)) / inRing)
        const R = 8 + ringCount * 0.6
        const card = createCard(3.6)
        card.m.position.set(Math.cos(yaw) * R, (ring - (ringCount - 1) / 2) * 1.9, Math.sin(yaw) * R * 0.75)
        card.i = i
        personCards.push(card)
        personLinks.push(createLink())
      }
      personCount = n
    }

    // camera view: rotates around the center; drag to rotate, scroll to zoom in
    // the camera looks at the middle of the group (people on the left, assistants on the right), not at the Claude card
    // góc nhìn: xoay quanh tâm; kéo để xoay, lăn chuột để lại gần
    // tâm nhìn ở giữa cụm (người bên trái, trợ lý bên phải), không phải ở thẻ Claude
    const CENTER = new T.Vector3(-1.2, 0, 0.8)
    const look = { yaw: -0.3, pitch: 0.4, distance: 15.5, idleSince: 0 }
    const DEFAULT_DISTANCE = 15.5
    const updateCamera = () => {
      // narrow, tall frame (phone): move the camera back so the width fits
      // khung hẹp, dọc (điện thoại): lùi máy quay ra cho đủ bề ngang
      const distance = look.distance * Math.max(1, 1.6 / Math.max(0.3, cam.aspect)) ** 0.75
      cam.position.set(CENTER.x + Math.sin(look.yaw) * Math.cos(look.pitch) * distance, CENTER.y + Math.sin(look.pitch) * distance, CENTER.z + Math.cos(look.yaw) * Math.cos(look.pitch) * distance)
      cam.lookAt(CENTER)
    }
    let drag = null
    let justDragged = false
    canvas.addEventListener('pointerdown', e => {
      drag = { x: e.clientX, y: e.clientY, yaw: look.yaw, pitch: look.pitch }
      justDragged = false
    })
    addEventListener('pointermove', e => {
      if (!drag) return
      const dx = e.clientX - drag.x
      const dy = e.clientY - drag.y
      if (!justDragged && Math.hypot(dx, dy) < 4) return
      justDragged = true
      canvas.classList.add('dragging')
      look.yaw = drag.yaw - dx * 0.006
      look.pitch = Math.min(1.35, Math.max(0.05, drag.pitch + dy * 0.005))
      look.idleSince = performance.now()
    })
    addEventListener('pointerup', () => {
      drag = null
      canvas.classList.remove('dragging')
    })
    canvas.addEventListener('wheel', e => {
      e.preventDefault()
      zoom(Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0015)))
    }, { passive: false })
    function zoom(k) {
      look.distance = Math.min(45, Math.max(6, look.distance / k))
      look.idleSince = performance.now()
    }
    function fit() {
      look.yaw = -0.3
      look.pitch = 0.4
      look.distance = DEFAULT_DISTANCE
    }
    const ray = new T.Raycaster()
    canvas.addEventListener('click', e => {
      if (justDragged) return void (justDragged = false)
      const r = canvas.getBoundingClientRect()
      ray.setFromCamera(new T.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1), cam)
      const hit = ray.intersectObjects(personCards.map(card => card.m))[0]
      const card = hit && personCards.find(x => x.m === hit.object)
      api.selected(card ? card.i : -1)
    })

    let visibleNow = false
    let frameId = 0
    function draw(ts) {
      if (!visibleNow) return
      frameId = requestAnimationFrame(draw)
      const t = ts / 1000
      const w = host.clientWidth
      const h = host.clientHeight
      if (canvas.width !== Math.round(w * ren.getPixelRatio()) || canvas.height !== Math.round(h * ren.getPixelRatio())) {
        ren.setSize(w, h, false)
        cam.aspect = w / Math.max(1, h)
        cam.updateProjectionMatrix()
      }
      // left alone for a few seconds, it rotates slowly by itself
      // để yên vài giây thì tự xoay chậm
      if (!drag && performance.now() - look.idleSince > 5000) look.yaw += 0.0016
      updateCamera()
      stage.position.z = (t * 0.4) % 1

      const people = api.people()
      if (people.length !== personCount) layoutPeople(people.length)
      const maxUsd = Math.max(...people.map(p => p.usdToday), 1e-9)
      const counts = people.filter(p => p.status === 'working').length
      const delegatingByHelper = [0, 1, 2].map(k => people.filter(p => (p.delegating || [])[k] > 0))
      const selected = api.selectedIndex()
      people.forEach((p, i) => {
        const card = personCards[i]
        const st = api.STATUS_INFO[p.status]
        const pulse = p.status === 'waiting' ? 0.5 + 0.5 * Math.abs(Math.sin(t * 3)) : 1
        card.m.material.opacity = p.status === 'offline' ? 0.45 : pulse
        drawCard(card, p.name, `${st.name} · ${api.mainModel(p) || api.compact(p.tokensIn) + ' tok'}`, st.color, p.status === 'working' || i === selected, p.usdToday / maxUsd)
        card.m.quaternion.copy(cam.quaternion)
        const active = p.status === 'working' || p.status === 'waiting'
        if (p.status === 'offline') {
          personLinks[i].line.visible = false
          personLinks[i].particles.forEach(x => (x.visible = false))
        } else {
          personLinks[i].line.visible = true
          setLink(personLinks[i], card.m.position, hub.m.position, st.color, active, t, p.status === 'working' ? 0.45 : 0.12)
        }
      })
      drawCard(hub, 'CLAUDE // CORE', `${counts} RUNNING · ${people.length} NODES`, '#5ee6f0', true, people.length ? counts / people.length : 0)
      hub.m.quaternion.copy(cam.quaternion)
      api.HELPERS.forEach((a, k) => {
        const helpers = delegatingByHelper[k]
        const sub = helpers.length ? 'PROCESSING ← ' + helpers.map(p => p.name).join(', ') : `STANDBY · ${people.reduce((s, p) => s + p.tasks[k], 0)} today`
        drawCard(helperCards[k], a.name, sub, a.color, helpers.length > 0)
        helperCards[k].m.quaternion.copy(cam.quaternion)
        setLink(helperLinks[k], hub.m.position, helperCards[k].m.position, a.color, helpers.length > 0, t, helpers.length ? 0.55 : 0.1)
      })
      ren.render(scene, cam)
    }

    function show(visible) {
      visibleNow = visible
      canvas.style.display = visible ? 'block' : 'none'
      cancelAnimationFrame(frameId)
      if (visible) {
        look.idleSince = 0
        frameId = requestAnimationFrame(draw)
      }
    }
    return { show, zoom, fit }
  }

  window.Ops3D = { create }
})()
