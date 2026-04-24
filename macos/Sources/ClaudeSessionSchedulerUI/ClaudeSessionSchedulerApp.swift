import CSSShared
import SwiftUI

@main
struct ClaudeSessionSchedulerApp: App {
    @StateObject private var controller = AppController()

    var body: some Scene {
        MenuBarExtra("Claude Scheduler", systemImage: "clock.badge.checkmark") {
            MenuBarContent(controller: controller)
                .frame(width: 360)
        }
        .menuBarExtraStyle(.window)

        Window("Claude Scheduler", id: "scheduler") {
            SchedulerWindow(controller: controller)
                .frame(minWidth: 780, minHeight: 560)
                .task {
                    await controller.refresh()
                }
        }
        .defaultSize(width: 840, height: 620)
    }
}
