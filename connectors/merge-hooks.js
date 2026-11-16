// Add the AI Worker connector's hooks to a tool's JSON settings file, or take them out, without touching anything else in it.
// Thêm các hook của bộ nối AI Worker vào file cấu hình JSON của một công cụ, hoặc gỡ chúng ra, mà không đụng tới thứ gì khác trong file.
//
//   add     <settings file> <file holding only our hooks>   merges our hooks in; a hook of ours already there is replaced
//   remove  <settings file>                                  takes our hooks out
//   add     <file cấu hình> <file chỉ chứa hook của ta>      gộp hook của ta vào; hook của ta đã có sẵn thì được thay
//   remove  <file cấu hình>                                  gỡ hook của ta ra
//
// Prints "changed", "same" or "empty" (nothing but our hooks was in the file, and they are gone now).
// A file that is not plain JSON, for example one with comments, is left as it is and the program fails.
// In ra "changed", "same" hoặc "empty" (file chỉ có hook của ta, và giờ chúng đã được gỡ).
// File không phải JSON thuần, ví dụ có chú thích, thì được để nguyên và chương trình báo lỗi.
//
// Runs with what the computer already has: `osascript -l JavaScript` on macOS, `node` elsewhere.
// Chạy bằng thứ máy đã có sẵn: `osascript -l JavaScript` trên macOS, `node` ở nơi khác.

// every command of ours holds this name, which is how a hook of ours is told from the person's own
// mọi lệnh của ta đều chứa tên này, nhờ đó phân biệt được hook của ta với hook của chính người dùng
const MARK = 'ai-worker-hook'

const isOurs = entry => typeof (entry && entry.command) === 'string' && entry.command.includes(MARK)

// One event's list without our hooks. Codex and Gemini CLI keep hooks inside groups ({hooks: [...]}), Cursor keeps them flat.
// A group is dropped only when taking our hook out left it empty.
// Danh sách của một sự kiện sau khi bỏ hook của ta. Codex và Gemini CLI để hook trong nhóm ({hooks: [...]}), Cursor để phẳng.
// Một nhóm chỉ bị bỏ khi việc gỡ hook của ta làm nó rỗng.
function withoutOurs(list) {
  const out = []
  for (const entry of list) {
    if (isOurs(entry)) continue
    if (entry && Array.isArray(entry.hooks) && entry.hooks.some(isOurs)) {
      const rest = entry.hooks.filter(h => !isOurs(h))
      if (rest.length) out.push(Object.assign({}, entry, { hooks: rest }))
      continue
    }
    out.push(entry)
  }
  return out
}

function isObject(v) {
  return !!v && typeof v === 'object' && !Array.isArray(v)
}

function parse(text, name) {
  let data
  try {
    data = JSON.parse(text.replace(/^﻿/, ''))
  } catch (e) {
    throw new Error(name + ' is not plain JSON: ' + e.message)
  }
  if (!isObject(data)) throw new Error(name + ' does not hold a JSON object')
  if (data.hooks !== undefined && !isObject(data.hooks)) throw new Error(name + ': "hooks" is not an object')
  return data
}

// The new text of the settings file, and what happened to it.
// Nội dung mới của file cấu hình, và điều đã xảy ra với nó.
function merge(action, text, oursText) {
  const data = parse(text, 'the settings file')
  const before = JSON.stringify(data)
  const hooks = data.hooks || {}
  for (const event of Object.keys(hooks)) {
    if (!Array.isArray(hooks[event])) continue
    hooks[event] = withoutOurs(hooks[event])
    if (!hooks[event].length) delete hooks[event]
  }
  if (action === 'add') {
    const ours = parse(oursText, 'the connector hooks')
    for (const key of Object.keys(ours)) {
      if (key !== 'hooks' && data[key] === undefined) data[key] = ours[key]
    }
    for (const event of Object.keys(ours.hooks || {})) hooks[event] = (Array.isArray(hooks[event]) ? hooks[event] : []).concat(ours.hooks[event])
    data.hooks = hooks
  } else if (data.hooks !== undefined) {
    if (Object.keys(hooks).length) data.hooks = hooks
    else delete data.hooks
  }
  const left = Object.keys(data).filter(k => k !== 'version' && k !== 'description')
  const result = JSON.stringify(data) === before ? 'same' : action === 'remove' && !left.length ? 'empty' : 'changed'
  return { text: JSON.stringify(data, null, 2) + '\n', result }
}

function main(argv, io) {
  const [action, file, oursFile] = argv
  if ((action !== 'add' && action !== 'remove') || !file || (action === 'add' && !oursFile)) throw new Error('usage: merge-hooks.js add <file> <ours> | remove <file>')
  const text = io.read(file)
  if (text === null) throw new Error('cannot read ' + file)
  const oursText = action === 'add' ? io.read(oursFile) : ''
  if (oursText === null) throw new Error('cannot read ' + oursFile)
  const out = merge(action, text, oursText)
  if (out.result !== 'same') io.write(file, out.text)
  return out.result
}

if (typeof ObjC !== 'undefined') {
  // macOS: osascript calls run() with the arguments and prints what it returns
  // macOS: osascript gọi run() với các tham số và in ra giá trị trả về
  ObjC.import('Foundation')
  var run = argv =>
    main(argv, {
      read: path => {
        const s = $.NSString.stringWithContentsOfFileEncodingError(path, $.NSUTF8StringEncoding, null)
        return s.isNil() ? null : s.js
      },
      write: (path, text) => {
        if (!$(text).writeToFileAtomicallyEncodingError(path, true, $.NSUTF8StringEncoding, null)) throw new Error('cannot write ' + path)
      },
    })
} else {
  const fs = require('fs')
  try {
    console.log(
      main(process.argv.slice(2), {
        read: path => {
          try {
            return fs.readFileSync(path, 'utf8')
          } catch (e) {
            return null
          }
        },
        write: (path, text) => fs.writeFileSync(path, text),
      }),
    )
  } catch (e) {
    console.error(e.message)
    process.exit(1)
  }
}
