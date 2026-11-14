#!/usr/bin/env python3
"""Checks the two-language rules. Usage: python3 tests/check-i18n.py [--comments] [path prefix ...]
Kiểm các quy tắc hai ngôn ngữ. Cách dùng: python3 tests/check-i18n.py [--comments] [đầu đường dẫn ...]

1. Vietnamese appears only in dictionaries, comments, *.vi.* documents, say "en" "vi" lines, or lines marked i18n-allow.
   Tiếng Việt chỉ nằm trong từ điển, chú thích, tài liệu *.vi.*, dòng say "en" "vi", hoặc dòng có dấu i18n-allow.
2. Every tx("...") text has a Vietnamese entry, and every entry is used.
   Mọi chữ trong tx("...") đều có bản tiếng Việt, và mọi mục trong từ điển đều được dùng.
3. With --comments: every comment has an English line followed by a Vietnamese line.
   Khi có --comments: mọi chú thích đều có dòng tiếng Anh rồi đến dòng tiếng Việt.
"""
import ast
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VI_CHARS = "àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ"
VI_RE = re.compile("[" + VI_CHARS + VI_CHARS.upper() + "]")
SKIP = re.compile(r"(^|/)(three\.js|three\.LICENSE|qrcode\.js|.*\.json)$|^skills/(ui-ux-pro-max|security-audit|browser-testing-with-devtools|codebase-design|diagnosing-bugs|domain-modeling|grilling|improve-codebase-architecture|interview-me|tdd)/")
DICT = re.compile(r"(\.vi\.(js|ts|md|txt|svg)$|webhook_vi\.py$)")
LINE_COMMENT = {".js": "//", ".ts": "//", ".tsx": "//", ".py": "#", ".sh": "#", ".command": "#", ".ps1": "#", ".caddy": "#", ".yml": "#", ".bat": "::", ".example": "#", ".swift": "//", ".cs": "//", ".toml": "#"}
TEXT_T = re.compile(r"""\btx\(\s*(?:'((?:\\.|[^'\\])*)'|"((?:\\.|[^"\\])*)"|`((?:\\.|[^`\\])*)`)""")
GROUPS = {
    "server/webhook_vi.py": ["server/webhook.py"] + sorted("server/board/" + f for f in os.listdir(os.path.join(ROOT, "server", "board")) if f.endswith(".py")),
    "server/static/ops.vi.js": ["server/static/ops.js", "server/static/ops3d.js", "server/static/page.js", "server/static/map-common.js",
                                "server/static/map2d.js", "server/static/map25d.js", "server/static/map3d.js"],
    "server/static/admin.vi.js": ["server/static/admin.js"],
    "web/index.vi.js": ["web/index.html"],
    "hooks/lang.vi.ts": ["hooks/activity.ts", "hooks/board.ts", "hooks/edits.ts", "hooks/help.ts", "hooks/office.ts", "hooks/register.tsx", "hooks/team.ts", "hooks/update.ts", "hooks/voice.ts", "hooks/workers.ts"],
}


def unescape(s):
    return s.replace("\\'", "'").replace('\\"', '"').replace("\\`", "`").replace("\\n", "\n")


def texts_in(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        src = f.read()
    return {unescape(a or b or c) for a, b, c in TEXT_T.findall(src)}


def keys_in(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        src = f.read()
    if path.endswith(".py"):
        return set(ast.literal_eval(src[src.index("VI = {") + 5:].strip()).keys())
    keys = re.findall(r"""^\s*(?:'((?:\\.|[^'\\])*)'|"((?:\\.|[^"\\])*)"|`((?:\\.|[^`\\])*)`)\s*:""", src, re.M)
    return {unescape(a or b or c) for a, b, c in keys}


def comment_of(line, marker):
    s = line.strip()
    if s.startswith(marker):
        return s[len(marker):].strip()
    return None


def check_comments(path, lines, marker, out):
    i = 0
    while i < len(lines):
        if comment_of(lines[i], marker) is None or lines[i].lstrip().startswith("#!"):
            i += 1
            continue
        start = i
        block = []
        while i < len(lines) and comment_of(lines[i], marker) is not None:
            block.append(comment_of(lines[i], marker))
            i += 1
        vi = [bool(VI_RE.search(b)) for b in block]
        if not any(vi) or all(vi):
            out.append("%s:%d comment needs English then Vietnamese: %s" % (path, start + 1, block[0][:70]))
        elif vi[0]:
            out.append("%s:%d comment must start with English: %s" % (path, start + 1, block[0][:70]))


def main():
    args = [a for a in sys.argv[1:] if a != "--comments"]
    want_comments = "--comments" in sys.argv
    files = subprocess.check_output(["git", "ls-files", "-co", "--exclude-standard"], cwd=ROOT, text=True).split("\n")
    problems = []
    for path in files:
        if not path or SKIP.search(path) or (args and not any(path.startswith(a) for a in args)):
            continue
        full = os.path.join(ROOT, path)
        if not os.path.isfile(full) or path == "tests/check-i18n.py":
            continue
        try:
            with open(full, encoding="utf-8-sig") as f:
                lines = f.read().split("\n")
        except UnicodeDecodeError:
            continue
        ext = os.path.splitext(path)[1]
        marker = "#" if os.path.basename(path) in (".gitignore", ".gitattributes", "allowed_signers") else LINE_COMMENT.get(ext)
        if not DICT.search(path):
            in_block = False
            for n, line in enumerate(lines, 1):
                if not VI_RE.search(line) or "i18n-allow" in line:
                    pass
                elif marker and comment_of(line, marker) is not None:
                    pass
                elif ext == ".css" or in_block:
                    pass
                elif re.match(r"\s*(say|Say-Text|call :say)\b", line):
                    pass
                elif ext == ".py" and ('"""' in line or line.startswith(" ")) and path.endswith(".py") and is_docstring_line(lines, n - 1):
                    pass
                elif re.match(r"\s*(<!--|/\*)", line):
                    pass
                elif path.endswith((".md",)) and line.startswith("description:"):
                    pass
                else:
                    problems.append("%s:%d Vietnamese in code: %s" % (path, n, line.strip()[:80]))
        if want_comments and marker and not DICT.search(path):
            check_comments(path, lines, marker, problems)
    for dict_path, sources in GROUPS.items():
        if args and not any(p.startswith(a) for a in args for p in [dict_path] + sources):
            continue
        keys = keys_in(dict_path)
        used = set()
        for src in sources:
            if os.path.isfile(os.path.join(ROOT, src)):
                used |= texts_in(src)
        for missing in sorted(used - keys):
            problems.append("%s: missing Vietnamese for: %s" % (dict_path, missing[:90]))
        for extra in sorted(keys - used):
            problems.append("%s: entry not used in code: %s" % (dict_path, extra[:90]))
        for key in keys:
            if VI_RE.search(key):
                problems.append("%s: key is not English: %s" % (dict_path, key[:90]))
    print("\n".join(problems) if problems else "OK")
    print("%d problem(s)" % len(problems))
    return 1 if problems else 0


def is_docstring_line(lines, idx):
    quotes = sum(line.count('"""') for line in lines[:idx])
    return quotes % 2 == 1 or '"""' in lines[idx]


if __name__ == "__main__":
    sys.exit(main())
