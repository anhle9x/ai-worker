// The AI Worker icon next to the clock for managers on Windows: how many people wait, a notification when someone waits long, the small /mini window.
// Replaces the old PowerShell icon (ai-worker-tray.ps1): one .exe, no black window, no ExecutionPolicy Bypass, no C# compiled at run time.
// Settings stay in %APPDATA%\ai-worker like before, so a paired computer stays paired; the session file is encrypted with DPAPI (only this Windows account opens it).
// Arguments: --open (open the window in the running copy; notifications use it), --round (one round, prints the state, for tests), --test-notify (notify-once test).
// Biểu tượng AI Worker cạnh đồng hồ cho quản lý trên Windows: số người đang chờ, thông báo khi có người chờ lâu, khung nhỏ /mini.
// Thay bản PowerShell cũ (ai-worker-tray.ps1): một file .exe, không cửa sổ đen, không ExecutionPolicy Bypass, không dịch C# lúc chạy.
// Cài đặt vẫn ở %APPDATA%\ai-worker như trước, nên máy đã ghép giữ nguyên ghép; file phiên được mã hoá bằng DPAPI (chỉ tài khoản Windows này mở được).
// Tham số: --open (mở khung ở bản đang chạy, do thông báo gọi), --round (một lượt, in trạng thái, cho bài thử), --test-notify (bài thử báo một lần).
using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Management;
using System.Net.Http;
using System.Runtime.InteropServices;
using System.Security;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Win32;

namespace AIWorker
{
    // The result of one round with the server
    // Kết quả một lượt hỏi máy chủ
    class Round
    {
        public string State = "off"; // ok | long | off | pair | setup
        public int Count;
        public string Text = "";
        public string Url = "";
        public string Code = "";
        public List<Waiter> Waiting = new List<Waiter>();
        public bool Notify = true;
        public int NotifyMinutes = 10;
    }

    class Waiter { public string Name = ""; public long Since; }

    // The part without a window: settings, words, pairing, asking the server, who was notified. Kept apart so tests run it without the tray.
    // Phần không có giao diện: cài đặt, chữ, ghép máy, hỏi máy chủ, đã báo ai. Tách riêng để bài thử chạy được không cần khay.
    class Core
    {
        public static readonly JavaScriptSerializer Json = new JavaScriptSerializer();
        public readonly string ConfigDir;
        public readonly string Server;
        public string Lang;
        readonly Dictionary<string, string> vi = new Dictionary<string, string>();
        readonly HttpClient client;
        public string LastError = "";

        public string ConfigFile => Path.Combine(ConfigDir, "menubar.json");
        public string SessionFile => Path.Combine(ConfigDir, "menubar-session");
        public string PendingFile => Path.Combine(ConfigDir, "menubar-pending.json");
        public string NotifiedFile => Path.Combine(ConfigDir, "menubar-notified.json");
        public static string InstallDir => AppDomain.CurrentDomain.BaseDirectory;

        public Core()
        {
            var env = Environment.GetEnvironmentVariable("AI_WORKER_MENUBAR_DIR");
            ConfigDir = string.IsNullOrEmpty(env) ? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "ai-worker") : env;
            var cfg = ReadConfig();
            Server = ReadServer(cfg).TrimEnd('/');
            Lang = cfg.TryGetValue("lang", out var l) ? Convert.ToString(l) : (CultureInfo.CurrentUICulture.Name.StartsWith("vi") ? "vi" : "en");
            // the language goes into the window's address, so only the two known codes are kept
            // ngôn ngữ đi vào địa chỉ của khung, nên chỉ giữ hai mã đã biết
            if (Lang != "en" && Lang != "vi") Lang = "en";
            // Vietnamese words: menubar-vi.json in the settings folder, else vi.json next to the app
            // Chữ tiếng Việt: menubar-vi.json trong thư mục cài đặt, không thì vi.json cạnh app
            foreach (var p in new[] { Path.Combine(ConfigDir, "menubar-vi.json"), Path.Combine(InstallDir, "vi.json") })
            {
                try
                {
                    if (!File.Exists(p)) continue;
                    if (Json.DeserializeObject(File.ReadAllText(p, Encoding.UTF8)) is Dictionary<string, object> d)
                        foreach (var kv in d) vi[kv.Key] = Convert.ToString(kv.Value);
                    break;
                }
                catch { }
            }
            var handler = new HttpClientHandler { UseCookies = false, AllowAutoRedirect = false };
            client = new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(8) };
            client.DefaultRequestHeaders.UserAgent.ParseAdd("AIWorkerMenuBar/2.0 (Windows)");
        }

        public string T(string text) => Lang == "vi" && vi.TryGetValue(text, out var v) ? v : text;

        Dictionary<string, object> ReadConfig()
        {
            try
            {
                if (File.Exists(ConfigFile) && Json.DeserializeObject(File.ReadAllText(ConfigFile, Encoding.UTF8)) is Dictionary<string, object> d) return d;
            }
            catch { }
            return new Dictionary<string, object>();
        }

        // The server address: the .msi writes it into the user's key (padded with spaces); the old installer and the tests use menubar.json
        // Địa chỉ máy chủ: file .msi ghi vào khoá của người dùng (có dấu cách đệm cuối); file cài cũ và bài thử dùng menubar.json
        string ReadServer(Dictionary<string, object> cfg)
        {
            if (string.IsNullOrEmpty(Environment.GetEnvironmentVariable("AI_WORKER_MENUBAR_DIR")))
            {
                try
                {
                    using (var k = Registry.CurrentUser.OpenSubKey(@"Software\AI Worker"))
                    {
                        var v = (k?.GetValue("Server") as string ?? "").Trim();
                        if (v.Length > 0 && !v.StartsWith("AIWORKER-SERVER")) return v;
                    }
                }
                catch { }
            }
            return cfg.TryGetValue("server", out var s) ? (Convert.ToString(s) ?? "").Trim() : "";
        }

        // Saves the chosen language next to the server address; the page is where the person chooses it
        // Lưu ngôn ngữ đã chọn cạnh địa chỉ máy chủ; người dùng chọn trong trang
        public void SaveLang(string code)
        {
            Lang = code;
            SavePrivate(ConfigFile, Json.Serialize(new Dictionary<string, string> { { "server", Server }, { "lang", code } }));
        }

        public void SavePrivate(string path, string text)
        {
            Directory.CreateDirectory(ConfigDir);
            File.WriteAllText(path, text, new UTF8Encoding(false));
        }

        // The pairing session is encrypted with DPAPI for this Windows account; an old plain file is read and written back encrypted
        // Phiên ghép được mã hoá bằng DPAPI theo tài khoản Windows này; file chữ thường cũ được đọc rồi ghi lại dạng mã hoá
        public string ReadSession()
        {
            try
            {
                if (!File.Exists(SessionFile)) return "";
                var text = File.ReadAllText(SessionFile).Trim();
                if (text.StartsWith("dpapi:"))
                    return Encoding.UTF8.GetString(ProtectedData.Unprotect(Convert.FromBase64String(text.Substring(6)), null, DataProtectionScope.CurrentUser));
                if (text.Length > 0) SaveSession(text);
                return text;
            }
            catch { return ""; }
        }

        public void SaveSession(string token)
        {
            var sealedBytes = ProtectedData.Protect(Encoding.UTF8.GetBytes(token), null, DataProtectionScope.CurrentUser);
            SavePrivate(SessionFile, "dpapi:" + Convert.ToBase64String(sealedBytes));
        }

        // https, or http only to this very computer (the host exactly localhost, 127.0.0.1 or ::1): the session never crosses the network in clear
        // https, hoặc http chỉ tới chính máy này (đúng localhost, 127.0.0.1, ::1): phiên không bao giờ đi qua mạng dưới dạng chữ thường
        public static bool ValidServer(string s)
        {
            if (string.IsNullOrEmpty(s) || !Regex.IsMatch(s, @"^[A-Za-z0-9._:/\[\]-]+$")) return false;
            if (!Uri.TryCreate(s, UriKind.Absolute, out var u)) return false;
            if (u.Scheme == "https") return u.Host.Length > 0;
            return u.Scheme == "http" && (u.Host == "localhost" || u.Host == "127.0.0.1" || u.Host == "[::1]");
        }

        class Reply { public int Status; public Dictionary<string, object> Json; public List<string> Cookies = new List<string>(); }

        // One request; never follows a redirect, so a session cannot leak to another host
        // Một yêu cầu; không đi theo chuyển hướng, để phiên không lọt sang máy khác
        Reply Call(string method, string path, string cookie = "")
        {
            var req = new HttpRequestMessage(new HttpMethod(method), new Uri(Server + path));
            if (cookie.Length > 0) req.Headers.Add("Cookie", cookie);
            if (method == "POST") req.Content = new ByteArrayContent(new byte[0]);
            var res = client.SendAsync(req).GetAwaiter().GetResult();
            var body = res.Content.ReadAsStringAsync().GetAwaiter().GetResult();
            var r = new Reply { Status = (int)res.StatusCode };
            if (res.Headers.TryGetValues("Set-Cookie", out var vals)) r.Cookies.AddRange(vals);
            try { r.Json = Json.DeserializeObject(body) as Dictionary<string, object>; } catch { }
            r.Json = r.Json ?? new Dictionary<string, object>();
            return r;
        }

        static string CookieValue(List<string> cookies, string name)
        {
            foreach (var c in cookies)
            {
                var first = c.Split(';')[0];
                var i = first.IndexOf('=');
                if (i > 0 && first.Substring(0, i).Trim() == name && i + 1 < first.Length) return first.Substring(i + 1);
            }
            return "";
        }

        static string Str(Dictionary<string, object> d, string k) => d != null && d.TryGetValue(k, out var v) && v != null ? Convert.ToString(v) : "";
        static long Num(object v) { try { return v == null ? 0 : Convert.ToInt64(v); } catch { return 0; } }
        string PairText(string code) => T("Pairing code") + ": " + code.Substring(0, 4) + "-" + code.Substring(4);

        public Round OneRound(bool retried = false)
        {
            if (!ValidServer(Server)) return new Round { State = "setup", Text = T("Not set up: run the installer again") };
            try
            {
                var token = ReadSession();
                if (token.Length == 0)
                {
                    Dictionary<string, object> pending = null;
                    try { if (File.Exists(PendingFile)) pending = Json.DeserializeObject(File.ReadAllText(PendingFile)) as Dictionary<string, object>; } catch { }
                    if (Str(pending, "key").Length > 0)
                    {
                        var r = Call("POST", "/tv/poll", "tv-pending=" + Str(pending, "key"));
                        var st = Str(r.Json, "status");
                        if (r.Status == 200 && st == "done")
                        {
                            token = CookieValue(r.Cookies, "session");
                            if (token.Length > 0) { SaveSession(token); File.Delete(PendingFile); }
                        }
                        else if (r.Status == 200 && st == "pending")
                        {
                            var code = Str(pending, "code");
                            return new Round { State = "pair", Code = code, Text = PairText(code) };
                        }
                        else File.Delete(PendingFile);
                    }
                    if (token.Length == 0)
                    {
                        var r = Call("POST", "/tv/request-code");
                        var key = CookieValue(r.Cookies, "tv-pending");
                        var code = Str(r.Json, "code");
                        if (r.Status != 200 || key.Length == 0 || !Regex.IsMatch(code, @"^\d{8}$")) return new Round { State = "off", Text = T("The server refused the pairing, try again later") };
                        SavePrivate(PendingFile, Json.Serialize(new Dictionary<string, string> { { "key", key }, { "code", code } }));
                        return new Round { State = "pair", Code = code, Text = PairText(code) };
                    }
                }
                var s = Call("GET", "/mini/state", "session=" + token);
                if ((s.Status == 401 || s.Status == 403) && !retried) { File.Delete(SessionFile); return OneRound(true); }
                if (s.Status != 200) throw new Exception("status " + s.Status);
                var h = Call("POST", "/mini/handoff", "session=" + token);
                var round = new Round { Notify = !s.Json.TryGetValue("notify", out var n) || n is bool b && b, NotifyMinutes = (int)Num(s.Json.TryGetValue("notifyMinutes", out var nm) ? nm : 10) };
                if (s.Json.TryGetValue("waiting", out var w) && w is IEnumerable list)
                    foreach (var o in list)
                        if (o is Dictionary<string, object> p) round.Waiting.Add(new Waiter { Name = Str(p, "name"), Since = Num(p.TryGetValue("since", out var since) ? since : null) });
                var now = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
                var longWait = round.Waiting.Any(p => p.Since > 0 && now - p.Since >= round.NotifyMinutes * 60000L);
                round.Count = round.Waiting.Count;
                round.State = longWait ? "long" : "ok";
                round.Text = round.Count > 0 ? T("{n} waiting").Replace("{n}", round.Count.ToString()) : T("Nobody is waiting");
                // the one-time window code from the server: anything else (a hostile server, a tampered reply) never goes into the address; the board opens instead
                // mã mở khung dùng một lần từ máy chủ: thứ khác (máy chủ xấu, câu trả lời bị sửa) không bao giờ vào địa chỉ; mở bảng thay vào đó
                var handoff = Str(h.Json, "code");
                round.Url = Regex.IsMatch(handoff, "^[A-Za-z0-9_-]{8,128}$") ? Server + "/mini?h=" + handoff + "&lang=" + Lang : Server + "/board";
                return round;
            }
            catch (Exception e)
            {
                LastError = e.Message;
                return new Round { State = "off", Text = T("Cannot reach the server") };
            }
        }

        // One notification per wait that passed the limit; waits that ended are forgotten. Returns who to notify now.
        // Mỗi lần chờ quá hạn chỉ báo một lần; quên những lần chờ đã xong. Trả về những người cần báo lần này.
        public List<(Waiter who, int minutes)> ToNotify(Round r)
        {
            var done = new HashSet<string>();
            try
            {
                if (File.Exists(NotifiedFile) && Json.DeserializeObject(File.ReadAllText(NotifiedFile, Encoding.UTF8)) is IEnumerable list)
                    foreach (var o in list) if (o != null) done.Add(Convert.ToString(o));
            }
            catch { }
            var current = new List<string>();
            var result = new List<(Waiter, int)>();
            var now = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
            foreach (var p in r.Waiting)
            {
                if (p.Since <= 0) continue;
                var key = p.Name + "|" + p.Since;
                current.Add(key);
                var minutes = (int)((now - p.Since) / 60000);
                if (r.Notify && minutes >= r.NotifyMinutes && !done.Contains(key)) { result.Add((p, minutes)); done.Add(key); }
            }
            SavePrivate(NotifiedFile, Json.Serialize(done.Where(current.Contains).ToArray()));
            return result;
        }
    }

    static class Program
    {
        [DllImport("kernel32.dll")] static extern bool AttachConsole(int pid);

        [STAThread]
        static int Main(string[] args)
        {
            if (args.Contains("--round") || args.Contains("--test-notify"))
            {
                // the result goes to the file after --out (a windowed app may have no console to print to)
                // kết quả ghi vào file sau --out (app có giao diện nên không chắc có cửa sổ dòng lệnh để in ra)
                var i = Array.IndexOf(args, "--out");
                var outFile = i >= 0 && i + 1 < args.Length ? args[i + 1] : null;
                var core = new Core();
                string line;
                if (args.Contains("--test-notify"))
                {
                    // test: three rounds with two long waits (one name with Vietnamese letters) must give exactly two notifications
                    // bài thử: ba lượt với hai người chờ lâu (một tên có dấu) phải ra đúng hai thông báo
                    var now = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
                    var r = new Round { Notify = true, NotifyMinutes = 10 };
                    r.Waiting.Add(new Waiter { Name = "An", Since = now - 900000 });
                    r.Waiting.Add(new Waiter { Name = Environment.GetEnvironmentVariable("TEST_NAME") ?? "Ann", Since = now - 720000 });
                    var names = new List<string>();
                    for (var n = 0; n < 3; n++) names.AddRange(core.ToNotify(r).Select(x => x.who.Name));
                    line = names.Count + "|" + string.Join(",", names);
                }
                else
                {
                    var r = core.OneRound();
                    line = r.State + "|" + r.Count + "|" + r.Text + "|" + (r.Url.Length > 0 ? "url" : "") + (core.LastError.Length > 0 ? "|" + core.LastError : "");
                }
                if (outFile != null) File.WriteAllText(outFile, line, new UTF8Encoding(false));
                else { AttachConsole(-1); Console.WriteLine(line); }
                return 0;
            }
            // one copy only; a second one (a notification click, or opening the app again) asks the running copy to open the window and quits
            // một bản duy nhất; bản thứ hai (bấm thông báo hay mở lại app) nhờ bản đang chạy mở khung rồi thoát
            using (var mutex = new Mutex(true, @"Local\AIWorker.MenuBar", out var first))
            using (var openSignal = new EventWaitHandle(false, EventResetMode.AutoReset, @"Local\AIWorker.MenuBar.Open"))
            {
                if (!first) { openSignal.Set(); return 0; }
                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);
                var app = new Tray(new Core(), openSignal, args.Contains("--open"));
                Application.Run();
                GC.KeepAlive(app);
            }
            return 0;
        }
    }

    // A hidden window for close messages: the .msi sends one when installing over the app or removing it, Windows at logoff. The app quits cleanly and takes
    // its icon off the tray, so no file stays in use and Windows does not ask for a reboot.
    // Cửa sổ ẩn nhận lệnh đóng: bộ cài .msi gửi lệnh đóng khi cài đè hay gỡ, Windows gửi khi đăng xuất. App thoát gọn và gỡ biểu tượng khỏi khay,
    // nên file không còn bị giữ và Windows không đòi khởi động lại máy.
    class HiddenWindow : Form
    {
        readonly Action quit;
        bool quitting;
        public HiddenWindow(Action quit) { this.quit = quit; ShowInTaskbar = false; Text = ""; FormBorderStyle = FormBorderStyle.None; }
        protected override void SetVisibleCore(bool value) { base.SetVisibleCore(false); }
        protected override void WndProc(ref Message m)
        {
            const int WM_CLOSE = 0x10, WM_ENDSESSION = 0x16;
            // quit once, after this message is handled: Application.Exit closes this very window, and that second close goes the normal way
            // thoát một lần, sau khi xử lý xong lệnh này: Application.Exit lại đóng chính cửa sổ này, lệnh đóng thứ hai đi theo đường thường
            if (!quitting && (m.Msg == WM_CLOSE || (m.Msg == WM_ENDSESSION && m.WParam != IntPtr.Zero))) { quitting = true; BeginInvoke(quit); return; }
            base.WndProc(ref m);
        }
    }

    // The part with a window: the tray icon, its menu, notifications, the small window
    // Phần có giao diện: biểu tượng khay, menu, thông báo, khung nhỏ
    class Tray
    {
        const string AppId = "AIWorker.MenuBar";
        const string UpgradeCode = "{CD80F6D2-E13A-423F-A6E7-0D2FC58C8EAE}"; // same as UpgradeCode in AIWorker.wxs
        const string RunKey = @"Software\Microsoft\Windows\CurrentVersion\Run";
        static readonly string[] AvatarColors = { "#e17076", "#faa774", "#a695e7", "#7bc862", "#6ec9cb", "#65aadd", "#ee7aae" };

        readonly Core core;
        readonly NotifyIcon tray = new NotifyIcon();
        readonly ToolStripItem itemText, itemBoard, itemQuit;
        readonly System.Windows.Forms.Timer timer = new System.Windows.Forms.Timer { Interval = 60000 };
        readonly System.Windows.Forms.Timer openTimer = new System.Windows.Forms.Timer { Interval = 300 };
        readonly EventWaitHandle openSignal;
        readonly Image logo;
        MenuBarPopup popup;
        readonly HiddenWindow hiddenWindow;
        bool popupFailed, opening, hasToasts;
        Round last = new Round();

        string ExePath => Process.GetCurrentProcess().MainModule.FileName;

        public Tray(Core core, EventWaitHandle openSignal, bool openNow)
        {
            this.core = core;
            this.openSignal = openSignal;
            CleanUpOldVersion();
            hiddenWindow = new HiddenWindow(Quit);
            var _ = hiddenWindow.Handle;
            logo = LoadLogo();
            var menu = new ContextMenuStrip();
            itemText = menu.Items.Add("");
            itemText.Enabled = false;
            itemBoard = menu.Items.Add(core.T("Open board"), null, (a, b) => { if (core.Server.Length > 0) OpenInBrowser(core.Server + "/board"); });
            itemQuit = menu.Items.Add(core.T("Quit"), null, (a, b) => Quit());
            tray.ContextMenuStrip = menu;
            tray.Visible = true;
            tray.MouseClick += (a, e) => { if (e.Button == MouseButtons.Left) OpenFromTray(); };
            tray.BalloonTipClicked += (a, b) => OpenFromTray();
            hasToasts = RegisterAppName();
            // first run: start at login (afterwards the person turns it on or off in the window)
            // lần chạy đầu: tự chạy khi đăng nhập (sau đó người dùng bật tắt trong khung)
            var marker = Path.Combine(core.ConfigDir, "start-at-login-set");
            if (!File.Exists(marker)) { SetStartAtLogin(true); try { core.SavePrivate(marker, "1"); } catch { } }
            timer.Tick += (a, b) => Refresh();
            timer.Start();
            openTimer.Tick += (a, b) => { if (openSignal.WaitOne(0)) OpenFromTray(); };
            openTimer.Start();
            Refresh();
            if (openNow) OpenFromTray();
        }

        // The old PowerShell icon: stop it, remove its Startup shortcut and script files; keep the pairing, the settings and the window's data
        // Bản PowerShell cũ: tắt tiến trình, xoá lối tắt Startup và các file script; giữ phiên ghép, cài đặt và dữ liệu khung
        void CleanUpOldVersion()
        {
            try
            {
                using (var search = new ManagementObjectSearcher("SELECT ProcessId, CommandLine FROM Win32_Process WHERE Name = 'powershell.exe'"))
                    foreach (ManagementObject p in search.Get())
                        if ((p["CommandLine"] as string ?? "").IndexOf("ai-worker-tray.ps1", StringComparison.OrdinalIgnoreCase) >= 0)
                            try { Process.GetProcessById(Convert.ToInt32(p["ProcessId"])).Kill(); } catch { }
            }
            catch { }
            try { File.Delete(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Startup), "AI Worker menu bar.lnk")); } catch { }
            foreach (var f in new[] { "ai-worker-tray.ps1", "menubar-popup.cs", "open-window.vbs", "notification-logo.png", "popup-error.txt" })
                try { File.Delete(Path.Combine(core.ConfigDir, f)); } catch { }
            try { var wv = Path.Combine(core.ConfigDir, "webview2"); if (Directory.Exists(wv)) Directory.Delete(wv, true); } catch { }
        }

        // The logo matching the taskbar: white on a dark taskbar, black on a light one. A company logo (icon-white.png, icon-black.png in the settings folder) wins.
        // Logo hợp với thanh tác vụ: trắng trên thanh tối, đen trên thanh sáng. Logo riêng của công ty (icon-white.png, icon-black.png trong thư mục cài đặt) được dùng trước.
        Image LoadLogo()
        {
            var light = 0;
            try { light = Convert.ToInt32(Registry.GetValue(@"HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", "SystemUsesLightTheme", 0)); } catch { }
            var color = light == 1 ? "black" : "white";
            foreach (var f in new[] { Path.Combine(core.ConfigDir, "icon-" + color + ".png"), Path.Combine(Core.InstallDir, "generic-" + color + ".png") })
                try { if (File.Exists(f) && new FileInfo(f).Length <= 20000) return Image.FromFile(f); } catch { }
            return null;
        }

        // The logo, the count on a round badge; the badge turns deep blue when someone waited past the limit; the logo fades without a connection or pairing
        // Logo, số đếm trong chấm tròn; chấm xanh lam đậm khi có người chờ quá hạn; logo mờ khi mất kết nối hay chưa ghép
        Icon MakeIcon(string state, int count)
        {
            using (var bmp = new Bitmap(32, 32))
            {
                using (var g = Graphics.FromImage(bmp))
                {
                    g.SmoothingMode = SmoothingMode.AntiAlias;
                    g.InterpolationMode = InterpolationMode.HighQualityBicubic;
                    if (logo != null)
                    {
                        var attrs = new ImageAttributes();
                        if (state == "off" || state == "pair") attrs.SetColorMatrix(new ColorMatrix { Matrix33 = 0.4f });
                        g.DrawImage(logo, new Rectangle(0, 0, 32, 32), 0, 0, logo.Width, logo.Height, GraphicsUnit.Pixel, attrs);
                    }
                    else g.FillEllipse(Brushes.Gray, 4, 4, 24, 24);
                    if (count > 0)
                    {
                        var badge = state == "long" ? Color.FromArgb(26, 86, 200) : Color.FromArgb(200, 40, 40);
                        using (var brush = new SolidBrush(badge)) g.FillEllipse(brush, 14, 14, 18, 18);
                        using (var font = new Font("Segoe UI", count > 9 ? 8 : 10, FontStyle.Bold))
                        using (var fmt = new StringFormat { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center })
                            g.DrawString(count > 99 ? "99" : count.ToString(), font, Brushes.White, new RectangleF(14, 14, 18, 18), fmt);
                    }
                }
                return Icon.FromHandle(bmp.GetHicon());
            }
        }

        void Refresh()
        {
            var r = core.OneRound();
            last = r;
            var old = tray.Icon;
            tray.Icon = MakeIcon(r.State, r.Count);
            old?.Dispose();
            var tip = "AI Worker: " + r.Text;
            tray.Text = tip.Length > 63 ? tip.Substring(0, 63) : tip;
            itemText.Text = r.Text;
            if (r.Waiting.Count > 0)
                foreach (var (who, minutes) in core.ToNotify(r))
                    Notify(core.T("Waiting for an answer"), core.T("{name} has waited {n} minutes").Replace("{name}", who.Name).Replace("{n}", minutes.ToString()), who.Name);
        }

        // A click on the icon or on a notification: refresh without a notification, then open the window (or the pairing page)
        // Bấm biểu tượng hay bấm thông báo: làm mới không bật thông báo, rồi mở khung (hoặc trang ghép)
        void OpenFromTray()
        {
            opening = true;
            try { Refresh(); } finally { opening = false; }
            if (last.Url.StartsWith(core.Server + "/mini?")) OpenWindow(last.Url);
            else if (last.Url.Length > 0) OpenInBrowser(last.Url);
            else if (last.State == "pair" && Regex.IsMatch(last.Code, @"^\d{8}$")) OpenWindow(core.Server + "/mini/pair#c=" + last.Code);
        }

        // Only this server's own pages, in the default browser
        // Chỉ mở trang của máy chủ này, bằng trình duyệt mặc định
        void OpenInBrowser(string url)
        {
            if (url.StartsWith(core.Server + "/")) try { Process.Start(new ProcessStartInfo(url) { UseShellExecute = true }); } catch { }
        }

        MenuBarPopup NewPopup()
        {
            if (popupFailed) return null;
            try
            {
                var arch = RuntimeInformation.ProcessArchitecture == Architecture.Arm64 ? "arm64" : RuntimeInformation.ProcessArchitecture == Architecture.X86 ? "x86" : "x64";
                var p = new MenuBarPopup(Path.Combine(core.ConfigDir, "popup-data"), Path.Combine(Core.InstallDir, "webview2", arch));
                // the language chosen in the window's Settings also drives the tray menu and the notifications
                // ngôn ngữ chọn trong Cài đặt của khung cũng đổi menu ở khay và thông báo
                p.LanguageChanged += code =>
                {
                    if ((code != "en" && code != "vi") || code == core.Lang) return;
                    core.SaveLang(code);
                    itemBoard.Text = core.T("Open board");
                    itemQuit.Text = core.T("Quit");
                    Refresh();
                };
                p.Hello += () => popup?.TellLogin(StartsAtLogin());
                p.UninstallRequested += RemoveApp;
                p.QuitRequested += Quit;
                p.LoginChanged += on => { SetStartAtLogin(on); popup?.TellLogin(StartsAtLogin()); };
                return p;
            }
            catch (Exception e)
            {
                popupFailed = true;
                try { core.SavePrivate(Path.Combine(core.ConfigDir, "popup-error.txt"), e.Message); } catch { }
                return null;
            }
        }

        void OpenWindow(string url)
        {
            // clear the notifications still showing, so nothing sits on top of the window
            // xoá các thông báo còn đang hiện, để không gì đè lên khung
            if (hasToasts) try { Windows.UI.Notifications.ToastNotificationManager.History.Clear(AppId); } catch { }
            if (popup == null) popup = NewPopup();
            if (popup != null)
            {
                try { popup.Open(url, core.Server); return; }
                catch (Exception e) { try { core.SavePrivate(Path.Combine(core.ConfigDir, "popup-error.txt"), e.Message); } catch { } }
            }
            // fallback: a compact Edge window with no address bar, next to the notification area, on a profile of its own
            // dự phòng: cửa sổ Edge gọn, không thanh địa chỉ, sát khay đồng hồ, hồ sơ riêng
            var area = Screen.PrimaryScreen.WorkingArea;
            var edge = new[] { Environment.GetEnvironmentVariable("ProgramFiles(x86)"), Environment.GetEnvironmentVariable("ProgramFiles") }
                .Where(p => p != null).Select(p => Path.Combine(p, @"Microsoft\Edge\Application\msedge.exe")).FirstOrDefault(File.Exists);
            if (edge == null) { OpenInBrowser(url); return; }
            try
            {
                Process.Start(edge, "--app=\"" + url + "\" --window-size=380,480 --window-position=" + (area.Right - 380) + "," + (area.Bottom - 480) +
                    " --user-data-dir=\"" + Path.Combine(core.ConfigDir, "edge-window") + "\" --no-first-run --no-default-browser-check");
            }
            catch { }
        }

        // Start at login: a value in the user's Run key (no admin rights)
        // Tự chạy khi đăng nhập: một giá trị trong khoá Run của người dùng (không cần quyền quản trị)
        bool StartsAtLogin()
        {
            try { using (var k = Registry.CurrentUser.OpenSubKey(RunKey)) return k?.GetValue("AI Worker") != null; } catch { return false; }
        }

        void SetStartAtLogin(bool on)
        {
            try
            {
                using (var k = Registry.CurrentUser.CreateSubKey(RunKey))
                    if (on) k.SetValue("AI Worker", "\"" + ExePath + "\""); else k.DeleteValue("AI Worker", false);
            }
            catch { }
        }

        // Notifications named AI Worker with the G logo: the app name is registered in the user's key; a click on one runs the exe again with --open
        // Thông báo mang tên AI Worker và logo G: tên app đăng ký trong khoá của người dùng; bấm thông báo chạy lại exe với --open
        bool RegisterAppName()
        {
            try
            {
                using (var k = Registry.CurrentUser.CreateSubKey(@"Software\Classes\AppUserModelId\" + AppId))
                {
                    k.SetValue("DisplayName", "AI Worker");
                    var logoFile = Path.Combine(Core.InstallDir, "app-icon.png");
                    if (File.Exists(logoFile)) k.SetValue("IconUri", logoFile);
                }
                using (var k = Registry.CurrentUser.CreateSubKey(@"Software\Classes\ai-worker-open"))
                {
                    k.SetValue("", "URL:AI Worker");
                    k.SetValue("URL Protocol", "");
                }
                using (var k = Registry.CurrentUser.CreateSubKey(@"Software\Classes\ai-worker-open\shell\open\command"))
                    k.SetValue("", "\"" + ExePath + "\" --open");
                return true;
            }
            catch { return false; }
        }

        // The round badge in a notification: the first letter of the person's name on a colour fixed by the name (same rule as the Mac and Ubuntu apps)
        // Ô tròn trong thông báo: chữ cái đầu của tên trên một màu cố định theo tên (cùng quy tắc với app Mac và Ubuntu)
        string Avatar(string name)
        {
            try
            {
                var letter = "?";
                foreach (var c in name) if (char.IsLetterOrDigit(c)) { letter = c.ToString().ToUpper(); break; }
                var sum = Encoding.UTF8.GetBytes(name).Sum(b => (int)b);
                var color = AvatarColors[sum % AvatarColors.Length];
                var dir = Path.Combine(core.ConfigDir, "avatars");
                var path = Path.Combine(dir, ((int)letter[0]).ToString("x") + "-" + color.Substring(1) + ".png");
                if (File.Exists(path)) return path;
                Directory.CreateDirectory(dir);
                const int size = 128;
                using (var bmp = new Bitmap(size, size))
                {
                    using (var g = Graphics.FromImage(bmp))
                    {
                        g.SmoothingMode = SmoothingMode.AntiAlias;
                        g.TextRenderingHint = System.Drawing.Text.TextRenderingHint.AntiAliasGridFit;
                        using (var fill = new SolidBrush(ColorTranslator.FromHtml(color))) g.FillEllipse(fill, 0, 0, size, size);
                        using (var font = new Font("Segoe UI", size * 0.5f, FontStyle.Bold, GraphicsUnit.Pixel))
                        using (var fmt = new StringFormat { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center })
                            g.DrawString(letter, font, Brushes.White, new RectangleF(0, 0, size, size), fmt);
                    }
                    bmp.Save(path, ImageFormat.Png);
                }
                return path;
            }
            catch { return null; }
        }

        void Notify(string title, string body, string who)
        {
            // the window is open: the person already sees the list, so no notification on top of it
            // khung đang mở: người dùng đã thấy danh sách, khỏi bật thông báo đè lên
            if (opening || (popup != null && popup.IsOpen)) return;
            if (hasToasts)
            {
                try
                {
                    // the text goes into the XML escaped, so a name never becomes a tag
                    // chữ đưa vào XML đã được thoát ký tự, nên tên người không thành thẻ XML
                    var img = "";
                    var a = string.IsNullOrEmpty(who) ? null : Avatar(who);
                    if (a != null) img = "<image placement=\"appLogoOverride\" hint-crop=\"circle\" src=\"" + SecurityElement.Escape(new Uri(a).AbsoluteUri) + "\"/>";
                    var xml = "<toast launch=\"ai-worker-open:window\" activationType=\"protocol\"><visual><binding template=\"ToastGeneric\"><text>" +
                        SecurityElement.Escape(title) + "</text><text>" + SecurityElement.Escape(body) + "</text>" + img + "</binding></visual></toast>";
                    var doc = new Windows.Data.Xml.Dom.XmlDocument();
                    doc.LoadXml(xml);
                    Windows.UI.Notifications.ToastNotificationManager.CreateToastNotifier(AppId).Show(new Windows.UI.Notifications.ToastNotification(doc));
                    return;
                }
                catch { hasToasts = false; }
            }
            tray.ShowBalloonTip(8000, title, body, ToolTipIcon.None);
        }

        void Quit()
        {
            tray.Visible = false;
            Application.Exit();
        }

        [DllImport("msi.dll", CharSet = CharSet.Unicode)] static extern uint MsiEnumRelatedProducts(string upgradeCode, uint reserved, uint index, StringBuilder productCode);

        // Remove the app (the server has already unpaired it): stop starting at login, drop the registrations, then a hidden command deletes the settings and uninstalls the .msi after the app quits
        // Gỡ app (máy chủ đã bỏ ghép): thôi tự chạy, bỏ đăng ký, rồi một lệnh chạy ẩn xoá cài đặt và gỡ gói .msi sau khi app thoát
        void RemoveApp()
        {
            SetStartAtLogin(false);
            foreach (var k in new[] { @"Software\Classes\AppUserModelId\" + AppId, @"Software\Classes\ai-worker-open", @"Software\AI Worker" })
                try { Registry.CurrentUser.DeleteSubKeyTree(k, false); } catch { }
            var steps = new List<string> { "timeout /t 3 /nobreak >nul" };
            // the whole folder goes only when it is the app's own (named ai-worker); otherwise only the app's own files go
            // cả thư mục chỉ khi đúng là thư mục riêng của app (tên ai-worker); thư mục khác thì chỉ xoá các file của app
            if (Path.GetFileName(core.ConfigDir.TrimEnd('\\', '/')) == "ai-worker") steps.Add("rmdir /s /q \"" + core.ConfigDir + "\"");
            else foreach (var f in new[] { "menubar-session", "menubar-pending.json", "menubar-notified.json", "start-at-login-set" }) steps.Add("del /f /q \"" + Path.Combine(core.ConfigDir, f) + "\"");
            var code = new StringBuilder(39);
            if (MsiEnumRelatedProducts(UpgradeCode, 0, 0, code) == 0) steps.Add("msiexec /x " + code + " /qn");
            try
            {
                Process.Start(new ProcessStartInfo(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "cmd.exe"),
                    "/c " + string.Join(" & ", steps) + " 2>nul") { CreateNoWindow = true, WindowStyle = ProcessWindowStyle.Hidden, UseShellExecute = false });
            }
            catch { }
            Quit();
        }
    }
}
