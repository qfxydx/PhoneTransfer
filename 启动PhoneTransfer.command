#!/bin/bash
# Phone Transfer — 桌面 CS 客户端启动器
cd "$(dirname "$0")"
export PATH="$HOME/Library/Android/sdk/platform-tools:$HOME/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

# Do not force-kill unrelated processes or other applications on port 8765.
# Launching PhoneTransfer must never terminate users' running programs.

PY=""
# 优先用已安装 PySide6 的 python
for candidate in \
  "$HOME/.pyenv/versions/3.12.13/bin/python3" \
  "$HOME/.pyenv/shims/python3" \
  "$(command -v python3)"
do
  if [ -x "$candidate" ] && "$candidate" -c "import PySide6" 2>/dev/null; then
    PY="$candidate"
    break
  fi
done

if [ -z "$PY" ]; then
  osascript -e 'display dialog "未找到 PySide6。请在终端执行：\npython3 -m pip install --user PySide6" buttons {"好"} default button 1'
  exit 1
fi

exec "$PY" "$(dirname "$0")/phone_transfer.py"
