import CSSShared
import AppKit
import SwiftUI

@main
struct ClaudeSessionSchedulerApp: App {
    @StateObject private var controller = AppController()

    var body: some Scene {
        MenuBarExtra {
            MenuBarContent(controller: controller)
        } label: {
            Image(nsImage: MenuBarIcon.image(for: controller.menuBarIconState))
                .accessibilityLabel(controller.menuBarIconAccessibilityLabel)
        }
        .menuBarExtraStyle(.menu)

        Window("Claude Status", id: "status") {
            StatusWindow(controller: controller)
                .frame(minWidth: 780, minHeight: 560)
                .task {
                    await controller.refresh()
                }
        }
        .defaultSize(width: 840, height: 620)
    }
}
