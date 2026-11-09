// The small window on Windows, like the Mac app's window: borderless, rounded corners, drop shadow, frosted backdrop (Windows 11 22H2 and later),
// anchored right above the clock tray, sized to the page height, hidden on a click outside or on Escape. The page inside is the server's /mini, shown with WebView2.
// Khung nhỏ trên Windows, giống khung app Mac: không viền, bo góc, bóng đổ, nền kính mờ (Windows 11 22H2 trở lên),
// dính ngay trên khay đồng hồ, co theo chiều cao trang, bấm ra ngoài hoặc Escape là ẩn. Trang bên trong là /mini của máy chủ, hiện bằng WebView2.
// Compiled into AI Worker.exe (windows-app); the old PowerShell icon (ai-worker-tray.ps1, the fallback .zip) still compiles it at run time with Add-Type.
// Được dịch vào AI Worker.exe (windows-app); bản PowerShell cũ (ai-worker-tray.ps1, gói .zip dự phòng) vẫn dịch file này lúc chạy bằng Add-Type.
using System;
using System.Diagnostics;
using System.Drawing;
using System.Runtime.InteropServices;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

public class MenuBarPopup : Form
{
    [DllImport("dwmapi.dll")] static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int value, int size);
    [DllImport("dwmapi.dll")] static extern int DwmExtendFrameIntoClientArea(IntPtr hwnd, ref Margins margins);
    [StructLayout(LayoutKind.Sequential)] struct Margins { public int Left, Right, Top, Bottom; }

    const int WIDTH = 380, GAP = 12, MIN_HEIGHT = 220, MAX_HEIGHT = 640;
    readonly WebView2 view = new WebView2();
    readonly string dataFolder;
    string server = "";
    string pendingUrl = null;
    bool acrylic;
    bool ready;

    // measures the page height like the Mac app; reports the Escape key
    // đo chiều cao trang như app Mac; báo phím Escape
    const string MEASURE = "(function(){var last=0;function send(){var m=document.querySelector('main');" +
        "var h=Math.ceil(m?m.getBoundingClientRect().bottom+14:document.body.scrollHeight);" +
        "if(h!==last){last=h;window.chrome.webview.postMessage('h:'+h)}}" +
        "addEventListener('DOMContentLoaded',function(){var r=new ResizeObserver(send);r.observe(document.documentElement);send()});" +
        "addEventListener('keydown',function(e){if(e.key==='Escape')window.chrome.webview.postMessage('esc')})})()";
    // a transparent page background, so the frosted backdrop shows through
    // nền trang trong suốt, để nền kính mờ lộ ra
    const string TRANSPARENT_PAGE = "addEventListener('DOMContentLoaded',function(){var s=document.createElement('style');" +
        "s.textContent='html,body{background:transparent!important}.btn{background:rgba(127,127,127,.12)}';document.head.appendChild(s)})";

    // shows the start-at-login row, which only the window can turn on and off
    // hiện dòng tự chạy khi đăng nhập, việc chỉ khung bật tắt được
    const string HOST_LOGIN = "addEventListener('DOMContentLoaded',function(){document.documentElement.classList.add('host-login')})";

    public MenuBarPopup(string dataFolder, string loaderFolder)
    {
        this.dataFolder = dataFolder;
        CoreWebView2Environment.SetLoaderDllFolderPath(loaderFolder);
        FormBorderStyle = FormBorderStyle.None;
        ShowInTaskbar = false;
        TopMost = true;
        StartPosition = FormStartPosition.Manual;
        Size = new Size(WIDTH, 420);
        // only Windows 11 22H2 (build 22621) and later has the frosted backdrop for ordinary windows
        // chỉ Windows 11 22H2 (bản dựng 22621) trở lên mới có nền kính mờ cho cửa sổ thường
        acrylic = Environment.OSVersion.Version.Build >= 22621;
        BackColor = acrylic ? Color.Black : Color.FromArgb(246, 246, 244);
        view.Dock = DockStyle.Fill;
        if (acrylic) view.DefaultBackgroundColor = Color.Transparent;
        Controls.Add(view);
        Deactivate += (s, e) => Hide();
    }

    protected override CreateParams CreateParams
    {
        get
        {
            var cp = base.CreateParams;
            // CS_DROPSHADOW: shadow under the window
            // CS_DROPSHADOW: bóng đổ dưới khung
            cp.ClassStyle |= 0x20000;
            // WS_EX_TOOLWINDOW: kept out of Alt+Tab
            // WS_EX_TOOLWINDOW: không hiện trong Alt+Tab
            cp.ExStyle |= 0x80;
            return cp;
        }
    }

    protected override void OnHandleCreated(EventArgs e)
    {
        base.OnHandleCreated(e);
        // DWMWA_WINDOW_CORNER_PREFERENCE = 33, DWMWCP_ROUND = 2: Windows 11 rounded corners
        // DWMWA_WINDOW_CORNER_PREFERENCE = 33, DWMWCP_ROUND = 2: góc bo của Windows 11
        int round = 2;
        DwmSetWindowAttribute(Handle, 33, ref round, 4);
        if (acrylic)
        {
            // DWMWA_USE_IMMERSIVE_DARK_MODE = 20: dark glass when Windows is in dark mode
            // DWMWA_USE_IMMERSIVE_DARK_MODE = 20: kính tối khi Windows để chế độ tối
            int dark = SystemIsDark() ? 1 : 0;
            DwmSetWindowAttribute(Handle, 20, ref dark, 4);
            // DWMWA_SYSTEMBACKDROP_TYPE = 38, DWMSBT_TRANSIENTWINDOW = 3: frosted like the Quick Settings panel
            // DWMWA_SYSTEMBACKDROP_TYPE = 38, DWMSBT_TRANSIENTWINDOW = 3: kính mờ như bảng Quick Settings
            int glass = 3;
            DwmSetWindowAttribute(Handle, 38, ref glass, 4);
            var margins = new Margins { Left = -1, Right = -1, Top = -1, Bottom = -1 };
            DwmExtendFrameIntoClientArea(Handle, ref margins);
        }
    }

    static bool SystemIsDark()
    {
        try
        {
            var v = Microsoft.Win32.Registry.GetValue(@"HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", "AppsUseLightTheme", 1);
            return v is int && (int)v == 0;
        }
        catch { return false; }
    }

    async void Initialize()
    {
        var environment = await CoreWebView2Environment.CreateAsync(null, dataFolder, null);
        await view.EnsureCoreWebView2Async(environment);
        var w = view.CoreWebView2;
        w.Settings.AreDevToolsEnabled = false;
        w.Settings.AreDefaultContextMenusEnabled = false;
        w.Settings.IsStatusBarEnabled = false;
        w.Settings.IsZoomControlEnabled = false;
        await w.AddScriptToExecuteOnDocumentCreatedAsync(HOST_LOGIN);
        await w.AddScriptToExecuteOnDocumentCreatedAsync(MEASURE);
        if (acrylic) await w.AddScriptToExecuteOnDocumentCreatedAsync(TRANSPARENT_PAGE);
        w.WebMessageReceived += OnMessage;
        // the window's own pages stay here; everything else (the board, other links) opens in the default browser
        // trang của khung ở lại đây; còn lại (bảng, đường dẫn) mở bằng trình duyệt của máy
        w.NavigationStarting += (s, e) =>
        {
            if (InsideWindow(e.Uri)) return;
            e.Cancel = true;
            OpenInBrowser(e.Uri);
        };
        w.NewWindowRequested += (s, e) => { e.Handled = true; OpenInBrowser(e.Uri); };
        ready = true;
        if (pendingUrl != null) { w.Navigate(pendingUrl); pendingUrl = null; }
    }

    bool InsideWindow(string uri)
    {
        return uri == "about:blank" || (server.Length > 0 && (uri.StartsWith(server + "/mini") || uri.StartsWith(server + "/static/")));
    }

    static void OpenInBrowser(string uri)
    {
        if (uri != null && (uri.StartsWith("https://") || uri.StartsWith("http://"))) Process.Start(new ProcessStartInfo(uri) { UseShellExecute = true });
    }

    void OnMessage(object s, CoreWebView2WebMessageReceivedEventArgs e)
    {
        // only the window's own page may ask for these (uninstall, quit, start at login); a page the window was led to elsewhere is ignored
        // chỉ chính trang của khung được xin mấy việc này (gỡ app, thoát, tự chạy khi đăng nhập); trang lạ mà khung bị dẫn tới thì bỏ qua
        if (server.Length == 0 || e.Source == null || !e.Source.StartsWith(server + "/mini", StringComparison.Ordinal)) return;
        string message;
        try { message = e.TryGetWebMessageAsString(); } catch { return; }
        if (message == "esc") { Hide(); return; }
        if (message == "lang:en" || message == "lang:vi") { if (LanguageChanged != null) LanguageChanged(message.Substring(5)); return; }
        if (message == "hello") { if (Hello != null) Hello(); return; }
        if (message == "uninstall") { Hide(); if (UninstallRequested != null) UninstallRequested(); return; }
        if (message == "quit") { Hide(); if (QuitRequested != null) QuitRequested(); return; }
        if (message == "login:on" || message == "login:off") { if (LoginChanged != null) LoginChanged(message == "login:on"); return; }
        int height;
        if (message != null && message.StartsWith("h:") && int.TryParse(message.Substring(2), out height)) AnimateTo(Math.Min(MAX_HEIGHT, Math.Max(MIN_HEIGHT, height)));
    }

    // anchored to the bottom-right of the work area, right above the clock tray; when the height changes the bottom edge stays put
    // dính góc dưới bên phải vùng làm việc, ngay trên khay đồng hồ; khung co giãn thì đáy đứng yên
    // while the window shows, it grows or shrinks smoothly (about 0.24 s, slowing at the end); while hidden it is set at once
    // khung đang hiện thì co giãn từ từ (khoảng 0,24 giây, chậm dần về cuối); đang ẩn thì đặt ngay
    readonly Timer stepper = new Timer { Interval = 15 };
    int fromHeight, toHeight;
    DateTime startedAt;
    void AnimateTo(int target)
    {
        if (!Visible || target == Height) { stepper.Stop(); Place(target); return; }
        fromHeight = Height; toHeight = target; startedAt = DateTime.Now;
        if (!stepper.Enabled)
        {
            stepper.Tick -= Step; stepper.Tick += Step;
            stepper.Start();
        }
    }
    void Step(object s, EventArgs e)
    {
        double x = Math.Min(1, (DateTime.Now - startedAt).TotalMilliseconds / 240.0);
        double eased = 1 - Math.Pow(1 - x, 3);
        Place((int)Math.Round(fromHeight + (toHeight - fromHeight) * eased));
        if (x >= 1) stepper.Stop();
    }

    void Place(int height)
    {
        var area = Screen.PrimaryScreen.WorkingArea;
        Bounds = new Rectangle(area.Right - WIDTH - GAP, area.Bottom - height - GAP, WIDTH, height);
    }

    // the language chosen in the window's Settings, for the tray menu and the notifications
    // ngôn ngữ chọn trong Cài đặt của khung, cho menu ở khay và thông báo
    public event Action<string> LanguageChanged;

    // the page asks whether this computer starts the icon at login, and turns that on or off
    // trang hỏi máy này có tự chạy biểu tượng khi đăng nhập không, và bật tắt việc đó
    public event Action Hello;
    // the person confirmed "Remove the app" in the window; the server is already unpaired
    // người dùng đã xác nhận "Gỡ app" trong khung; máy chủ đã bỏ ghép
    public event Action UninstallRequested;
    public event Action QuitRequested;
    public event Action<bool> LoginChanged;

    // answers the page the way the macOS app does: window.appState({login: true|false})
    // trả lời trang như app macOS: window.appState({login: true|false})
    public void TellLogin(bool on)
    {
        if (ready) view.CoreWebView2.ExecuteScriptAsync("window.appState&&window.appState({login:" + (on ? "true" : "false") + "})");
    }

    public void Open(string url, string server)
    {
        this.server = (server ?? "").TrimEnd('/');
        if (!IsHandleCreated) { Place(Height); CreateControl(); Initialize(); }
        if (ready) view.CoreWebView2.Navigate(url); else pendingUrl = url;
        if (!Visible) Place(Height);
        Show();
        Activate();
    }

    // the window is open: the person already sees the list, so no notification on top of it
    // khung đang mở: người dùng đã thấy danh sách, khỏi bật thông báo đè lên
    public bool IsOpen { get { return Visible; } }
}
