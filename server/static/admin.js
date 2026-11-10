// Admin page: OTP accounts, locations, Team plan, open sessions, audit log. The server checks the right for every action itself.
// Trang quản trị: tài khoản OTP, địa điểm, gói Team, phiên đang mở, nhật ký. Máy chủ tự kiểm quyền từng thao tác.
;(function () {
  'use strict'
  // The 34 provinces and cities after the merger; rough coordinates, only used to place a dot on the map. Names stay Vietnamese on purpose.
  // 34 tỉnh, thành sau sáp nhập; toạ độ xấp xỉ, chỉ để chấm lên bản đồ. Tên giữ tiếng Việt có chủ đích.
  const PROVINCES = [['Hà Nội', 21.03, 105.85], ['TP. Hồ Chí Minh', 10.78, 106.7], ['Hải Phòng', 20.86, 106.68], ['Đà Nẵng', 16.05, 108.21], ['Cần Thơ', 10.04, 105.78], ['Huế', 16.46, 107.59], ['An Giang', 10.01, 105.08], ['Bắc Ninh', 21.28, 106.2], ['Cà Mau', 9.18, 105.15], ['Cao Bằng', 22.67, 106.26], ['Đắk Lắk', 12.67, 108.04], ['Điện Biên', 21.39, 103.02], ['Đồng Nai', 10.95, 106.82], ['Đồng Tháp', 10.36, 106.36], ['Gia Lai', 13.78, 109.22], ['Hà Tĩnh', 18.34, 105.91], ['Hưng Yên', 20.65, 106.05], ['Khánh Hòa', 12.24, 109.19], ['Lai Châu', 22.39, 103.46], ['Lâm Đồng', 11.94, 108.44], ['Lạng Sơn', 21.85, 106.76], ['Lào Cai', 21.72, 104.9], ['Nghệ An', 18.67, 105.68], ['Ninh Bình', 20.25, 105.97], ['Phú Thọ', 21.32, 105.4], ['Quảng Ngãi', 15.12, 108.8], ['Quảng Ninh', 20.95, 107.08], ['Quảng Trị', 17.47, 106.62], ['Sơn La', 21.33, 103.91], ['Tây Ninh', 10.54, 106.41], ['Thái Nguyên', 21.59, 105.85], ['Thanh Hóa', 19.81, 105.78], ['Tuyên Quang', 21.82, 105.21], ['Vĩnh Long', 10.25, 105.97]] // i18n-allow
  const ROLE_NAMES = { 'admin': tx('Admin'), viewer: tx('View only'), wall: tx('Wall display') }
  const ACTION_NAMES = {
    'login': tx('Log in'), 'login-failed': tx('Login failed'), 'confirmed': tx('Re-enter OTP'), 'confirm-failed': tx('Wrong OTP re-entered'), 'confirm-required': tx('OTP not re-entered'),
    'role-denied': tx('Denied by role'), error: tx('Error'), assign: tx('Add network'), unassign: tx('Remove network'), 'unassign-delete-location': tx('Last network removed, location deleted'), 'set-sales': tx('Mark as sales'), csv: tx('Load CSV'),
    'account-create': tx('Create account'), 'account-reissue': tx('Reissue key'), 'account-role': tx('Change role'), 'account-delete': tx('Delete account'), 'end-session': tx('End session'),
    'tv-request-code': tx('Screen asked for code'), 'tv-refused': tx('Code request refused'), 'tv-view': tx('Viewed screen request'), 'tv-approve': tx('Approved screen'), 'tv-joined': tx('Screen joined board'), 'tv-revoke': tx('Revoked screen'), 'tv-self-exit': tx('Screen exited by itself'), 'tv-reload': tx('Reloaded screen remotely'), 'tv-rename': tx('Renamed screen'), 'tv-ip-changed': tx('Screen changed IP'), 'tv-renewed': tx('Renewed screen'),
    'tv-revoked-key-used': tx('Revoked device asked again'),
    'account-telegram-unlink': tx('Unlink Telegram'), 'telegram-link': tx('Link Telegram'), 'telegram-unlink': tx('Unlink Telegram'), 'telegram-link-failed': tx('Telegram link failed'),
  }
  // Error text that means "the admin cancelled", so no error toast is shown.
  // Chữ lỗi nghĩa là "quản trị viên đã huỷ", nên không hiện thông báo lỗi.
  const CANCELLED = tx('Cancelled')
  const viewerName = document.body.dataset.user || ''
  const root = document.getElementById('admin')
  const o = (el, cls, text) => {
    const e = document.createElement(el)
    if (cls) e.className = cls
    if (text !== undefined) e.textContent = text
    return e
  }
  const button = (text, actions, cls) => {
    const b = o('button', cls || 'qt-button', text)
    b.type = 'button'
    b.addEventListener('click', actions)
    return b
  }
  const dateTime = ms => new Date(ms).toLocaleString(I18n.locale, { hour12: false })
  // Vietnamese mode shows dong through the rate as before; English shows US dollars with no conversion.
  // Tiếng Việt hiện đồng qua tỉ giá như trước; tiếng Anh hiện đô la Mỹ, không quy đổi.
  const compactMoney = d => (d >= 1e6 ? (d / 1e6).toFixed(2).replace('.', ',') + 'tr' : d >= 1e3 ? Math.round(d / 1e3) + 'k' : Math.round(d)) + ' đ' // i18n-allow
  const money = (dollars, rate) => (I18n.lang === 'vi' ? compactMoney(dollars * rate) : '$' + dollars.toFixed(2))

  let snapshot = null, month = '', newSecret = null, singlesOpen = false, dateFrom = '', dateTo = '', tvRequest = null, tvCode = ''
  // ip -> what is half filled in
  // ip -> nội dung đang điền dở
  const drafts = new Map()
  const notice = o('div', 'qt-notice')
  notice.hidden = true
  notice.setAttribute('role', 'status')
  function toast(text, isError) {
    notice.textContent = text
    notice.classList.toggle('error', !!isError)
    notice.hidden = false
    clearInterval(countdown.t)
    clearTimeout(toast.t)
    toast.t = setTimeout(() => (notice.hidden = true), isError ? 9000 : 4000)
  }
  // The TV asks the server every 10 seconds, so it may reload before the countdown ends; the server does not report back, so at the end we only remind to check.
  // TV hỏi máy chủ 10 giây một lần nên có thể tải lại sớm hơn lúc đếm xong; máy chủ không báo lại nên hết giờ chỉ nhắc kiểm tra.
  function countdown(name, seconds) {
    const endAt = Date.now() + seconds * 1000
    const text = () => tx('{name} will reload within {n} seconds', { name, n: Math.ceil((endAt - Date.now()) / 1000) })
    toast(text())
    clearTimeout(toast.t)
    countdown.t = setInterval(() => {
      if (Date.now() < endAt) notice.textContent = text()
      else toast(tx('Over {seconds} seconds have passed. If {name} has not reloaded, check that the screen is still on', { seconds, name }))
    }, 1000)
  }

  // Box to re-enter the OTP code: resolves to true once confirmed.
  // Hộp nhập lại mã OTP: trả về true khi đã xác nhận.
  const dialog = o('dialog', 'qt-dialog')
  const dialogForm = o('form')
  dialogForm.method = 'dialog'
  const otpInput = o('input')
  otpInput.inputMode = 'numeric'
  otpInput.maxLength = 6
  otpInput.autocomplete = 'one-time-code'
  otpInput.setAttribute('aria-label', tx('OTP code'))
  const dialogError = o('small', 'qt-error')
  const dialogOk = o('button', 'qt-button primary', tx('Confirm'))
  dialogOk.type = 'submit'
  const dialogCancel = button(tx('Cancel'), () => dialog.close('cancel'))
  const dialogButtons = o('div', 'qt-row')
  dialogButtons.append(dialogOk, dialogCancel)
  dialogForm.append(o('b', '', tx('Enter your OTP code again')), o('small', '', tx('This action needs confirmation, valid for 5 minutes. The code you just used to log in cannot be reused, wait for a new one.')), otpInput, dialogError, dialogButtons)
  dialog.append(dialogForm)
  // Kept outside #qt: ve() replaces all of #qt, and removing an open box from the page would lose its modal state.
  // Để ngoài #qt: ve() thay toàn bộ #qt, gỡ hộp đang mở khỏi trang sẽ làm nó mất trạng thái modal.
  document.body.append(dialog)
  function askOtp() {
    return new Promise(done => {
      otpInput.value = ''
      dialogError.textContent = ''
      const submit = async e => {
        e.preventDefault()
        dialogOk.disabled = true
        try {
          const r = await fetch('/admin/confirm', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code: otpInput.value.trim() }) })
          if (r.status === 401) return location.reload()
          if (r.ok) {
            dialog.close('ok')
            return
          }
          dialogError.textContent = (await r.json().catch(() => ({}))).error || tx('Could not confirm')
          otpInput.value = ''
        } catch {
          dialogError.textContent = tx('Connection lost, try again')
        } finally {
          dialogOk.disabled = false
        }
      }
      dialogForm.addEventListener('submit', submit)
      dialog.addEventListener('close', () => {
        dialogForm.removeEventListener('submit', submit)
        done(dialog.returnValue === 'ok')
      }, { once: true })
      dialog.returnValue = ''
      dialog.showModal()
      otpInput.focus()
    })
  }

  async function submit(path, body) {
    for (let attempt = 0; attempt < 2; attempt++) {
      const r = await fetch(path, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      if (r.status === 401) location.reload()
      const d = await r.json().catch(() => ({}))
      if (r.ok) return d
      if (d.needsConfirm && attempt === 0) {
        if (!(await askOtp())) throw new Error(CANCELLED)
        continue
      }
      throw new Error(d.error || tx('Server refused ({status})', { status: r.status }))
    }
  }

  // Do the action, then reload the data; on error show it, without losing what is being filled in.
  // Thao tác rồi tải lại dữ liệu; lỗi thì báo, không làm mất nội dung đang điền.
  async function post(path, body, done) {
    try {
      const d = await submit(path, body)
      if (done) done(d)
      await load()
      return d
    } catch (e) {
      if (e.message !== CANCELLED) toast(e.message, true)
    }
  }

  function section(title, subtitle) {
    const p = o('section', 'qt-section')
    const h = o('h2', '', title)
    if (subtitle) h.append(o('small', '', subtitle))
    p.append(h)
    return p
  }
  // Phone: each table row becomes a card, each cell carries its column name (CSS reads data-label).
  // Điện thoại: mỗi dòng của bảng thành một thẻ, mỗi ô ghi kèm tên cột (CSS đọc data-label).
  function addLabel(board) {
    const head = [...board.rows[0].cells].map(c => c.textContent)
    for (const r of [...board.rows].slice(1)) [...r.cells].forEach((c, i) => {
      if (head[i]) c.dataset.label = head[i]
    })
    return board
  }
  function pickRole(value) {
    const s = o('select')
    s.setAttribute('aria-label', tx('Role'))
    for (const [k, text] of Object.entries(ROLE_NAMES)) {
      const c = o('option', '', text)
      c.value = k
      s.append(c)
    }
    s.value = value
    return s
  }

  function newSecretSection() {
    const p = o('div', 'qt-secret')
    p.append(o('b', '', tx('Scan code for {name}', { name: newSecret.name })))
    try {
      const qr = window.qrcode(0, 'M')
      qr.addData(newSecret.uri)
      qr.make()
      const qrImage = o('img')
      qrImage.alt = tx('QR code to scan with Google Authenticator')
      qrImage.src = qr.createDataURL(5, 3)
      p.append(qrImage)
    } catch {
      p.append(o('small', 'qt-error', tx('Could not draw the QR code, type the key below.')))
    }
    p.append(o('small', '', tx('Open Google Authenticator > the + sign > Scan QR code. Or choose to enter a setup key, time-based key type:')))
    p.append(o('code', '', newSecret.key.replace(/(.{4})/g, '$1 ').trim()))
    p.append(o('small', '', tx('The key is shown only this once. Do not take a photo or send it by chat.')))
    p.append(button(tx('Scanned, hide'), () => {
      newSecret = null
      render()
    }, 'qt-button primary'))
    return p
  }

  function accountsSection() {
    const p = section(tx('Accounts'), tx('A role change takes effect at once, nobody is logged out'))
    if (newSecret) p.append(newSecretSection())
    const adminCount = snapshot.accounts.filter(t => t.role === 'admin').length
    if (adminCount < 2) p.append(o('div', 'qt-hint', tx('Keep at least two admins, so that if one loses their phone the other can still get in.')))
    const board = o('table', 'qt-table')
    const head = o('tr')
    // the Telegram column shows once someone has linked Telegram
    // cột Telegram hiện khi đã có người liên kết Telegram
    const withTelegram = snapshot.accounts.some(t => t.telegram)
    for (const c of [tx('Name'), tx('Role'), ...(withTelegram ? ['Telegram'] : []), tx('Last login'), '']) head.append(o('th', '', c))
    board.append(head)
    for (const t of snapshot.accounts) {
      const h = o('tr')
      const role = pickRole(t.role)
      role.addEventListener('change', () => post('/admin/accounts', { action: 'role', name: t.name, role: role.value }, () => toast(tx('Changed the role of {name}', { name: t.name }))).then(d => {
        if (!d) role.value = t.role
      }))
      const roleCell = o('td')
      roleCell.append(role)
      const actions = o('td', 'qt-action')
      actions.append(button(tx('Reissue key'), () => {
        if (confirm(tx('Reissue the key for {name}? The old code of this account stops working at once.', { name: t.name }))) post('/admin/accounts', { action: 'reissue', name: t.name }, d => (newSecret = { name: t.name, key: d.secret, uri: d.uri }))
      }))
      if (t.telegram) {
        actions.append(button(tx('Unlink Telegram'), () => {
          if (confirm(tx('Unlink Telegram from {name}? They log in with their name and code until they link again.', { name: t.name }))) post('/admin/accounts', { action: 'telegram-unlink', name: t.name }, () => toast(tx('Unlinked Telegram from {name}', { name: t.name })))
        }))
      }
      if (t.name !== viewerName) {
        actions.append(button(tx('Delete'), () => {
          if (confirm(tx('Delete the account {name}? They are logged out at once. Data is not deleted.\n\nRemind this person to delete the entry in Google Authenticator, because this page cannot do it for them.', { name: t.name }))) post('/admin/accounts', { action: 'delete', name: t.name }, () => toast(tx('Deleted {name}', { name: t.name })))
        }, 'qt-button critical'))
      }
      h.append(o('td', '', t.name + (t.name === viewerName ? ' ' + tx('(you)') : '')), roleCell, ...(withTelegram ? [o('td', '', t.telegram === 'linked' ? tx('linked') : t.telegram || '—')] : []),
        o('td', '', t.lastLoginAt ? dateTime(t.lastLoginAt) : '—'), actions)
      board.append(h)
    }
    p.append(addLabel(board))
    const row = o('div', 'qt-row')
    const name = o('input')
    name.placeholder = tx('Name, for example finance-team')
    name.maxLength = 30
    name.setAttribute('aria-label', tx('Name of the new account'))
    const newRole = pickRole('viewer')
    row.append(name, newRole, button(tx('Create account'), () => {
      const t = name.value.trim()
      if (!/^[A-Za-z0-9._-]{1,30}$/.test(t)) return toast(tx('The name may only contain letters without accents, digits, . _ -'), true)
      post('/admin/accounts', { action: 'create', name: t, role: newRole.value }, d => (newSecret = { name: t, key: d.secret, uri: d.uri }))
    }, 'qt-button primary'))
    p.append(row)
    return p
  }

  async function viewTv(count) {
    tvCode = count
    try {
      const d = await submit('/admin/tv-view', { code: count })
      tvRequest = { ...d, code: count }
      tvCode = ''
      render()
      const el = document.querySelector('.qt-tv-card')
      if (el) el.scrollIntoView({ block: 'center' })
    } catch (e) {
      if (e.message !== CANCELLED) toast(e.message, true)
      render()
    }
  }

  function tvSection() {
    const p = section(tx('TV screens'), tx('Scan the QR code on the TV with a phone camera, or enter the code here'))
    const row = o('div', 'qt-row')
    const code = o('input')
    code.placeholder = tx('8-digit code on the TV')
    code.inputMode = 'numeric'
    code.maxLength = 9
    code.setAttribute('aria-label', tx('Code on the TV'))
    code.value = tvCode
    row.append(code, button(tx('View request'), () => viewTv(code.value.replace(/\D/g, '')), 'qt-button primary'))
    p.append(row)
    if (tvRequest) {
      const y = tvRequest
      const el = o('div', 'qt-secret qt-tv-card')
      el.append(o('b', '', tx('Request from code {code}', { code: y.code.slice(0, 4) + '-' + y.code.slice(4) })), o('span', '', tx('Device: {device}', { device: y.device })), o('span', '', `IP: ${y.ip}`))
      // A browser extension of a manager pairs with the same code: say so, so an admin can tell a laptop from a TV.
      // Tiện ích trình duyệt của quản lý ghép bằng cùng loại mã: nói rõ, để quản trị phân biệt laptop với TV.
      const isExtension = y.kind === 'extension'
      if (isExtension) el.append(o('span', '', tx('Type: browser extension for a manager')))
      if (y.branch) el.append(o('span', '', tx('Branch: {branch}', { branch: y.branch })))
      else el.append(o('div', 'qt-hint', tx('This IP is outside the declared branches. Approve only if you are sure this is a company screen.')))
      el.append(o('span', '', tx('Asked at {time}', { time: dateTime(y.createdAt) })), o('small', '', tx('Approve only if it is really the screen you are setting up. An approved device can see people names and costs.')))
      const name = o('input')
      name.placeholder = tx('Screen name, for example Meeting room TV')
      name.maxLength = 40
      name.setAttribute('aria-label', tx('Screen name'))
      // Pairing an old screen again replaces the old row instead of adding one. Same network and same device type can still be two different TVs, so the person must choose.
      // Ghép lại màn hình cũ thì thay dòng cũ, không tạo thêm. Cùng mạng và cùng loại máy vẫn có thể là hai TV khác nhau, nên bắt người chọn.
      const similar = new Set(y.similar.map(x => x.id))
      const picker = o('select')
      picker.setAttribute('aria-label', tx('New screen or replace an old screen'))
      const addOption = (value, text) => {
        const c = o('option', '', text)
        c.value = value
        picker.append(c)
      }
      if (similar.size) addOption('', tx('Choose: new screen or old screen…'))
      addOption('new', tx('Add a new screen'))
      for (const t of snapshot.screens) addOption(t.id, tx('Replace {name}', { name: t.name }) + (t.exitedAt ? ' ' + tx('(exited)') : '') + (similar.has(t.id) ? ' ' + tx('(same network, same device type)') : ''))
      picker.addEventListener('change', () => {
        const existing = snapshot.screens.find(t => t.id === picker.value)
        if (existing && !name.value.trim()) name.value = existing.name
      })
      if (similar.size) el.append(o('div', 'qt-hint', tx('This may be a screen already paired: {names}. If so, choose replace so no extra row is added.', { names: y.similar.map(x => x.name).join(', ') })))
      if (snapshot.screens.length) el.append(picker)
      const row = o('div', 'qt-row')
      row.append(name, button(tx('Approve'), () => {
        if (snapshot.screens.length && !picker.value) return toast(tx('Choose new screen or old screen first'), true)
        if (!name.value.trim()) return toast(tx('Give the screen a name first'), true)
        post('/admin/tv-approve', { code: y.code, name: name.value, ...(picker.value && picker.value !== 'new' ? { replaceId: picker.value } : {}) }, () => {
          tvRequest = null
          toast(isExtension ? tx('Approved, the extension will be paired within a minute') : tx('Approved, the screen will join the board by itself within about 10 seconds'))
        })
      }, 'qt-button primary'), button(tx('Skip'), () => {
        tvRequest = null
        render()
      }))
      el.append(row)
      p.append(el)
    }
    if (snapshot.screens.length) {
      const board = o('table', 'qt-table')
      const head = o('tr')
      for (const c of [tx('Name'), tx('Status'), tx('Version'), tx('Device'), tx('Branch'), tx('Latest IP'), tx('Approved by'), '']) head.append(o('th', '', c))
      board.append(head)
      for (const t of snapshot.screens) {
        const h = o('tr')
        const actions = o('td', 'qt-action')
        // Once exited there is no page left to reload; the row only remains to keep the name when pairing again, delete it when no longer needed.
        // Đã thoát thì không còn trang nào để tải lại; dòng chỉ còn để ghép lại giữ tên, không cần nữa thì xoá.
        if (!t.exitedAt) actions.append(button(tx('Reload'), () => post('/admin/tv-reload', { id: t.id }, () => countdown(t.name, 10))))
        actions.append(button(tx('Rename'), () => {
          const newName = prompt(tx('New name for the screen'), t.name)
          if (newName && newName.trim()) post('/admin/tv-rename', { id: t.id, name: newName })
        }), t.exitedAt ? button(tx('Delete'), () => {
          if (confirm(tx('Remove {name} from the list? This name will no longer be available to choose when pairing again.', { name: t.name }))) post('/admin/tv-revoke', { id: t.id }, () => toast(tx('Deleted {name}', { name: t.name })))
        }, 'qt-button critical') : button(tx('Revoke'), () => {
          const question = t.kind === 'extension' ? tx('Revoke {name}? Within a minute that browser shows it is not paired.', { name: t.name }) : tx('Revoke {name}? That screen goes back to the pairing page at once.', { name: t.name })
          if (confirm(question)) post('/admin/tv-revoke', { id: t.id }, () => toast(tx('Revoked {name}', { name: t.name })))
        }, 'qt-button critical'))
        const statusText = t.exitedAt ? tx('Exited at {time}', { time: dateTime(t.exitedAt * 1000) }) : t.running ? tx('Running') : t.lastSeenAt ? tx('Not seen for a while, last seen {time}', { time: dateTime(t.lastSeenAt) }) : tx('Not seen since the server started')
        const statusCell = o('td', t.running ? '' : 'qt-muted', statusText)
        const versionCell = o('td', t.upToDate === false ? 'qt-old' : '', t.upToDate === null ? '—' : t.upToDate ? tx('Latest') : tx('Old version'))
        h.append(o('td', '', t.name), statusCell, versionCell, o('td', '', t.kind === 'extension' ? tx('Browser extension · {device}', { device: t.device }) : t.device), o('td', '', t.branch || '—'), o('td', '', t.lastIp), o('td', '', t.owner ? tx('{name} (paired by themselves)', { name: t.owner }) : t.approvedBy), actions)
        board.append(h)
      }
      p.append(addLabel(board))
    }
    return p
  }

  function groupForm(g, branches) {
    const draft = drafts.get(g.ip) || {}
    drafts.set(g.ip, draft)
    const groupBox = o('div', 'qt-group')
    groupBox.append(o('b', '', tx('{n} people · network {ip}', { n: g.people.length, ip: g.ip })), o('small', '', g.people.join(', ')))
    const picker = o('select')
    picker.setAttribute('aria-label', tx('Location of this group of devices'))
    const addOption = (parent, value, text) => {
      const c = o('option', '', text)
      c.value = value
      parent.append(c)
    }
    addOption(picker, '', tx('Choose a location…'))
    if (branches.length) {
      const existingGroup = o('optgroup')
      existingGroup.label = tx('Existing branches')
      branches.forEach(b => addOption(existingGroup, 'ma:' + b.id, b.name))
      picker.append(existingGroup)
    }
    const newGroup = o('optgroup')
    newGroup.label = tx('New location in a province or city')
    PROVINCES.forEach((t, i) => addOption(newGroup, 'tinh:' + i, t[0]))
    picker.append(newGroup)
    picker.value = draft.picker || ''
    const name = o('input')
    name.placeholder = tx('Name (leave empty: province name)')
    name.maxLength = 60
    name.value = draft.name || ''
    name.hidden = !String(picker.value).startsWith('tinh:')
    name.addEventListener('input', () => (draft.name = name.value))
    picker.addEventListener('change', () => {
      draft.picker = picker.value
      name.hidden = !picker.value.startsWith('tinh:')
    })
    const row = o('div', 'qt-row')
    row.append(picker, name, button(tx('Save'), () => {
      if (!picker.value) return toast(tx('Choose a location first'), true)
      const [kind, value] = picker.value.split(':')
      const body = kind === 'ma' ? { ip: g.ip, id: value } : { ip: g.ip, name: name.value.trim() || PROVINCES[value][0], lat: PROVINCES[value][1], lon: PROVINCES[value][2] }
      post('/locations', body, () => drafts.delete(g.ip))
    }, 'qt-button primary'))
    groupBox.append(row)
    return groupBox
  }

  function locationsSection() {
    const p = section(tx('Locations'), tx('New devices on the same network join the right group by themselves'))
    const branches = snapshot.branches
    const multiGroups = snapshot.unnamedGroups.filter(g => g.people.length > 1), singles = snapshot.unnamedGroups.filter(g => g.people.length === 1)
    if (multiGroups.length) p.append(o('h3', '', tx('Unnamed groups of devices')), ...multiGroups.map(g => groupForm(g, branches)))
    if (singles.length) {
      const d = o('details')
      d.open = singlesOpen
      d.addEventListener('toggle', () => (singlesOpen = d.open))
      d.append(o('summary', '', tx('Single devices ({n}): home, 4G, or a small office', { n: singles.length })), ...singles.map(g => groupForm(g, branches)))
      p.append(d)
    }
    p.append(o('h3', '', tx('Branches')))
    if (!branches.length) p.append(o('small', '', tx('No location yet.')))
    for (const b of branches) {
      const h = o('div', 'qt-group')
      h.append(o('b', '', b.name + (b.isHq ? ' · ' + tx('head office') : '')))
      if (!(b.customNetworks || []).length) h.append(o('small', '', tx('Declared in the config file, cannot be removed here.')))
      for (const ip of b.customNetworks || []) {
        const d = o('div', 'qt-row')
        d.append(o('span', '', ip), button(tx('Remove network'), () => {
          const isLast = b.customNetworks.length === 1
          if (confirm(tx('Remove network {ip} from {name}?', { ip, name: b.name }) + (isLast ? '\n\n' + tx('This is the last network: the pin of this location will disappear from the map. Data is not deleted.') : ''))) post('/locations', { ip, remove: true, confirm: true }, () => toast(tx('Removed network {ip}', { ip })))
        }, 'qt-button critical'))
        h.append(d)
      }
      p.append(h)
    }
    return p
  }

  function teamSection() {
    const p = section(tx('Team plan'), tx('Costs outside the plugin: Claude on phone and web'))
    const t = snapshot.team
    const usd = v => v.net || v.gross
    const day = (value, setValue, label) => {
      const labelEl = o('label', 'qt-date')
      const n = o('input')
      n.type = 'date'
      n.value = value
      n.addEventListener('change', () => setValue(n.value))
      labelEl.append(o('small', '', label), n)
      return labelEl
    }
    p.append(o('small', '', tx('Download the file at claude.ai/analytics, section “How much is Claude costing?” > Export spend report. Enter the exact period of the file in the two date boxes, then click load.')))
    const row = o('div', 'qt-row')
    row.append(day(dateFrom, v => (dateFrom = v), tx('From date')), day(dateTo, v => (dateTo = v), tx('To date')), button(t ? tx('Load new file') : tx('Load CSV'), () => {
      const f = o('input')
      f.type = 'file'
      f.accept = '.csv,text/csv'
      f.addEventListener('change', async () => {
        if (f.files[0]) post('/team-csv', { csv: await f.files[0].text(), dateFrom, dateTo }, () => toast(tx('File loaded')))
      })
      f.click()
    }, 'qt-button primary'))
    p.append(row)
    if (!t) return p
    const rate = snapshot.usdRate || 26000
    const period = t.dateFrom || t.dateTo ? `${t.dateFrom || '?'} → ${t.dateTo || '?'}` : tx('no period recorded')
    p.append(o('div', 'qt-group', `${period} · ${tx('{n} people', { n: t.items.length })} · ${money(t.items.reduce((a, x) => a + usd(x.other), 0), rate)}`))
    const d = o('details')
    d.append(o('summary', '', tx('Each person (mark the market sales team)')))
    for (const x of t.items) {
      const h = o('label', 'qt-person')
      const c = o('input')
      c.type = 'checkbox'
      c.checked = x.isSales
      c.addEventListener('change', () => post('/team-sale', { email: x.email, isSales: c.checked }).then(r => {
        if (!r) c.checked = !c.checked
      }))
      h.append(c, o('span', '', x.email + (x.hasDevice ? '' : ' · ' + tx('plugin not installed'))), o('b', '', money(usd(x.other), rate)))
      d.append(h)
    }
    p.append(d)
    return p
  }

  function sessionsSection() {
    const p = section(tx('Open sessions'), tx('If you suspect a leak, end the sessions then reissue the key'))
    const groups = new Map()
    for (const x of snapshot.sessions) groups.set(x.name, [...(groups.get(x.name) || []), x])
    for (const [name, items] of groups) {
      const h = o('div', 'qt-row')
      const mine = items.some(x => x.mine)
      h.append(o('span', '', `${name}${mine ? ' ' + tx('(you)') : ''} · ${ROLE_NAMES[items[0].role] || items[0].role} · ${items.length === 1 ? tx('1 session') : tx('{n} sessions', { n: items.length })} · ${tx('expires {time}', { time: dateTime(Math.max(...items.map(x => x.expiresAt))) })}`))
      if (!mine || items.length > 1) {
        h.append(button(mine ? tx('End the other sessions') : tx('End'), () => post('/admin/sessions', { name }, () => toast(tx('Ended the sessions of {name}', { name })))))
      }
      p.append(h)
    }
    return p
  }

  function auditSection() {
    const p = section(tx('Audit log'), tx('Kept for 12 months; the newest 300 lines'))
    const row = o('div', 'qt-row')
    const picker = o('input')
    picker.type = 'month'
    picker.value = snapshot.month
    picker.setAttribute('aria-label', tx('Month'))
    picker.addEventListener('change', () => {
      month = picker.value
      load()
    })
    row.append(picker)
    p.append(row)
    const board = o('table', 'qt-table small')
    const head = o('tr')
    for (const c of [tx('Time'), tx('Who'), tx('Action'), tx('Device IP'), tx('Details')]) head.append(o('th', '', c))
    board.append(head)
    for (const x of snapshot.auditLog) {
      const { at, actor, role, clientIp, action, path, device, ...rest } = x
      const h = o('tr', /tu-choi|sai|^loi$/.test(action || '') ? 'qt-bad-row' : '')
      h.append(o('td', '', String(at || '').replace('T', ' ').slice(0, 19)), o('td', '', actor || '—'), o('td', '', ACTION_NAMES[action] || action || '—'), o('td', '', clientIp || '—'), o('td', '', Object.entries(rest).map(([k, v]) => `${k}: ${v && typeof v === 'object' ? JSON.stringify(v) : v}`).join(' · ')))
      board.append(h)
    }
    if (!snapshot.auditLog.length) p.append(o('small', '', tx('Nothing this month.')))
    else p.append(addLabel(board))
    return p
  }

  // Menu bar icon for managers: the installers come from this server with its address already inside; the code the icon shows is approved in TV screens.
  // Biểu tượng thanh menu cho quản lý: gói cài lấy từ máy chủ này, đã có sẵn địa chỉ; mã biểu tượng hiện ra được duyệt ở mục Màn hình TV.
  function menubarSection() {
    const p = section(tx('Menu bar icon'), tx('For managers: who is waiting for an answer, without opening the board'))
    const row = o('div', 'qt-row')
    // one button per system; a system with two kinds of file gets a drop-down, the recommended file first
    // mỗi hệ điều hành một nút; hệ có hai kiểu file thì thành menu xổ xuống, file nên dùng đứng đầu
    const mac = [], windows = []
    // the built macOS app also comes as a disk image when the server has one: drag it into Applications
    // app macOS đã đóng gói có thêm bản ổ đĩa ảo khi máy chủ có: kéo vào Applications
    // in a drop-down each entry is the file's own name, the recommended one marked
    // trong menu xổ, mỗi dòng là chính tên file, file nên dùng có ghi chú
    const pick = (name, recommended) => recommended ? tx('{file} (recommended)', { file: name }) : name
    if (snapshot.menubarDmg) mac.push([pick('AI-Worker.dmg', true), '/menubar/install-mac.dmg', 'AI-Worker.dmg'])
    mac.push([snapshot.menubarDmg ? pick('AI-Worker-mac.zip') : tx('Download for macOS'), '/menubar/install-mac.zip', 'AI-Worker-mac.zip'])
    // Windows: AI Worker.msi when the server has it; the .zip (a .bat file) is the old installer, kept as a fallback
    // Windows: gói AI Worker.msi khi máy chủ có; gói .zip (file .bat) là bản cũ, để dự phòng
    if (snapshot.menubarMsi) windows.push([pick('AI-Worker.msi', true), '/menubar/install-windows.msi', 'AI-Worker.msi'])
    windows.push([snapshot.menubarMsi ? pick('AI-Worker-windows.zip') : tx('Download for Windows'), '/menubar/install-windows.zip', 'AI-Worker-windows.zip'])
    const groups = [[tx('Download for macOS'), mac], [tx('Download for Windows'), windows],
      [tx('Download for Ubuntu (.deb)'), [[tx('Download for Ubuntu (.deb)'), '/menubar/install-ubuntu.deb', 'ai-worker-menubar.deb']]]]
    // the browser extension for managers, when packaging/build-extension.sh put it on the server
    // tiện ích trình duyệt cho quản lý, khi packaging/build-extension.sh đã đưa lên máy chủ
    if (snapshot.menubarExtension) groups.push(['', [[tx('Extension for Chrome, Edge'), '/menubar/extension.zip', 'AI-Worker-extension.zip']]])
    const fileLink = (cls, [label, file, name]) => {
      const link = o('a', cls, label)
      link.href = file
      link.download = name
      return link
    }
    for (const [title, list] of groups) {
      if (list.length === 1) { row.append(fileLink('qt-button', list[0])); continue }
      const menu = o('details', 'qt-menu')
      menu.append(o('summary', 'qt-button', title + ' ▾'))
      const box = o('div', 'qt-menu-list')
      for (const item of list) box.append(fileLink('', item))
      menu.append(box)
      // close it after a pick, and when another menu opens
      // đóng sau khi chọn, và khi mở menu khác
      box.addEventListener('click', () => { menu.open = false })
      menu.addEventListener('toggle', () => {
        if (!menu.open) return
        for (const other of row.querySelectorAll('.qt-menu[open]')) if (other !== menu) other.open = false
        // near the right edge (a phone), open towards the left so the list stays on screen
        // sát mép phải (điện thoại) thì mở về bên trái để menu không lọt ra ngoài màn hình
        box.classList.remove('to-left')
        if (box.getBoundingClientRect().right > document.documentElement.clientWidth - 12) box.classList.add('to-left')
      })
      row.append(menu)
    }
    p.append(row)
    const steps = o('ol', 'qt-steps')
    for (const text of [
      tx('Send the file to the manager. Only install a file downloaded from this page; do not open an installer that came by email, chat or USB, even if the name looks right.'),
      // with the built app the Mac files hold the app itself; without it the .zip holds an installer
      // có app đã dựng thì file cho Mac chứa chính app; không có thì file .zip chứa file cài
      snapshot.menubarDmg
        ? tx('macOS: open the .zip or .dmg, drag the app into Applications and open it. Updating: first open the window from the menu bar, go to Settings and click Quit, then drag and pick Replace. If it is blocked the first time: System Settings > Privacy & Security > Open Anyway. To remove it: Settings > Uninstall, not dragging it to the Trash, so it also stops starting at login.')
        : tx('macOS: unzip and open the install file inside. If it is blocked the first time: System Settings > Privacy & Security > Open Anyway.'),
      snapshot.menubarMsi
        ? tx('Windows: open AI-Worker.msi and click Install (no admin rights needed). If Windows says "Windows protected your PC", click More info, then Run anyway, only for a file downloaded from this page. Installing a new version over the old one works the same way and keeps the pairing. To remove it: Settings > Apps > AI Worker, or Uninstall in the window\'s Settings. Use the .zip only when the .msi does not install.')
        : tx('Windows: unzip and double-click the .bat file inside.'),
      tx('Ubuntu: open the .deb with App Center, or run sudo apt install ./ai-worker-menubar.deb, then log out and back in.'),
      tx('The manager clicks the icon and pairs it with their own account and 6-digit code; nobody needs to approve. A manager without an account: enter the code shown on the icon in TV screens above.'),
      tx('Within a minute the icon shows how many people are waiting; a click opens the small window.'),
      ...(snapshot.menubarExtension ? [tx('Chrome, Edge: unzip somewhere it will stay (for example Documents), open chrome://extensions (edge://extensions), turn on Developer mode, click Load unpacked and pick the AI-Worker-extension folder. Click the icon, enter this board\'s address and read the 8-digit code to an admin, who approves it in TV screens above.')] : []),
    ]) steps.append(o('li', '', text))
    p.append(steps)
    p.append(o('small', '', tx('A paired computer sees short names and costs, like a wall screen. Each account may pair 2 computers; deleting the account or ending its sessions removes them.')))
    return p
  }

  function render() {
    const head = o('header', 'qt-head')
    const backLink = o('a', 'qt-button', tx('← Back to board'))
    backLink.href = '/'
    head.append(o('h1', '', tx('Admin')), o('span', '', viewerName), I18n.switcher(), backLink)
    const column = o('div', 'qt-column')
    column.append(accountsSection(), tvSection(), menubarSection(), locationsSection(), teamSection(), sessionsSection(), auditSection())
    root.replaceChildren(head, notice, column)
  }

  async function load() {
    const r = await fetch('/admin/data' + (month ? '?month=' + month : ''), { cache: 'no-store', credentials: 'same-origin' })
    if (r.status === 401 || r.status === 403) return location.reload()
    snapshot = await r.json()
    // While typing, with a box open or a key on show, leave it as it is; the next action will redraw.
    // Đang gõ, đang mở hộp hay đang hiện khoá thì giữ nguyên; lần thao tác sau sẽ vẽ lại.
    render()
  }
  // Opened from the QR code on the TV: remove the code from the address bar and open the request straight away; approving is still up to the person.
  // Mở từ mã QR trên TV: bỏ mã khỏi thanh địa chỉ rồi mở luôn yêu cầu; việc duyệt vẫn do người bấm.
  function codeFromLink() {
    const m = /^#pair=(\d{8})$/.exec(location.hash)
    if (!m) return ''
    history.replaceState(null, '', location.pathname)
    return m[1]
  }
  const initialCode = codeFromLink()
  try {
    sessionStorage.removeItem('pair')
  } catch {
    // The browser blocks storage: no harm.
    // Trình duyệt chặn lưu trữ: không sao.
  }
  load().then(() => initialCode && viewTv(initialCode)).catch(() => toast(tx('Could not load the data'), true))
  addEventListener('hashchange', () => {
    const count = codeFromLink()
    if (count && snapshot) viewTv(count)
  })
  setInterval(() => {
    const focused = document.activeElement
    if (newSecret || tvRequest || dialog.open || (focused && /^(INPUT|SELECT)$/.test(focused.tagName))) return
    load().catch(() => toast(tx('Connection lost'), true))
  }, 30000)
})()
