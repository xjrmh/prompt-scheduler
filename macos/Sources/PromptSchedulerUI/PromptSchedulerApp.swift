import PromptSchedulerShared
import AppKit
import SwiftUI

@main
struct PromptSchedulerApp: App {
    @StateObject private var controller = AppController()

    var body: some Scene {
        MenuBarExtra {
            MenuBarContent(controller: controller)
        } label: {
            Image(nsImage: MenuBarIcon.image(for: controller.menuBarIconState))
                .accessibilityLabel(controller.menuBarIconAccessibilityLabel)
        }
        .menuBarExtraStyle(.menu)
    }
}
