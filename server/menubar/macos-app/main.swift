// Menu bar app for managers on macOS: the logo with the number of people waiting, a fixed panel with a blurred background.
// Biểu tượng thanh menu cho quản lý trên macOS: logo kèm số người đang chờ, khung cố định có nền mờ.
// The panel shows the server's /mini page, so its design lives on the server; this app only pairs, counts and notifies.
// Khung hiện trang /mini của máy chủ, nên giao diện nằm trên máy chủ; app chỉ ghép máy, đếm số và báo tin.
// Build: build.sh next to this file (swiftc from Apple's Command Line Tools, no Xcode needed).
// Đóng gói: build.sh cạnh file này (swiftc trong Command Line Tools của Apple, không cần Xcode).
import AppKit
import ServiceManagement
import UserNotifications
import WebKit

// MARK: settings
// MARK: cài đặt

/// config.json inside the app: the board's address and the language, written in when the app is built.
/// config.json trong app: địa chỉ bảng và ngôn ngữ, ghi vào lúc đóng gói app.
struct Config: Decodable {
  let server: String
  let lang: String?
  let name: String?
  let dialect: String?
}

/// Route, cookie and field names of the server: the public AI Worker server, or a company server that names them in Vietnamese.
/// Tên đường dẫn, cookie và trường của máy chủ: máy chủ AI Worker công khai, hoặc máy chủ công ty đặt tên bằng tiếng Việt.
struct Names {
  let requestCode, poll, state, handoff, mini, pair, board, unpair: String
  let session, pending: String
  let code, status, done, waitingStatus: String
  let waiting, name, since, notify, notifyMinutes: String
  static let english = Names(requestCode: "/tv/request-code", poll: "/tv/poll", state: "/mini/state", handoff: "/mini/handoff", mini: "/mini",
                             pair: "/mini/pair", board: "/board", unpair: "/mini/unpair", session: "session", pending: "tv-pending", code: "code", status: "status",
                             done: "done", waitingStatus: "pending", waiting: "waiting", name: "name", since: "since", notify: "notify",
                             notifyMinutes: "notifyMinutes")
  static let vietnamese = Names(requestCode: "/tv/xin-ma", poll: "/tv/hoi", state: "/mini/trang-thai", handoff: "/mini/doi-ma", mini: "/mini",
                                pair: "/mini/ghep", board: "/bang", unpair: "/mini/bo-ghep", session: "phien", pending: "tv-cho", code: "ma", status: "trangThai",
                                done: "xong", waitingStatus: "cho", waiting: "dangCho", name: "ten", since: "tu", notify: "baoTin",
                                notifyMinutes: "baoSauPhut")
}

let bundle = Bundle.main
let config: Config? = {
  guard let url = bundle.url(forResource: "config", withExtension: "json"), let data = try? Data(contentsOf: url) else { return nil }
  return try? JSONDecoder().decode(Config.self, from: data)
}()
let server: String = {
  let s = (config?.server ?? "").trimmingCharacters(in: CharacterSet(charactersIn: "/"))
  // only HTTPS, or this computer while testing: the host itself must be localhost, 127.0.0.1 or ::1, not a name that starts with it
  // chỉ HTTPS, hoặc chính máy này khi thử: máy chủ phải đúng là localhost, 127.0.0.1 hoặc ::1, không phải tên bắt đầu bằng mấy chữ đó
  guard let parts = URLComponents(string: s), let host = parts.host, !host.isEmpty, parts.user == nil, parts.password == nil else { return "" }
  if parts.scheme == "https" { return s }
  return parts.scheme == "http" && ["localhost", "127.0.0.1", "::1", "[::1]"].contains(host) ? s : ""
}()
/// Where a link leaving the panel may go: an https page, or this server's own pages when it is this computer over http.
/// Đường dẫn rời khỏi khung được đi đâu: trang https, hoặc trang của chính máy chủ này khi nó là máy này qua http.
func opensInBrowser(_ url: URL) -> Bool {
  url.scheme == "https" || (!server.isEmpty && url.scheme == "http" && url.absoluteString.hasPrefix(server + "/"))
}
let appName = config?.name ?? "AI Worker"
let N = config?.dialect == "vi" ? Names.vietnamese : Names.english
/// The language chosen in Settings wins; then the one fixed when built; otherwise the Mac's own language.
/// Ngôn ngữ chọn trong Cài đặt được ưu tiên; rồi tới ngôn ngữ cố định lúc đóng gói; không thì theo ngôn ngữ của máy Mac.
func loadVietnamese() -> [String: String] {
  let chosen = readFile("lang")
  let lang = chosen.isEmpty ? (config?.lang ?? "auto") : chosen
  let wantsVietnamese = lang == "vi" || (lang == "auto" && (Locale.preferredLanguages.first ?? "").hasPrefix("vi"))
  guard wantsVietnamese, let url = bundle.url(forResource: "vi", withExtension: "json"), let data = try? Data(contentsOf: url) else { return [:] }
  return (try? JSONSerialization.jsonObject(with: data)) as? [String: String] ?? [:]
}
var vietnamese: [String: String] = [:]
func tx(_ text: String, _ params: [String: String] = [:]) -> String {
  var out = vietnamese[text] ?? text
  for (k, v) in params { out = out.replacingOccurrences(of: "{\(k)}", with: v) }
  return out
}

/// The session and the pending pairing key live in a folder only this user can read.
/// Phiên và khoá ghép đang chờ nằm trong thư mục chỉ người dùng này đọc được.
/// The round badge in a notification: the first letter of the person's name on a colour fixed by the name (same rule as the Windows and Ubuntu apps).
/// macOS keeps the app's own logo on the left, so the badge shows as the picture on the right.
/// Ô tròn trong thông báo: chữ cái đầu của tên người trên một màu cố định theo tên (cùng quy tắc với app Windows và Ubuntu).
/// macOS giữ logo của app ở bên trái, nên ô tròn hiện thành ảnh bên phải.
let avatarColors: [UInt32] = [0xe17076, 0xfaa774, 0xa695e7, 0x7bc862, 0x6ec9cb, 0x65aadd, 0xee7aae]
func avatarFile(_ name: String) -> UNNotificationAttachment? {
  let letter = name.first(where: { $0.isLetter || $0.isNumber }).map { String($0).uppercased() } ?? "?"
  let rgb = avatarColors[name.utf8.reduce(0) { $0 + Int($1) } % avatarColors.count]
  let size: CGFloat = 128
  let image = NSImage(size: NSSize(width: size, height: size), flipped: false) { rect in
    NSColor(red: CGFloat((rgb >> 16) & 255) / 255, green: CGFloat((rgb >> 8) & 255) / 255, blue: CGFloat(rgb & 255) / 255, alpha: 1).setFill()
    NSBezierPath(ovalIn: rect).fill()
    let text = NSAttributedString(string: letter, attributes: [.font: NSFont.systemFont(ofSize: size * 0.5, weight: .semibold), .foregroundColor: NSColor.white])
    let box = text.size()
    text.draw(at: NSPoint(x: (size - box.width) / 2, y: (size - box.height) / 2))
    return true
  }
  guard let tiff = image.tiffRepresentation, let png = NSBitmapImageRep(data: tiff)?.representation(using: .png, properties: [:]) else { return nil }
  // the system moves the file away when it takes it, so each notification gets its own copy
  // hệ thống chuyển file đi khi nhận, nên mỗi thông báo một bản riêng
  let file = FileManager.default.temporaryDirectory.appendingPathComponent("avatar-\(UUID().uuidString).png")
  guard (try? png.write(to: file)) != nil else { return nil }
  return try? UNNotificationAttachment(identifier: "avatar", url: file, options: nil)
}

let dataDir: URL = {
  let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent(appName + " Menu Bar", isDirectory: true)
  try? FileManager.default.createDirectory(at: base, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
  return base
}()
func readFile(_ name: String) -> String {
  (try? String(contentsOf: dataDir.appendingPathComponent(name), encoding: .utf8))?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
}
func writePrivate(_ name: String, _ text: String) {
  let url = dataDir.appendingPathComponent(name)
  FileManager.default.createFile(atPath: url.path, contents: Data(text.utf8), attributes: [.posixPermissions: 0o600])
}
func removeFile(_ name: String) { try? FileManager.default.removeItem(at: dataDir.appendingPathComponent(name)) }

// MARK: talking to the server
// MARK: nói chuyện với máy chủ

/// No redirects are followed and no cookies are kept by URLSession: the session goes only in the header this app writes.
/// Không đi theo chuyển hướng và URLSession không giữ cookie: phiên chỉ đi trong header do app tự ghi.
final class NoRedirect: NSObject, URLSessionTaskDelegate {
  func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                  newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) { completionHandler(nil) }
}
let http: URLSession = {
  let c = URLSessionConfiguration.ephemeral
  c.httpCookieStorage = nil
  c.httpShouldSetCookies = false
  c.timeoutIntervalForRequest = 8
  return URLSession(configuration: c, delegate: NoRedirect(), delegateQueue: nil)
}()
struct Reply { let status: Int; let json: [String: Any]; let cookies: [String: String] }
/// For actions that require an Origin header (unpairing): the server's own address.
/// Cho thao tác bắt buộc có header Origin (bỏ ghép): chính địa chỉ máy chủ.
func callWithOrigin(_ method: String, _ path: String, cookie: String) async -> Reply? {
  await call(method, path, cookie: cookie, origin: server)
}
func call(_ method: String, _ path: String, cookie: String = "", origin: String = "") async -> Reply? {
  guard let url = URL(string: server + path) else { return nil }
  var req = URLRequest(url: url)
  req.httpMethod = method
  // the server recognises the menu bar by these words: "menu bar" (English server) or "thanh menu" (Vietnamese server)
  // máy chủ nhận ra thanh menu qua mấy chữ này: "menu bar" (máy chủ tiếng Anh) hoặc "thanh menu" (máy chủ tiếng Việt)
  req.setValue(config?.dialect == "vi" ? "\(appName) thanh menu app (macOS)" : "\(appName) menu bar app (macOS)", forHTTPHeaderField: "User-Agent")
  if !cookie.isEmpty { req.setValue(cookie, forHTTPHeaderField: "Cookie") }
  if !origin.isEmpty { req.setValue(origin, forHTTPHeaderField: "Origin") }
  if method == "POST" { req.httpBody = Data() }
  guard let (data, resp) = try? await http.data(for: req), let h = resp as? HTTPURLResponse else { return nil }
  var cookies: [String: String] = [:]
  for (k, v) in h.allHeaderFields where (k as? String)?.lowercased() == "set-cookie" {
    for part in String(describing: v).components(separatedBy: ",") {
      let first = part.components(separatedBy: ";")[0].trimmingCharacters(in: .whitespaces)
      if let eq = first.firstIndex(of: "=") { cookies[String(first[..<eq])] = String(first[first.index(after: eq)...]) }
    }
  }
  let json = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
  return Reply(status: h.statusCode, json: json, cookies: cookies)
}

// MARK: the app
// MARK: ứng dụng

enum State { case ok, long, off, pair, setup }

final class App: NSObject, NSApplicationDelegate, NSPopoverDelegate, WKNavigationDelegate, WKScriptMessageHandler, WKUIDelegate {
  let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
  let popover = NSPopover()
  let web: WKWebView
  var state: State = .setup
  var count = 0
  var pairCode = ""
  var notified = Set<String>()
  var timer: Timer?

  override init() {
    let conf = WKWebViewConfiguration()
    conf.websiteDataStore = .default()
    conf.applicationNameForUserAgent = "AIWorkerApp/1"
    // the page reports its height whenever it changes (the lists fill in after the page loads), and the panel follows
    // trang báo chiều cao mỗi khi đổi (danh sách được điền sau khi trang tải xong), và khung co giãn theo
    let measure = "(function(){var last=0;function send(){var m=document.querySelector('main');var h=Math.ceil((m?m.getBoundingClientRect().bottom:document.body.scrollHeight)+14);" +
      "if(h!==last){last=h;window.webkit.messageHandlers.size.postMessage(h)}}new ResizeObserver(send).observe(document.documentElement);send()})()"
    conf.userContentController.addUserScript(WKUserScript(source: measure, injectionTime: .atDocumentEnd, forMainFrameOnly: true))
    web = WKWebView(frame: NSRect(x: 0, y: 0, width: 360, height: 480), configuration: conf)
    super.init()
    conf.userContentController.add(self, name: "size")
    conf.userContentController.add(self, name: "app")
  }

  func applicationDidFinishLaunching(_ note: Notification) {
    vietnamese = loadVietnamese()
    // a blurred see-through background behind a transparent page
    // nền mờ nhìn xuyên phía sau một trang trong suốt
    let blur = NSVisualEffectView(frame: web.frame)
    blur.material = .popover
    blur.blendingMode = .behindWindow
    blur.state = .active
    web.setValue(false, forKey: "drawsBackground")
    web.navigationDelegate = self
    web.uiDelegate = self
    web.autoresizingMask = [.width, .height]
    blur.addSubview(web)
    let holder = NSViewController()
    holder.view = blur
    popover.contentViewController = holder
    popover.contentSize = NSSize(width: 360, height: 480)
    popover.behavior = .transient
    popover.animates = true
    popover.delegate = self
    item.button?.target = self
    item.button?.action = #selector(clicked)
    item.button?.sendAction(on: [.leftMouseUp, .rightMouseUp])
    UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, _ in }
    // the first launch turns on start-at-login once; after that the person's choice in Settings stays
    // lần mở đầu tiên bật tự chạy khi đăng nhập một lần; sau đó giữ lựa chọn của người dùng trong Cài đặt
    if readFile("login-set").isEmpty {
      try? SMAppService.mainApp.register()
      writePrivate("login-set", "1")
    }
    draw()
    Task { await refresh() }
    timer = Timer.scheduledTimer(withTimeInterval: 60, repeats: true) { [weak self] _ in Task { await self?.refresh() } }
  }

  /// The panel never comes loose: it stays under the icon.
  /// Khung không bao giờ tách ra: luôn nằm dưới biểu tượng.
  func popoverShouldDetach(_ popover: NSPopover) -> Bool { false }

  /// The panel takes the height the page reports, between 220 and 640 points, so there is no empty space and nothing is cut off.
  /// Khung lấy chiều cao trang báo về, từ 220 tới 640 điểm, để không thừa khoảng trống và không bị cắt.
  func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) {
    if message.name == "app", let body = message.body as? [String: Any], let action = body["action"] as? String {
      // only the panel's own page, in the main frame, may ask the app for anything (removing the app, start at login)
      // chỉ chính trang của khung, ở khung chính, mới được nhờ app làm gì (gỡ app, tự chạy khi đăng nhập)
      guard !server.isEmpty, message.frameInfo.isMainFrame,
            (message.frameInfo.request.url?.absoluteString ?? "").hasPrefix(server + N.mini) else { return }
      return appAction(action, body)
    }
    guard message.name == "size", let h = message.body as? Double ?? (message.body as? Int).map(Double.init) else { return }
    // grows or shrinks smoothly, like the Windows and Ubuntu windows (about 0.24 s, slowing at the end)
    // co giãn từ từ, như khung Windows và Ubuntu (khoảng 0,24 giây, chậm dần về cuối)
    NSAnimationContext.runAnimationGroup { ctx in
      ctx.duration = 0.24
      ctx.timingFunction = CAMediaTimingFunction(name: .easeOut)
      ctx.allowsImplicitAnimation = true
      popover.contentSize = NSSize(width: 360, height: min(max(h, 220), 640))
    }
  }

  /// Links that leave the panel (Open board) go to the normal browser; the panel only shows this server's pages.
  /// Đường dẫn rời khỏi khung (Mở bảng) mở bằng trình duyệt thường; khung chỉ hiện trang của máy chủ này.
  func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
    guard let url = action.request.url else { return decisionHandler(.cancel) }
    let mine = url.absoluteString.hasPrefix(server + N.mini)
    if action.targetFrame == nil || !mine {
      if opensInBrowser(url) { NSWorkspace.shared.open(url) }
      return decisionHandler(.cancel)
    }
    decisionHandler(.allow)
  }
  func webView(_ webView: WKWebView, createWebViewWith c: WKWebViewConfiguration, for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
    // a new window from the page opens in the browser only for a web address, never another scheme (file:, a custom app link)
    // cửa sổ mới từ trang chỉ mở bằng trình duyệt khi là địa chỉ web, không bao giờ là kiểu khác (file:, đường dẫn gọi app)
    if let url = action.request.url, opensInBrowser(url) { NSWorkspace.shared.open(url) }
    return nil
  }

  /// What the Settings tab asks of the app: its start-at-login state, switching it, and removing the app.
  /// Những gì thẻ Cài đặt nhờ app: trạng thái tự chạy khi đăng nhập, bật tắt nó, và gỡ app.
  func appAction(_ action: String, _ body: [String: Any]) {
    switch action {
    case "hello":
      sendState()
    case "login":
      if body["on"] as? Bool == true { try? SMAppService.mainApp.register() } else { try? SMAppService.mainApp.unregister() }
      sendState()
    case "lang":
      if let code = body["value"] as? String, code == "vi" || code == "en" {
        writePrivate("lang", code)
        vietnamese = loadVietnamese()
        draw()
      }
    case "uninstall":
      Task { await uninstall() }
    case "quit":
      NSApp.terminate(nil)
    default:
      break
    }
  }
  func sendState() {
    web.evaluateJavaScript("window.appState && window.appState({login: \(SMAppService.mainApp.status == .enabled)})", completionHandler: nil)
  }

  /// Unpair on the server, forget the session, stop starting at login, move the app to the Trash (it can be put back), quit.
  /// Bỏ ghép trên máy chủ, quên phiên, thôi tự chạy khi đăng nhập, đưa app vào Thùng rác (khôi phục được), thoát.
  @MainActor func uninstall() async {
    let token = readFile("session")
    if !token.isEmpty { _ = await callWithOrigin("POST", N.unpair, cookie: N.session + "=" + token) }
    try? await SMAppService.mainApp.unregister()
    try? FileManager.default.removeItem(at: dataDir)
    try? FileManager.default.trashItem(at: bundle.bundleURL, resultingItemURL: nil)
    NSApp.terminate(nil)
  }

  /// window.confirm in the panel, shown as a normal macOS question.
  /// window.confirm trong khung, hiện thành hộp hỏi bình thường của macOS.
  func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
    let alert = NSAlert()
    alert.messageText = message
    alert.addButton(withTitle: "OK")
    alert.addButton(withTitle: tx("Cancel"))
    NSApp.activate(ignoringOtherApps: true)
    completionHandler(alert.runModal() == .alertFirstButtonReturn)
  }

  @objc func clicked() {
    if NSApp.currentEvent?.type == .rightMouseUp { return showMenu() }
    if popover.isShown { return popover.performClose(nil) }
    Task { await openPanel() }
  }

  func showMenu() {
    let menu = NSMenu()
    if !server.isEmpty { menu.addItem(withTitle: tx("Open board"), action: #selector(openBoard), keyEquivalent: "").target = self }
    let login = menu.addItem(withTitle: tx("Start at login"), action: #selector(toggleLogin), keyEquivalent: "")
    login.target = self
    login.state = SMAppService.mainApp.status == .enabled ? .on : .off
    menu.addItem(.separator())
    menu.addItem(withTitle: tx("Quit"), action: #selector(NSApplication.terminate(_:)), keyEquivalent: "")
    item.menu = menu
    item.button?.performClick(nil)
    item.menu = nil
  }
  @objc func openBoard() { if let u = URL(string: server + N.board) { NSWorkspace.shared.open(u) } }
  @objc func toggleLogin() {
    if SMAppService.mainApp.status == .enabled { try? SMAppService.mainApp.unregister() } else { try? SMAppService.mainApp.register() }
  }

  @MainActor func openPanel() async {
    guard let button = item.button else { return }
    var target = ""
    if state == .pair, pairCode.range(of: "^[0-9]{8}$", options: .regularExpression) != nil {
      target = "\(server)\(N.pair)#c=\(pairCode)"
    } else if state == .ok || state == .long {
      let token = readFile("session")
      // a one-time code lets the panel take this computer's session; the code dies once used
      // mã dùng một lần để khung nhận phiên của máy này; dùng xong là hết
      // the code goes into the address only when it looks like one the server issues
      // mã chỉ vào địa chỉ khi đúng dạng máy chủ cấp
      if let r = await call("POST", N.handoff, cookie: N.session + "=" + token), let code = r.json[N.code] as? String ?? r.json["code"] as? String,
         code.range(of: "^[A-Za-z0-9_-]{8,128}$", options: .regularExpression) != nil {
        target = "\(server)\(N.mini)?h=\(code)"
      } else {
        target = server + N.mini
      }
    }
    if target.isEmpty || server.isEmpty {
      web.loadHTMLString("<body style='font:14px -apple-system;color:#888;padding:20px;background:transparent'>\(tx(server.isEmpty ? "Not set up: run the installer again" : "Cannot reach the server"))</body>", baseURL: nil)
    } else if let u = URL(string: target) {
      web.load(URLRequest(url: u))
    }
    popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
    popover.contentViewController?.view.window?.makeKey()
  }

  // MARK: one round every minute
  // MARK: mỗi phút một lượt

  @MainActor func refresh() async {
    guard !server.isEmpty else { state = .setup; return draw() }
    let token = readFile("session")
    if token.isEmpty { return await pairing() }
    guard let r = await call("GET", N.state, cookie: N.session + "=" + token) else { state = .off; return draw() }
    if r.status == 401 || r.status == 403 {
      removeFile("session")
      return await pairing()
    }
    guard r.status == 200 else { state = .off; return draw() }
    let waiting = r.json[N.waiting] as? [[String: Any]] ?? []
    let notify = r.json[N.notify] as? Bool ?? true
    let minutes = r.json[N.notifyMinutes] as? Int ?? 10
    let now = Date().timeIntervalSince1970 * 1000
    var long = false
    var current = Set<String>()
    for p in waiting {
      guard let since = p[N.since] as? Double else { continue }
      let name = p[N.name] as? String ?? "?"
      let key = "\(name)|\(Int(since))"
      current.insert(key)
      let waited = Int((now - since) / 60000)
      if waited >= minutes {
        long = true
        if notify && !notified.contains(key) {
          notified.insert(key)
          // the window is open: the person already sees the list, so no notification on top of it
          // khung đang mở: người dùng đã thấy danh sách, khỏi bật thông báo đè lên
          if popover.isShown { continue }
          let content = UNMutableNotificationContent()
          content.title = tx("Waiting for an answer")
          content.body = tx("{name} has waited {n} minutes", ["name": name, "n": String(waited)])
          if let badge = avatarFile(name) { content.attachments = [badge] }
          try? await UNUserNotificationCenter.current().add(UNNotificationRequest(identifier: key, content: content, trigger: nil))
        }
      }
    }
    notified.formIntersection(current)
    count = waiting.count
    state = long ? .long : .ok
    draw()
  }

  /// Ask for a pairing code, or check whether the code asked for before has been approved.
  /// Xin mã ghép, hoặc hỏi mã đã xin trước đó được duyệt chưa.
  @MainActor func pairing() async {
    let pending = readFile("pending")
    if !pending.isEmpty, let data = pending.data(using: .utf8), let p = try? JSONSerialization.jsonObject(with: data) as? [String: String],
       let key = p["key"], let code = p["code"] {
      if let r = await call("POST", N.poll, cookie: N.pending + "=" + key), r.status == 200 {
        if r.json[N.status] as? String == N.done, let token = r.cookies[N.session], !token.isEmpty {
          writePrivate("session", token)
          removeFile("pending")
          if popover.isShown { popover.performClose(nil) }
          return await refresh()
        }
        if r.json[N.status] as? String == N.waitingStatus { pairCode = code; state = .pair; return draw() }
      }
      removeFile("pending")
    }
    guard let r = await call("POST", N.requestCode), r.status == 200, let code = r.json[N.code] as? String, let key = r.cookies[N.pending] else {
      state = .off
      return draw()
    }
    if let data = try? JSONSerialization.data(withJSONObject: ["key": key, "code": code]), let text = String(data: data, encoding: .utf8) { writePrivate("pending", text) }
    pairCode = code
    state = .pair
    draw()
  }

  // MARK: the icon
  // MARK: biểu tượng

  func draw() {
    guard let button = item.button else { return }
    let logo = bundle.image(forResource: "icon-black")
    logo?.size = NSSize(width: 18, height: 18)
    switch state {
    case .ok:
      logo?.isTemplate = true
      button.image = logo
      button.alphaValue = 1
    case .long:
      // the wait alert is painted into the logo in the board's blue
      // báo chờ lâu được tô thẳng vào logo bằng màu xanh lam của bảng
      button.image = logo.map { tint($0, NSColor(srgbRed: 26 / 255, green: 86 / 255, blue: 200 / 255, alpha: 1)) }
      button.alphaValue = 1
    case .off, .setup:
      logo?.isTemplate = true
      button.image = logo
      button.alphaValue = 0.4
    case .pair:
      button.image = NSImage(systemSymbolName: "person.badge.key", accessibilityDescription: tx("Pairing code"))
      button.alphaValue = 1
    }
    button.title = (state == .ok || state == .long) && count > 0 ? " \(count)" : ""
    button.imagePosition = .imageLeft
    button.toolTip = state == .off ? tx("Cannot reach the server") : state == .pair ? tx("Pair with my account") : appName
  }

  func tint(_ image: NSImage, _ color: NSColor) -> NSImage {
    let out = NSImage(size: image.size)
    out.lockFocus()
    image.draw(in: NSRect(origin: .zero, size: image.size))
    color.set()
    NSRect(origin: .zero, size: image.size).fill(using: .sourceAtop)
    out.unlockFocus()
    out.isTemplate = false
    return out
  }
}

let app = NSApplication.shared
let delegate = App()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
