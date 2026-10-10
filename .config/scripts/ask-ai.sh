#!/usr/bin/env bash
# ask-ai: quick AI question from anywhere.
#
# Prompts via fuzzel, sends the question to the first available backend
# (GitHub Copilot CLI, gh copilot extension, llm, or a local ollama), shows
# the answer as a notification and copies it to the clipboard.
#
# Prefix your question with "clip:" to append the clipboard as context.
# Bound to Mod+Shift+A in niri and the  button in waybar.
set -uo pipefail

q=$(printf "" | fuzzel --dmenu --prompt="ai> " --lines=0 --width=60 \
        --placeholder="ask anything — prefix clip: to include clipboard") || exit 0
[ -n "$q" ] || exit 0

case "$q" in
    clip:*) q="${q#clip:} — context: $(wl-paste --no-newline 2>/dev/null | head -c 2000)" ;;
esac

answer=""
if command -v copilot >/dev/null 2>&1; then
    answer=$(copilot -p "$q" 2>/dev/null)
elif gh extension list 2>/dev/null | grep -q gh-copilot; then
    answer=$(gh copilot explain "$q" 2>/dev/null)
elif command -v llm >/dev/null 2>&1; then
    answer=$(llm "$q" 2>/dev/null)
elif command -v ollama >/dev/null 2>&1; then
    model=$(ollama list 2>/dev/null | awk 'NR==2{print $1}')
    [ -n "$model" ] && answer=$(ollama run "$model" "$q" 2>/dev/null)
fi

if [ -z "$answer" ]; then
    notify-send -u critical "ask-ai" \
        "No AI backend found. Install one of: GitHub Copilot CLI, gh copilot extension, llm, ollama."
    exit 1
fi

printf '%s' "$answer" | wl-copy
notify-send "ask-ai (copied to clipboard)" "$(printf '%s' "$answer" | head -c 1000)"
