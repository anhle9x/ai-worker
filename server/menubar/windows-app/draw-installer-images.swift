import AppKit
// Draws the setup window images: a dark left column (164 px, full height) with a large faint G behind the app name and a short line;
// a white 493x58 banner with the logo on the right. Layout: centred (G centred behind the name) or bleed (larger G running off the left edge).
// Vẽ hình cho cửa sổ cài: cột trái tối (164px, hết chiều cao) có chữ G lớn chìm sau tên app và một dòng ngắn;
// banner 493x58 nền trắng, logo bên phải. Bố cục: centred (G ở giữa, sau tên) hoặc bleed (G to hơn, tràn ra mép trái).
// Usage / Cách dùng (on a Mac): swiftc draw-installer-images.swift -o draw && ./draw <app-icon.png> <name> <short line> <centred|bleed> <output folder>
let a = CommandLine.arguments
let logo = NSImage(contentsOfFile: a[1])!, name = a[2], line = a[3], layout = a[4], out = a[5]
func png(_ w: Int, _ h: Int, _ file: String, _ draw: () -> Void) {
    let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: w, pixelsHigh: h, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true,
                               isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    NSGraphicsContext.saveGraphicsState(); NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    draw(); NSGraphicsContext.restoreGraphicsState()
    try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: out + "/" + file + ".png"))
}
func text(_ s: String, _ r: NSRect, _ size: CGFloat, _ weight: NSFont.Weight, _ color: NSColor, kern: CGFloat = 0) {
    let p = NSMutableParagraphStyle(); p.alignment = .center
    (s as NSString).draw(in: r, withAttributes: [.font: NSFont.systemFont(ofSize: size, weight: weight), .foregroundColor: color, .paragraphStyle: p, .kern: kern])
}
func gray(_ v: Int) -> NSColor { NSColor(calibratedRed: CGFloat(v)/255, green: CGFloat(v)/255, blue: CGFloat(v + 6)/255, alpha: 1) }
png(493, 312, "dialog") {
    NSColor.white.setFill(); NSRect(x: 0, y: 0, width: 493, height: 312).fill()
    let col = NSRect(x: 0, y: 0, width: 164, height: 312)
    NSGradient(starting: gray(46), ending: gray(22))!.draw(in: col, angle: -90)
    NSGraphicsContext.saveGraphicsState(); NSBezierPath(rect: col).addClip()
    let g = NSColor(calibratedWhite: 1, alpha: 0.07)
    if layout == "bleed" { text("G", NSRect(x: -120, y: 30, width: 320, height: 320), 280, .heavy, g) }
    else { text("G", NSRect(x: -43, y: 46, width: 250, height: 250), 210, .heavy, g) }
    NSGraphicsContext.restoreGraphicsState()
    // the name sits on the middle of the G, the short line under it
    // tên nằm giữa chữ G, dòng ngắn ngay dưới
    text(name, NSRect(x: 0, y: 162, width: 164, height: 28), 20, .semibold, .white)
    text(line.uppercased(), NSRect(x: 0, y: 140, width: 164, height: 16), 9.5, .medium, NSColor(calibratedWhite: 1, alpha: 0.55), kern: 1.4)
}
png(493, 58, "banner") {
    NSColor.white.setFill(); NSRect(x: 0, y: 0, width: 493, height: 58).fill()
    logo.draw(in: NSRect(x: 493 - 44 - 10, y: 7, width: 44, height: 44))
}
