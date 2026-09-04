#!/bin/bash
# 把本仓库的插件安装或刷新到本机 Codex（本地市场 china-trip-weaver-local）。
# 用法：scripts/install_local_plugin.sh            安装或刷新，然后校验
#       scripts/install_local_plugin.sh --check    只校验，不改任何配置
#       scripts/install_local_plugin.sh --skill-smoke  只用 Codex 解析一次源码 SKILL.md
# 环境变量：CODEX_BIN 指定 codex 可执行文件；CODEX_HOME 指向隔离目录时只影响该目录（用于测试）。
set -eu

case "${1:-}" in
  "") MODE="install" ;;
  --check) MODE="check" ;;
  --skill-smoke) MODE="skill-smoke" ;;
  *) echo "未知参数：$1（可用：--check、--skill-smoke）" >&2; exit 2 ;;
esac

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PLUGIN_DIR="$REPO/plugins/china-trip-weaver"
MARKET="china-trip-weaver-local"
PLUGIN="china-trip-weaver"
SELECTOR="$PLUGIN@$MARKET"
HOME_DIR="${CODEX_HOME:-$HOME/.codex}"

if [ -n "${CODEX_BIN:-}" ]; then
  CODEX="$CODEX_BIN"
elif command -v codex >/dev/null 2>&1; then
  CODEX="$(command -v codex)"
elif [ -x "/Applications/ChatGPT.app/Contents/Resources/codex" ]; then
  CODEX="/Applications/ChatGPT.app/Contents/Resources/codex"
else
  echo "找不到 codex 可执行文件；请设置 CODEX_BIN" >&2; exit 2
fi

skill_parser_smoke() {
  SMOKE_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/ctw-skill-smoke.XXXXXX")"
  SMOKE_CODEX_HOME="$SMOKE_ROOT/codex-home"
  SMOKE_USER_HOME="$SMOKE_ROOT/home"
  SMOKE_OUTPUT="$SMOKE_ROOT/prompt-input.json"
  trap 'chmod -R u+w "$SMOKE_ROOT"; rm -rf "$SMOKE_ROOT"' EXIT HUP INT TERM
  mkdir -p "$SMOKE_CODEX_HOME/skills" "$SMOKE_USER_HOME"

  SKILL_NAMES=""
  SKILL_COUNT=0
  for SKILL_DIR in "$PLUGIN_DIR"/skills/*; do
    if [ ! -d "$SKILL_DIR" ]; then continue; fi
    SKILL_NAME="$(basename "$SKILL_DIR")"
    if [ ! -r "$SKILL_DIR/SKILL.md" ]; then
      echo "SKILL parser smoke 失败：读不到 $SKILL_DIR/SKILL.md" >&2
      exit 6
    fi
    mkdir -p "$SMOKE_CODEX_HOME/skills/$SKILL_NAME"
    cp "$SKILL_DIR/SKILL.md" "$SMOKE_CODEX_HOME/skills/$SKILL_NAME/SKILL.md"
    SKILL_NAMES="$SKILL_NAMES $SKILL_NAME"
    SKILL_COUNT=$((SKILL_COUNT + 1))
  done
  if [ "$SKILL_COUNT" -eq 0 ]; then
    echo "SKILL parser smoke 失败：源码中没有 Skill" >&2
    exit 6
  fi

  HOME="$SMOKE_USER_HOME" CODEX_HOME="$SMOKE_CODEX_HOME" \
    "$CODEX" -C "$REPO" debug prompt-input "Inspect the available skills." > "$SMOKE_OUTPUT"
  /usr/bin/python3 -c 'import json,sys
payload = json.dumps(json.load(open(sys.argv[1], encoding="utf-8")), ensure_ascii=False)
missing = [name for name in sys.argv[2:] if ("- " + name + ":") not in payload]
if missing:
    print("SKILL parser smoke 失败：Codex 未读到 " + ", ".join(missing), file=sys.stderr)
    raise SystemExit(6)' "$SMOKE_OUTPUT" $SKILL_NAMES
  echo "SKILL parser smoke: OK ($SKILL_COUNT SKILL.md via codex debug prompt-input)"
}

VERSION="$(/usr/bin/python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' "$PLUGIN_DIR/.codex-plugin/plugin.json")"
echo "codex: $CODEX"
echo "源码: $PLUGIN_DIR (manifest 版本 $VERSION)"
echo "Codex home: $HOME_DIR"

skill_parser_smoke
if [ "$MODE" = "skill-smoke" ]; then exit 0; fi

# 1. 市场是否已注册且指向本仓库
ROOT="$("$CODEX" plugin marketplace list 2>/dev/null | awk -v m="$MARKET" '$1==m {print $2}')"
if [ -z "$ROOT" ]; then
  if [ "$MODE" = "check" ]; then echo "未注册本地市场 $MARKET" ; exit 3; fi
  "$CODEX" plugin marketplace add "$REPO" >/dev/null
  echo "已注册本地市场 $MARKET -> $REPO"
elif [ "$ROOT" != "$REPO" ]; then
  echo "本地市场 $MARKET 指向别的路径: $ROOT" >&2
  echo "请先执行: $CODEX plugin marketplace remove $MARKET，再重跑本脚本" >&2
  exit 4
else
  echo "本地市场已注册 -> $ROOT"
fi

# 2. 安装或刷新（plugin add 对已安装的本地插件会用源码刷新缓存）
if [ "$MODE" = "install" ]; then
  "$CODEX" plugin add "$SELECTOR" >/dev/null
  echo "已执行 plugin add $SELECTOR"
fi

# 3. 校验：状态、版本、缓存与源码一致
LINE="$("$CODEX" plugin list 2>/dev/null | grep -F "$SELECTOR" || true)"
if [ -z "$LINE" ]; then echo "校验失败：plugin list 里没有 $SELECTOR" >&2; exit 5; fi
STATUS="$(echo "$LINE" | grep -oE 'installed, (enabled|disabled)|available' | head -1)"
INSTALLED_VERSION="$(echo "$LINE" | awk '{print $4}')"
CACHE="$HOME_DIR/plugins/cache/$MARKET/$PLUGIN/$VERSION"
echo "plugin list: $STATUS $INSTALLED_VERSION"
FAIL=0
if [ "$STATUS" != "installed, enabled" ]; then echo "校验失败：状态不是 installed, enabled" >&2; FAIL=1; fi
if [ "$INSTALLED_VERSION" != "$VERSION" ]; then echo "校验失败：已装版本 $INSTALLED_VERSION 与源码 $VERSION 不一致" >&2; FAIL=1; fi
if [ ! -d "$CACHE" ]; then echo "校验失败：缓存目录不存在 $CACHE" >&2; FAIL=1;
elif ! diff -rq -x __pycache__ -x '*.pyc' "$PLUGIN_DIR" "$CACHE" >/dev/null; then
  echo "校验失败：缓存与源码不一致（先跑不带 --check 的本脚本刷新）" >&2
  diff -rq -x __pycache__ -x '*.pyc' "$PLUGIN_DIR" "$CACHE" | head -5 >&2; FAIL=1
fi
if [ "$FAIL" -ne 0 ]; then exit 1; fi
echo "OK：$SELECTOR $VERSION 已安装且缓存与源码一致"
if [ "$MODE" = "install" ]; then echo "提醒：在 Codex 里新建一个任务才会加载新版本；若 Skill 未出现，重启 Codex 桌面版"; fi
