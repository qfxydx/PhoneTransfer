import AppKit
import Foundation

let app = NSApplication.shared
app.setActivationPolicy(.accessory)
app.activate(ignoringOtherApps: true)

let title = CommandLine.arguments.count > 1
    ? CommandLine.arguments[1]
    : "选择要传输的内容"

let panel = NSOpenPanel()
panel.title = title
panel.canChooseFiles = true
panel.canChooseDirectories = true
panel.allowsMultipleSelection = true
panel.canCreateDirectories = false
panel.level = .modalPanel

guard panel.runModal() == .OK else {
    exit(0)
}

for url in panel.urls {
    print(url.path)
}
