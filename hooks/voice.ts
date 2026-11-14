// Speaking instead of typing. The plugin brings no speech recognition of its own: it points the person at the dictation
// their computer already has, which covers Vietnamese, and opens the settings page where it is turned on.
// It changes no setting: turning the microphone on stays the person's own click.
// Nói thay vì gõ. Plugin không mang theo bộ nhận giọng nói nào: nó chỉ người dùng tới tính năng đọc chính tả
// mà máy họ đã có sẵn, có tiếng Việt, và mở trang cài đặt nơi bật tính năng đó.
// Nó không đổi cài đặt nào: bật micro vẫn là cú bấm của chính người dùng.
import { tx } from './lang'

export type VoiceSystem = 'Mac' | 'Windows' | 'Linux'

/** The command that opens the settings page for dictation. Linux has no such page the plugin knows of. */
/** Lệnh mở trang cài đặt của tính năng đọc chính tả. Trên Linux plugin không biết trang nào như vậy. */
export function voiceSettingsCommand(system: VoiceSystem): string[] | undefined {
  if (system === 'Mac') return ['open', 'x-apple.systempreferences:com.apple.Keyboard-Settings.extension?Dictation']
  if (system === 'Windows') return ['cmd', '/d', '/c', 'start', 'ms-settings:regionlanguage']
  return undefined
}

/** The steps for this system. `opened` says whether the settings page is already in front of the person. */
/** Các bước cho hệ này. `opened` cho biết trang cài đặt đã mở sẵn trước mặt người dùng hay chưa. */
export function voiceSteps(system: VoiceSystem, opened: boolean): string {
  if (system === 'Mac') {
    return [
      tx("Speak instead of typing with the dictation this Mac already has. It works in any box you can type in, Claude's message box too, and it has Vietnamese."),
      '',
      opened ? tx('The Keyboard page of System Settings is now open. Do this once:') : tx('Open the Apple menu, then System Settings, then Keyboard. Do this once:'),
      tx('1. Scroll down to "Dictation". Turn the switch on and click "Enable" (skip this if the switch is already on). If it asks about sharing recordings with Apple, click "Not Now".'),
      tx('2. Next to "Languages", click "Edit" and tick the language you will speak, for example Vietnamese.'),
      tx('3. Back in Claude, click in the message box, press the microphone key in the top row of the keyboard once and let go (holding it down calls Siri instead). When the microphone sign shows by the cursor, speak. Press Esc when you are done, then send.'),
      '',
      tx('No microphone key? The "Shortcut" line under "Dictation" shows the keys to press instead.'),
      tx('The small text under "Dictation" says whether your voice is turned into text on this Mac or sent to Apple. If it is sent, do not say names of people or internal figures aloud.'),
    ].join('\n')
  }
  if (system === 'Windows') {
    return [
      tx("Speak instead of typing with the voice typing Windows already has. It works in any box you can type in, Claude's message box too, and it has Vietnamese."),
      '',
      opened ? tx('The "Language & region" page of Settings is now open. Do this once:') : tx('Open Start, then Settings, then "Time & language", then "Language & region". Do this once:'),
      tx('1. If the language you will speak (for example Vietnamese) is not in the list, click "Add a language", pick it and follow the steps to install it. If it is there already, close the window.'),
      tx('2. Back in Claude, click in the message box. Press the Windows key + Space until that language is chosen.'),
      tx('3. Press the Windows key + H, wait for "Listening...", and speak. Click the microphone on the small voice typing bar to stop, then send.'),
      '',
      tx('Windows needs the internet for this and sends your voice to Microsoft to turn it into text. Do not say names of people or internal figures aloud.'),
    ].join('\n')
  }
  return tx('On Linux the plugin knows no built-in dictation to open. Type your message, or use a dictation tool your admin has approved.')
}
