# Language of the install scripts. Usage: say "English text" "Vietnamese text". AI_WORKER_LANG=en or vi overrides the system.
# Ngôn ngữ của file cài. Cách dùng: say "English text" "Tiếng Việt". AI_WORKER_LANG=en hoặc vi thắng ngôn ngữ của hệ thống.
case "${AI_WORKER_LANG:-${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}}" in
  vi*) AI_WORKER_LANG=vi ;;
  *) AI_WORKER_LANG=en ;;
esac
export AI_WORKER_LANG
say() { if [ "$AI_WORKER_LANG" = vi ]; then printf '%s\n' "$2"; else printf '%s\n' "$1"; fi; }
