# PhoneTransfer 📱 ⇄ 💻

<p align="center">
  <b>针对 macOS 精心打造的 Android 极速传输与协同中枢（零手机端 App 侵入）</b>
</p>

<p align="center">
  <a href="https://github.com/qfxydx/PhoneTransfer/releases/latest"><img src="https://img.shields.io/github/v/release/qfxydx/PhoneTransfer?style=flat-square&color=blue&label=Download%20DMG" alt="Latest Release" /></a>
  <img src="https://img.shields.io/badge/Platform-macOS-black?style=flat-square&logo=apple" alt="Platform" />
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python" alt="Python" />
  <img src="https://img.shields.io/badge/GUI-PySide6%20%2F%20Qt-green?style=flat-square&logo=qt" alt="GUI" />
  <img src="https://img.shields.io/badge/License-MIT-orange?style=flat-square" alt="License" />
</p>

---

## 💡 为什么需要 PhoneTransfer？

在 macOS 上连接 Android 手机一直是个令人头疼的痛点：
- 官方 **Android File Transfer (AFT)** 已被 Google 废弃，传输稍大文件经常卡死闪退。
- 基于 Electron 的开源工具（如 OpenMTP）内存占用动辄几百兆，且脆弱的 MTP 协议不支持并发。
- 大量互传工具要求在手机上常驻安装一个后台 APK，不仅费电，还极易被国内手机系统杀后台。

**PhoneTransfer 彻底改变了这一切**：
基于原生 **ADB 管道与底层反射技术**，做到 **手机端 0 App 安装、0 常驻后台**，插线即连、拔线即走！同时深度融入 macOS 人机交互精髓，为你带来真正顺滑的跨端协同体验。

---

## 🌟 核心亮点特性

### 1. ⚡ 原生双向高速传输
- **带宽跑满**：USB 有线直连稳定 40+ MB/s，大体积 4K 视频、无损音频秒级传输。
- **智能防冲突策略**：支持「跳过已存在」、「直接覆盖」、「重命名备份」三种灵活冲突解决机制。
- **空间动态侦测**：自动获取手机实际可用存储，带轻量防闪烁动画，传输前杜绝空间溢出风险。

### 2. 👁️ Mac 级 QuickLook 空格键即时预览
- 无论是电脑本地文件，还是**手机内部存储**中的照片、音视频、PDF 或文档，只要**轻按空格键（Space）**即可直接呼出 macOS 原生 QuickLook 大图/高清视频播放预览！

### 3. 📋 跨端系统剪贴板秒传 (`⌘⇧V`)
- 攻克 Android 10～16 严格的后台剪贴板安全沙箱。
- 在 Mac 上按下 `⌘⇧V`，输入或粘贴任意内容，按 `⌘↵` 即可在 **30ms 内直推至手机系统剪贴板**。
- 手机端无需打开任何应用，长按输入框或在输入法（Gboard、微信键盘、搜狗等）浮条上**直接点击粘贴**！

### 4. 🖥️ 一键手机投屏与反向协同 (`⌘⇧M`)
- 顶栏一键直连 `scrcpy` 超低延迟投屏，自动共享当前 ADB 实例环境，杜绝版本冲突服务重置。
- 在 Mac 屏幕上直接通过鼠标拖拽点击、Mac 键盘直接打字反向操作手机，传完文件秒开验证。

### 5. ≋ 业界首创「插线转无线」免配对
- **插线转无线**：插上数据线点击一次，系统自动配置并建立 Wi-Fi 调试通道，随后**拔掉数据线即可随时无线漫游传输**！
- 亦全面支持 Android 11+ 六位配对码无线连接与手动 IP 直连。

### 6. 📂 智能分类筛选与 APK 极速安装
- 一键分类切换：照片、视频、音乐、文档、APK 安装包、压缩包。
- 拖拽任意 `.apk` 文件至手机端，自动携带 `-r -d` 参数实现免确认覆盖与降级安装。

---

## ⌨️ 快捷键指南

| 快捷键 | 功能描述 |
| :--- | :--- |
| **`Space` (空格键)** | 快速呼出/关闭 QuickLook 原生大图与音视频预览 |
| **`⌘⇧V` (`Ctrl+Shift+V`)** | 呼出跨端剪贴板速传对话框 |
| **`⌘⇧M` (`Ctrl+Shift+M`)** | 一键启动手机屏幕镜像与协同控制 (scrcpy) |
| **`⌘↵` (`Cmd+Return`)** | 跨端速传弹窗内一键直接发送到手机剪贴板 |
| **`Esc`** | 清空文件筛选过滤词 / 返回上级目录 |

---

## 🚀 快速上手与运行

### 方式一：直接下载安装包（推荐普通用户）

1. 前往 [Releases 发布页面](https://github.com/qfxydx/PhoneTransfer/releases/latest) 下载最新的 **`PhoneTransfer-v1.0.0-macOS.dmg`**；
2. 双击打开镜像，将 **`PhoneTransfer.app`** 拖入 **`Applications`** 应用程序文件夹；
3. 打开即可使用！（若首次打开提示“无法打开未受信任的开发者”，请在 macOS「系统设置 -> 隐私与安全性」中轻按「仍要打开」即可）。

---

### 方式二：开发者源码运行

#### 依赖环境
- **macOS**：macOS 11 (Big Sur) 及更高版本
- **Python**：Python 3.10+
- **ADB**：系统已安装 `adb`（若安装了 Android SDK 或通过 `brew install android-platform-tools`）

#### 命令行启动

```bash
# 1. 克隆本项目仓库
git clone https://github.com/qfxydx/PhoneTransfer.git
cd PhoneTransfer

# 2. 安装 Python 依赖
pip3 install -r requirements.txt

# 3. 启动应用
python3 phone_transfer.py
```

*或者直接双击根目录下的 `启动PhoneTransfer.command` 脚本。*

---

## 🛠️ 底层组件与源码构建

PhoneTransfer 秉承 100% 纯粹透明的开源精神，所有核心二进制与助手组件源码均完整开源并包含在代码库中：

- **Android 剪贴板反射组件 (ClipTool)**：
  - 源码目录：[`tools/cliptool/src/`](tools/cliptool/src/)
  - 构建脚本：[`tools/cliptool/build.sh`](tools/cliptool/build.sh)（支持调用 javac 与 Android SDK d8 重新编译生成 `pt_clip.jar`）
  - 架构解析文档：[`tools/cliptool/README.md`](tools/cliptool/README.md)
- **Mac 原生文件多选器 (pick_items)**：
  - 源码文件：[`pick_items.swift`](pick_items.swift)

---

## ☕ 请作者喝杯咖啡 (Buy Me a Coffee)

PhoneTransfer 是一款由个人在业余时间独立精心打磨的开源项目。如果它在日常工作中为你省下了宝贵的时间或带来了愉悦的体验，欢迎：
- 在应用左上角点击 **`☕`** 请作者喝杯咖啡 🥐
- 在 GitHub 右上角给本项目点一个 **Star ⭐**（这是莫大的精神支持！）

---

## 📄 开源许可证

本项目基于 [MIT License](LICENSE) 开源协议发布，欢迎 Fork、提交 PR 或 Issue。
