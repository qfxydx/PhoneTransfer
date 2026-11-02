# PhoneTransfer ClipTool

针对 Android 10+ 后台剪贴板安全沙箱的免 Root、免 APK 注入反射桥接组件。

---

## 💡 背景与技术原理

从 Android 10 开始，Google 出于安全和隐私限制，禁止非前台焦点应用（Background Apps）及通用 Shell 命令访问系统剪贴板（`ClipboardManager`），传统的 `service call clipboard` 或 `cmd clipboard` 会抛出安全异常或无实现。

### ClipTool 核心实现机制：
1. **进程环境**：通过 ADB `app_process` 启动独立的轻量级 Java 运行时，直接运行在 Android `shell` (UID 2000) 权限下。
2. **上下文反射构造**：
   - 提取 `ActivityThread.systemMain()` 获取系统主线程；
   - 通过反射调用 `LoadedApk.makeApplication` 构造以 `com.android.shell` 为包名的应用上下文（`appContext`）；
   - 使得系统的 `ClipboardService` 权限检查（AppOps）认为调用方为受信任的系统 Shell 包名，从而安全放行写入。
3. **Stdin 流式写入**：
   - 支持通过标准输入（`-` 参数）以 UTF-8 管道读取长文本；
   - 彻底免除 Linux/Android Shell 命令行参数长度限制（`ARG_MAX`）和单双引号、美元符、反引号等特殊字符转义难题；
   - 完整支持 Unicode、中文、多行长文本和各类复杂 Emoji 🚀。

---

## 🛠️ 构建依赖

- **JDK**：Java 8 或更高版本（需包含 `javac`）
- **Android SDK**：
  - `platforms/android-*/android.jar`
  - `build-tools/*/d8`

构建脚本会自动查找 `$ANDROID_HOME`、`$ANDROID_SDK_ROOT` 或 `~/Library/Android/sdk`。

---

## 🚀 一键构建指令

在项目根目录下或本目录直接运行：

```bash
# 位于 tools/cliptool/ 目录下
./build.sh
```

构建脚本将自动完成：
1. 编译 `src/com/phonetransfer/clip/ClipTool.java` 为字节码；
2. 调用 Android SDK 的 `d8` 编译器将 `.class` 打包为包含 `classes.dex` 的 `pt_clip.jar`；
3. 自动同步更新至 `phonetransfer/assets/pt_clip.jar`。

---

## 📱 运行协议与命令行调用

通过 ADB 推送至手机临时目录 `/data/local/tmp/pt_clip.jar`：

```bash
# 推送组件至手机
adb push phonetransfer/assets/pt_clip.jar /data/local/tmp/pt_clip.jar

# 1. 读取手机剪贴板内容
adb shell "CLASSPATH=/data/local/tmp/pt_clip.jar app_process /system/bin com.phonetransfer.clip.ClipTool"

# 2. 从标准输入流（stdin）写入手机剪贴板（推荐，支持任意字符与超长文本）
echo "Hello PhoneTransfer 🚀" | adb shell "CLASSPATH=/data/local/tmp/pt_clip.jar app_process /system/bin com.phonetransfer.clip.ClipTool -"

# 3. 直接通过参数写入剪贴板
adb shell "CLASSPATH=/data/local/tmp/pt_clip.jar app_process /system/bin com.phonetransfer.clip.ClipTool '测试文本'"
```

---

## 兼容性测试记录

- **Android 10 (Q / API 29)**：支持
- **Android 11 (R / API 30)**：支持
- **Android 12 / 12L (S / API 31, 32)**：支持
- **Android 13 (Tiramisu / API 33)**：支持
- **Android 14 (UpsideDownCake / API 34)**：支持
- **Android 15 (VanillaIceCream / API 35)**：支持
- **Android 16 (Baklava / API 36)**：已在真机全量回归测试通过
