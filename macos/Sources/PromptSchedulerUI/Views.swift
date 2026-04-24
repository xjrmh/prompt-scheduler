import PromptSchedulerShared
import SwiftUI
import AppKit

struct MenuBarContent: View {
    @ObservedObject var controller: AppController

    var body: some View {
        Group {
            Text(readinessLine)

            ForEach(controller.providerStatusLines, id: \.self) { line in
                Text(line)
            }

            if let lastRunLine {
                Text(lastRunLine)
            }

            if let responseLine {
                Text(responseLine)
            }

            Divider()

            Button {
                Task { await controller.startNow() }
            } label: {
                Label("Send Prompt Now", systemImage: "paperplane.fill")
            }
            .disabled(controller.isLoading || !controller.isReady)

            Button {
                Task { await controller.refresh() }
            } label: {
                Label("Refresh", systemImage: "arrow.clockwise")
            }
            .disabled(controller.isLoading)

            if controller.activeProviderStatus?.available != true, controller.status != nil {
                Divider()

                Button {
                    Task { await controller.installActiveProvider() }
                } label: {
                    Label("Install \(controller.activeProviderLabel)", systemImage: "square.and.arrow.down")
                }
                .disabled(controller.isLoading)
            }

            if controller.activeProviderStatus?.available == true,
               controller.activeProviderStatus?.authenticated == false {
                Button {
                    copyLoginCommand()
                } label: {
                    Label("Copy Login Command", systemImage: "doc.on.doc")
                }
            }

            if let logPath = lastLogPath {
                Button {
                    revealLog(logPath)
                } label: {
                    Label("Reveal Last Log", systemImage: "doc.text.magnifyingglass")
                }
            }

            Divider()

            Button {
                NSApplication.shared.terminate(nil)
            } label: {
                Label("Quit", systemImage: "power")
            }
        }
        .task {
            await controller.refresh()
        }
    }

    private var readinessLine: String {
        controller.readinessText
    }

    private var lastRunLine: String? {
        if let sendStatus = controller.lastManualSend {
            return "Last Send: \(sendStatus.title)"
        }

        guard let job = latestJob else {
            return nil
        }
        let status = job.lastStatus ?? job.status ?? "Unknown"
        if let lastRunAt = job.lastRunAt {
            return "Last Run: \(status) at \(shortTimestamp(lastRunAt))"
        }
        return "Last Run: \(status)"
    }

    private var responseLine: String? {
        if let response = cleanDisplayText(controller.lastManualSend?.responseText) {
            return "Response: \(singleLine(response))"
        }

        if let response = cleanDisplayText(latestJob?.lastResponseSummary ?? latestJob?.lastClaudeResponseSummary) {
            return "Response: \(singleLine(response))"
        }
        return nil
    }

    private var latestJob: ScheduleJob? {
        (controller.status?.jobs ?? [])
            .filter { $0.lastRunAt != nil || $0.lastStatus != nil }
            .sorted { ($0.lastRunAt ?? "") > ($1.lastRunAt ?? "") }
            .first
    }

    private var lastLogPath: String? {
        controller.lastManualSend?.logPath ?? latestJob?.lastLogPath
    }

    private func singleLine(_ text: String) -> String {
        let collapsed = text
            .components(separatedBy: .newlines)
            .filter { !$0.isEmpty }
            .joined(separator: " ")
        if collapsed.count <= 80 {
            return collapsed
        }
        return "\(collapsed.prefix(77))..."
    }

    private func shortTimestamp(_ value: String) -> String {
        let rows = TimestampRows.rows(for: value)
        if rows.count >= 2 {
            return rows[1]
        }
        return value
    }

    private func copyLoginCommand() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(controller.loginCommand, forType: .string)
    }

    private func revealLog(_ path: String) {
        NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: path)])
    }
}

private enum TimestampRows {
    static func rows(for value: String) -> [String] {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let separator = trimmed.firstIndex(of: "T") else {
            return [value]
        }

        let date = String(trimmed[..<separator])
        let rawTime = String(trimmed[trimmed.index(after: separator)...])
        guard !date.isEmpty, !rawTime.isEmpty, date.contains("-") else {
            return [value]
        }

        return [date, displayTime(from: rawTime)]
    }

    private static func displayTime(from rawTime: String) -> String {
        guard let timezoneIndex = timezoneStartIndex(in: rawTime) else {
            return timeWithoutFraction(rawTime)
        }

        let time = timeWithoutFraction(String(rawTime[..<timezoneIndex]))
        let timezone = String(rawTime[timezoneIndex...])
        return timezone == "Z" ? "\(time) UTC" : "\(time) \(timezone)"
    }

    private static func timeWithoutFraction(_ time: String) -> String {
        String(time.split(separator: ".", maxSplits: 1, omittingEmptySubsequences: false).first ?? "")
    }

    private static func timezoneStartIndex(in value: String) -> String.Index? {
        if value.hasSuffix("Z") {
            return value.index(before: value.endIndex)
        }

        return value.firstIndex { character in
            character == "+" || character == "-"
        }
    }
}

private func cleanDisplayText(_ value: String?) -> String? {
    guard let value = value?.trimmingCharacters(in: .whitespacesAndNewlines), !value.isEmpty else {
        return nil
    }
    return value
}
