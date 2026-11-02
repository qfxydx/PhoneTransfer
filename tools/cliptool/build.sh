#!/usr/bin/env bash
# ==============================================================================
# PhoneTransfer ClipTool Build Script
# 编译 ClipTool.java 并使用 d8 构建包含 classes.dex 的 pt_clip.jar
# ==============================================================================
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$DIR/../.." && pwd)"

# 1. 探测 Android SDK 路径
SDK_DIR="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-$HOME/Library/Android/sdk}}"

if [ ! -d "$SDK_DIR" ]; then
  echo "[ERROR] 未找到 Android SDK 目录: $SDK_DIR"
  echo "请设置环境变量 ANDROID_HOME 或安装 Android Studio / Command Line Tools。"
  exit 1
fi

# 查找最新的 android.jar
ANDROID_JAR=$(find "$SDK_DIR/platforms" -name "android.jar" 2>/dev/null | sort -V | tail -n 1)
if [ -z "$ANDROID_JAR" ] || [ ! -f "$ANDROID_JAR" ]; then
  echo "[ERROR] 在 $SDK_DIR/platforms 下未找到 android.jar。"
  exit 1
fi

# 查找最新的 d8 编译工具
D8_BIN=$(find "$SDK_DIR/build-tools" -name "d8" 2>/dev/null | sort -V | tail -n 1)
if [ -z "$D8_BIN" ] || [ ! -x "$D8_BIN" ]; then
  echo "[ERROR] 在 $SDK_DIR/build-tools 下未找到 d8 可执行文件。"
  exit 1
fi

# 检查 javac 编译器
if ! command -v javac >/dev/null 2>&1; then
  echo "[ERROR] 环境变量 PATH 中未找到 javac。"
  exit 1
fi

echo "=== PhoneTransfer ClipTool 构建流程 ==="
echo "  Android SDK:  $SDK_DIR"
echo "  android.jar:  $ANDROID_JAR"
echo "  d8 工具:      $D8_BIN"
echo "  javac 编译器: $(command -v javac)"

BUILD_DIR="$DIR/build"
SRC_DIR="$DIR/src"
CLASSES_DIR="$BUILD_DIR/classes"
OUTPUT_JAR="$PROJECT_ROOT/phonetransfer/assets/pt_clip.jar"

rm -rf "$BUILD_DIR"
mkdir -p "$CLASSES_DIR"
mkdir -p "$(dirname "$OUTPUT_JAR")"

# 2. 编译 Java 源码为 class 文件
echo "--> 正在编译 Java 源码..."
javac -cp "$ANDROID_JAR" \
  -source 1.8 -target 1.8 \
  "$SRC_DIR/com/phonetransfer/clip/ClipTool.java" \
  -d "$CLASSES_DIR"

# 3. 使用 d8 生成包含 classes.dex 的目标 JAR
echo "--> 正在通过 d8 转换为 Dalvik/ART Dex 字节码..."
"$D8_BIN" "$CLASSES_DIR/com/phonetransfer/clip/ClipTool.class" \
  --output "$BUILD_DIR/pt_clip.jar"

# 4. 同步至工程 assets 目录
cp "$BUILD_DIR/pt_clip.jar" "$OUTPUT_JAR"

echo "=== 构建成功！==="
ls -lh "$OUTPUT_JAR"
