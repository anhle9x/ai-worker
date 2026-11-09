#!/usr/bin/env python3
"""Checks that the map shaders and fly-to animations use names the JavaScript really sets. Usage: python3 tests/check-maps.py [files...]
  Kiểm shader và hiệu ứng bay của bản đồ chỉ dùng tên mà JavaScript thật sự gán. Cách dùng: python3 tests/check-maps.py [các file...]

1. Every `uniform <type> <name>` in a shader is given a value: a key of a shared `const U = {...}` or of a `uniforms: {...}` in the same file.
   Mọi `uniform <kiểu> <tên>` trong shader đều được gán giá trị: là khoá của `const U = {...}` dùng chung hoặc của `uniforms: {...}` trong cùng file.
2. Every `#ifdef NAME` has NAME in a `defines: {...}` of the same file.
   Mọi `#ifdef TÊN` đều có TÊN trong `defines: {...}` của cùng file.
3. Every key animated by `for (const k of [...]) v[k] = flight...` is a real view key, used as `v.<key>`.
   Mọi khoá được bay trong `for (const k of [...]) v[k] = flight...` đều là khoá thật của góc nhìn, có dùng dạng `v.<khoá>`.
An unmatched name makes WebGL read 0, so the globe draws nothing and the flight goes nowhere, with no error in the console.
  Tên không khớp thì WebGL đọc ra 0, địa cầu không vẽ gì và hiệu ứng bay đứng yên, không báo lỗi gì trong console.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = ["server/static/map-common.js", "server/static/map2d.js", "server/static/map25d.js", "server/static/map3d.js"]
UNIFORM = re.compile(r"\buniform\s+\w+\s+(\w+)\s*;")
IFDEF = re.compile(r"#ifn?def\s+(\w+)")
FLIGHT = re.compile(r"for\s*\(\s*const\s+k\s+of\s+\[([^\]]*)\]\s*\)\s*v\[k\]\s*=\s*flight")


def braced(text, start):
    # the {...} that opens at text[start], matching nested braces
    # đoạn {...} mở tại text[start], khớp cả ngoặc lồng nhau
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1:i]
    return text[start + 1:]


def top_keys(body):
    # keys at the top level of an object literal body
    # các khoá ở tầng ngoài cùng của một object literal
    keys, depth = set(), 0
    for m in re.finditer(r"[{}]|(?<![\w.])(\w+)\s*:", body):
        if m.group(0) == "{":
            depth += 1
        elif m.group(0) == "}":
            depth -= 1
        elif depth == 0:
            keys.add(m.group(1))
    return keys


def objects_after(text, pattern):
    # each object literal right after the pattern, also the ones in `a ? {...} : {...}`
    # từng object literal ngay sau mẫu, kể cả trong `a ? {...} : {...}`
    for m in re.finditer(pattern, text):
        i = m.end()
        line_end = text.find("\n", i)
        while i < len(text) and i != line_end:
            if text[i] == "{":
                body = braced(text, i)
                yield body
                i += len(body) + 2
                rest = text[i:i + 40]
                if not re.match(r"\s*:\s*\{|\s*:\s*[\w.]+\s*\?", rest):
                    break
            elif text[i] in ",)":
                break
            else:
                i += 1


def check(paths):
    texts = {p: open(os.path.join(ROOT, p), encoding="utf-8").read() for p in paths}
    problems = []
    shared = {}
    for p, text in texts.items():
        for body in objects_after(text, r"\bconst\s+U\s*=\s*"):
            shared[p] = top_keys(body)
    # map-common.js gets U from its callers, so every caller must hand it the same names
    # map-common.js nhận U từ nơi gọi, nên mọi nơi gọi phải đưa cùng một bộ tên
    if len({frozenset(k) for k in shared.values()}) > 1:
        problems.append("const U differs between files: " + ", ".join(f"{p} {sorted(k)}" for p, k in shared.items()))
    all_shared = set().union(*shared.values()) if shared else set()
    for p, text in texts.items():
        given = set(shared.get(p, all_shared))
        for body in objects_after(text, r"\buniforms\s*:\s*"):
            given |= top_keys(body)
        defines = set()
        for body in objects_after(text, r"\bdefines\s*:\s*"):
            defines |= top_keys(body)
        for m in UNIFORM.finditer(text):
            if m.group(1) not in given:
                line = text.count("\n", 0, m.start()) + 1
                problems.append(f"{p}:{line}: shader uniform '{m.group(1)}' is never given a value (known: {', '.join(sorted(given))})")
        for m in IFDEF.finditer(text):
            if m.group(1) not in defines:
                line = text.count("\n", 0, m.start()) + 1
                problems.append(f"{p}:{line}: '#ifdef {m.group(1)}' but no defines: {{ {m.group(1)}: ... }}")
        for m in FLIGHT.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            for key in re.findall(r"['\"](\w+)['\"]", m.group(1)):
                if not re.search(r"\bv\." + re.escape(key) + r"\b", text):
                    problems.append(f"{p}:{line}: flight animates '{key}' but the view never uses v.{key}")
    return problems


def main():
    paths = sys.argv[1:] or FILES
    problems = check(paths)
    for line in problems:
        print(line)
    if problems:
        print(f"{len(problems)} problem(s)")
        sys.exit(1)
    print(f"maps OK: {len(paths)} files")


if __name__ == "__main__":
    main()
