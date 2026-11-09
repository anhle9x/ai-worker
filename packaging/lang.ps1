# Language of the PowerShell install scripts. Usage: Say-Text "English text" "Vietnamese text". AI_WORKER_LANG=en or vi overrides the system.
# Ngôn ngữ của file cài PowerShell. Cách dùng: Say-Text "English text" "Tiếng Việt". AI_WORKER_LANG=en hoặc vi thắng ngôn ngữ của hệ thống.
# Order: AI_WORKER_LANG, then the Windows language (Get-Culture), then English.
# Thứ tự: AI_WORKER_LANG, rồi ngôn ngữ của Windows (Get-Culture), rồi tiếng Anh.
if (-not $env:AI_WORKER_LANG) {
  try { $env:AI_WORKER_LANG = (Get-Culture).TwoLetterISOLanguageName } catch { }
}
if ("$env:AI_WORKER_LANG" -like 'vi*') { $env:AI_WORKER_LANG = 'vi' } else { $env:AI_WORKER_LANG = 'en' }
# -AsString returns the text instead of printing it (for prompts); -NoNewline prints without a line break
# -AsString trả về chữ thay vì in ra (cho câu hỏi); -NoNewline in ra không xuống dòng
function Say-Text([string]$En, [string]$Vi, [switch]$AsString, [switch]$NoNewline) {
  $text = if ($env:AI_WORKER_LANG -eq 'vi') { $Vi } else { $En }
  if ($AsString) { return $text }
  if ($NoNewline) { Write-Host $text -NoNewline } else { Write-Host $text }
}
