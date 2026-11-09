# PNG (8-bit RGB/RGBA) to a 24-bit BMP on white, for the Windows Installer bitmap controls. Usage: python3 png-to-bmp.py in.png out.bmp
# Đổi PNG (RGB/RGBA 8-bit) thành BMP 24-bit trên nền trắng, cho ô hình của Windows Installer. Cách dùng: python3 png-to-bmp.py vao.png ra.bmp
import sys, zlib, struct
def read_png(p):
    d = open(p, "rb").read(); i = 8; idat = b""
    while i < len(d):
        n, t = struct.unpack(">I4s", d[i:i+8]); c = d[i+8:i+8+n]; i += 12 + n
        if t == b"IHDR": w, h, bd, ct = struct.unpack(">IIBB", c[:10]); assert bd == 8 and ct in (2, 6)
        elif t == b"IDAT": idat += c
    bpp = 4 if ct == 6 else 3; raw = zlib.decompress(idat); stride = w * bpp; rows = []; prev = bytearray(stride); j = 0
    for _ in range(h):
        f = raw[j]; j += 1; line = bytearray(raw[j:j+stride]); j += stride
        for x in range(stride):
            a = line[x-bpp] if x >= bpp else 0; b = prev[x]; c2 = prev[x-bpp] if x >= bpp else 0
            if f == 1: line[x] = (line[x] + a) & 255
            elif f == 2: line[x] = (line[x] + b) & 255
            elif f == 3: line[x] = (line[x] + (a + b) // 2) & 255
            elif f == 4:
                pa, pb, pc = abs(b - c2), abs(a - c2), abs(a + b - 2 * c2)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c2)) & 255
        rows.append(bytes(line)); prev = line
    return w, h, bpp, rows
w, h, bpp, rows = read_png(sys.argv[1]); pad = (4 - w * 3 % 4) % 4; body = b""
for y in range(h - 1, -1, -1):
    r = rows[y]; out = bytearray()
    for x in range(w):
        R, G, B = r[x*bpp:x*bpp+3]; A = r[x*bpp+3] if bpp == 4 else 255
        out += bytes((B * A // 255 + 255 - A, G * A // 255 + 255 - A, R * A // 255 + 255 - A))
    body += bytes(out) + b"\0" * pad
open(sys.argv[2], "wb").write(struct.pack("<2sIHHI", b"BM", 54 + len(body), 0, 0, 54) + struct.pack("<IiiHHIIiiII", 40, w, h, 1, 24, 0, len(body), 2835, 2835, 0, 0) + body)
