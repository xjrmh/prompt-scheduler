import PromptSchedulerShared
import SwiftUI
import AppKit

struct MenuBarContent: View {
    @ObservedObject var controller: AppController

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            VStack(alignment: .leading, spacing: 10) {
                ForEach(Array(controller.providerSummaries.enumerated()), id: \.element.id) { index, summary in
                    if index > 0 {
                        Divider()
                    }
                    ProviderSummarySection(summary: summary)
                }
            }

            Divider()

            VStack(alignment: .leading, spacing: 5) {
                Text("Send With")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                Picker("Send With", selection: Binding(
                    get: { controller.sendProviderSelection },
                    set: { controller.setSendProviderSelection($0) }
                )) {
                    Text("Codex").tag("codex")
                    Text("Claude Code").tag("claude")
                    Text("Both").tag("both")
                }
                .pickerStyle(.segmented)
                .labelsHidden()
            }

            if let statusDetailLine {
                Text(statusDetailLine)
                    .font(.caption)
                    .foregroundStyle(.secondary)
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

            VStack(alignment: .leading, spacing: 5) {
                Text("Send Wake Up Prompt Every")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                Picker("Wake Up Every", selection: Binding(
                    get: { controller.currentWakeLoopInterval },
                    set: { newValue in
                        Task { await controller.setWakeLoopInterval(newValue) }
                    }
                )) {
                    ForEach(WakeLoopInterval.allCases) { option in
                        Text(option.label).tag(option)
                    }
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .disabled(controller.isLoading || !controller.isReady)

                Button {
                    WakePromptHost.shared.show(controller: controller)
                } label: {
                    Label("Edit Wake Prompt...", systemImage: "pencil")
                }
                .disabled(controller.isLoading)
            }

            Button {
                ScheduleWindowHost.shared.show(controller: controller)
            } label: {
                Label("Schedule Message...", systemImage: "calendar.badge.plus")
            }
            .disabled(controller.isLoading)

            Button {
                Task { await controller.refresh() }
            } label: {
                Label("Refresh", systemImage: "arrow.clockwise")
            }
            .disabled(controller.isLoading)

            if let installProviderLabel = controller.installProviderLabel, controller.status != nil {
                Divider()

                Button {
                    Task { await controller.installActiveProvider() }
                } label: {
                    Label("Install \(installProviderLabel)", systemImage: "square.and.arrow.down")
                }
                .disabled(controller.isLoading)
            }

            if controller.shouldShowLoginCommand {
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

            if !controller.scheduledJobs.isEmpty {
                Divider()

                Text("Scheduled")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                VStack(alignment: .leading, spacing: 4) {
                    ForEach(controller.scheduledJobs) { job in
                        ScheduledJobRow(job: job, controller: controller)
                    }
                }
            }

            Divider()

            Button {
                NSApplication.shared.terminate(nil)
            } label: {
                Label("Quit", systemImage: "power")
            }
        }
        .padding(14)
        .frame(width: 300, alignment: .leading)
        .buttonStyle(MenuRowButtonStyle())
        .task {
            await controller.refresh()
        }
    }

    private var statusDetailLine: String? {
        guard let detail = cleanDisplayText(controller.lastManualSend?.detail) else {
            return nil
        }
        return singleLine(detail)
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

    private func copyLoginCommand() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(controller.loginCommand, forType: .string)
    }

    private func revealLog(_ path: String) {
        NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: path)])
    }
}

private struct ProviderSummarySection: View {
    var summary: ProviderRunSummary

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(summary.title)
                .font(.headline)

            row("Status", summary.status)
            row("Next Usage Reset", summary.nextUsageStart)
            row("Last Sent Time", summary.lastSentTime)
            row("Last Sent Status", summary.lastSentStatus)
        }
    }

    private func row(_ label: String, _ value: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
                .frame(width: 104, alignment: .leading)

            Text(value)
                .font(.caption)
                .lineLimit(1)
                .truncationMode(.middle)
        }
    }
}

@MainActor
private final class ScheduleWindowHost {
    static let shared = ScheduleWindowHost()

    private var window: NSWindow?

    func show(controller: AppController) {
        if let window, window.isVisible {
            window.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return
        }

        let rootView = SchedulePromptView(controller: controller) { [weak self] in
            self?.close()
        }
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 440, height: 430),
            styleMask: [.titled, .closable],
            backing: .buffered,
            defer: false
        )
        window.title = "Schedule Message"
        window.isReleasedWhenClosed = false
        window.contentView = NSHostingView(rootView: rootView)
        window.center()
        self.window = window
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    private func close() {
        window?.close()
        window = nil
    }
}

@MainActor
private final class WakePromptHost {
    static let shared = WakePromptHost()

    private var window: NSWindow?

    func show(controller: AppController) {
        if let window, window.isVisible {
            window.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return
        }

        let rootView = WakePromptEditView(controller: controller) { [weak self] in
            self?.close()
        }
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 380, height: 240),
            styleMask: [.titled, .closable],
            backing: .buffered,
            defer: false
        )
        window.title = "Edit Wake Prompt"
        window.isReleasedWhenClosed = false
        window.contentView = NSHostingView(rootView: rootView)
        window.center()
        self.window = window
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    private func close() {
        window?.close()
        window = nil
    }
}

private struct WakePromptEditView: View {
    @ObservedObject var controller: AppController
    var onClose: () -> Void

    @State private var prompt: String
    @State private var isSaving = false

    init(controller: AppController, onClose: @escaping () -> Void) {
        self.controller = controller
        self.onClose = onClose
        _prompt = State(initialValue: controller.wakeLoopPrompt)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Edit Wake Prompt")
                    .font(.headline)
                Spacer()
                Button {
                    onClose()
                } label: {
                    Image(systemName: "xmark")
                }
                .buttonStyle(.borderless)
            }

            Text("Sent on every wake-up tick. Saving while a loop is running re-installs it with the new prompt.")
                .font(.caption)
                .foregroundStyle(.secondary)

            TextEditor(text: $prompt)
                .frame(minHeight: 84)
                .overlay(
                    RoundedRectangle(cornerRadius: 6)
                        .stroke(Color.secondary.opacity(0.35))
                )

            HStack {
                Spacer()
                Button("Cancel") {
                    onClose()
                }
                Button("Save") {
                    save()
                }
                .keyboardShortcut(.defaultAction)
                .disabled(isSaving || prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
        }
        .padding(18)
        .frame(width: 380)
    }

    private func save() {
        isSaving = true
        Task { @MainActor in
            await controller.setWakeLoopPrompt(prompt)
            isSaving = false
            onClose()
        }
    }
}

private struct SchedulePromptView: View {
    @ObservedObject var controller: AppController
    var onClose: () -> Void

    @State private var name = "Scheduled message"
    @State private var prompt = ""
    @State private var cwd = SchedulerDefaults.projectFolderPath
    @State private var kind = SimpleScheduleKind.daily
    @State private var weekday = SimpleScheduleWeekday.mon
    @State private var time = SchedulePromptView.defaultTime()
    @State private var feedbackText: String?
    @State private var feedbackIsError = false
    @State private var isSaving = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Schedule Message")
                    .font(.headline)
                Spacer()
                Button {
                    onClose()
                } label: {
                    Image(systemName: "xmark")
                }
                .buttonStyle(.borderless)
            }

            TextField("Name", text: $name)

            VStack(alignment: .leading, spacing: 4) {
                Text("Message")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                TextEditor(text: $prompt)
                    .frame(minHeight: 84)
                    .overlay(
                        RoundedRectangle(cornerRadius: 6)
                            .stroke(Color.secondary.opacity(0.35))
                    )
            }

            Picker("Repeats", selection: $kind) {
                ForEach(SimpleScheduleKind.allCases) { option in
                    Text(option.label).tag(option)
                }
            }
            .pickerStyle(.segmented)

            HStack {
                DatePicker("Time", selection: $time, displayedComponents: .hourAndMinute)
                if kind == .weekly {
                    Picker("Day", selection: $weekday) {
                        ForEach(SimpleScheduleWeekday.allCases) { option in
                            Text(option.label).tag(option)
                        }
                    }
                    .frame(width: 170)
                }
            }

            HStack {
                TextField("Project Folder", text: $cwd)
                Button {
                    chooseFolder()
                } label: {
                    Image(systemName: "folder")
                }
                .help("Choose project folder")
            }

            Picker("Provider", selection: Binding(
                get: { controller.sendProviderSelection },
                set: { controller.setSendProviderSelection($0) }
            )) {
                Text("Codex").tag("codex")
                Text("Claude Code").tag("claude")
                Text("Both").tag("both")
            }
            .pickerStyle(.segmented)

            if let feedbackText {
                Text(feedbackText)
                    .font(.caption)
                    .foregroundStyle(feedbackIsError ? .red : .secondary)
                    .lineLimit(2)
            }

            HStack {
                Button {
                    copyCLICommand()
                } label: {
                    Label("Copy CLI Command", systemImage: "terminal")
                }

                Spacer()

                Button("Cancel") {
                    onClose()
                }

                Button("Schedule") {
                    save()
                }
                .keyboardShortcut(.defaultAction)
                .disabled(!canSave)
            }
        }
        .padding(18)
        .frame(width: 440)
    }

    private var canSave: Bool {
        !isSaving
            && !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !cwd.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private var draft: SimpleScheduleDraft {
        SimpleScheduleDraft(
            name: name,
            cwd: cwd,
            prompt: prompt,
            provider: controller.sendProviderSelection,
            kind: kind,
            time: Self.timeFormatter.string(from: time),
            weekday: weekday
        )
    }

    private func save() {
        isSaving = true
        feedbackText = nil
        Task { @MainActor in
            let result = await controller.createSimpleSchedule(draft)
            isSaving = false
            switch result {
            case .success(let message):
                feedbackText = message
                feedbackIsError = false
                prompt = ""
            case .failure(let message):
                feedbackText = message
                feedbackIsError = true
            }
        }
    }

    private func chooseFolder() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        panel.directoryURL = URL(fileURLWithPath: cwd, isDirectory: true)
        if panel.runModal() == .OK, let url = panel.url {
            cwd = url.path
        }
    }

    private func copyCLICommand() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(cliCommand, forType: .string)
        feedbackText = "Copied CLI command."
        feedbackIsError = false
    }

    private var cliCommand: String {
        let currentDraft = draft
        var args = [
            "prompt-scheduler",
            "add",
            "--provider",
            currentDraft.provider,
            "--name",
            currentDraft.name,
            "--cwd",
            currentDraft.cwd,
        ]
        if let daily = currentDraft.daily {
            args.append(contentsOf: ["--daily", daily])
        } else if let weekly = currentDraft.weekly {
            args.append(contentsOf: ["--weekly", weekly])
        }
        args.append(contentsOf: ["--prompt", currentDraft.prompt])
        return args.map(shellQuote).joined(separator: " ")
    }

    private func shellQuote(_ value: String) -> String {
        if value.range(of: #"^[A-Za-z0-9_./:-]+$"#, options: .regularExpression) != nil {
            return value
        }
        return "'" + value.replacingOccurrences(of: "'", with: "'\\''") + "'"
    }

    private static func defaultTime() -> Date {
        Calendar.current.date(bySettingHour: 9, minute: 0, second: 0, of: Date()) ?? Date()
    }

    private static let timeFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "HH:mm"
        return formatter
    }()
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

private struct ScheduledJobRow: View {
    var job: ScheduleJob
    @ObservedObject var controller: AppController

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            VStack(alignment: .leading, spacing: 1) {
                Text(displayTitle)
                    .font(.system(size: 12))
                    .lineLimit(1)
                    .truncationMode(.tail)
                if let detail = displayDetail {
                    Text(detail)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .truncationMode(.tail)
                }
            }
            Spacer(minLength: 4)
            Button {
                Task { await controller.removeSchedule(job.id) }
            } label: {
                Image(systemName: "xmark.circle.fill")
                    .foregroundStyle(.secondary)
            }
            .buttonStyle(.borderless)
            .help("Cancel")
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 2)
    }

    private var displayTitle: String {
        if job.name == "wake-loop" {
            return "Wake-up loop"
        }
        if job.name == "start-window-at-reset" {
            let label = job.providerLabel ?? job.provider ?? "provider"
            return "Wake \(label) at next reset"
        }
        return job.name ?? job.id
    }

    private var displayDetail: String? {
        guard let label = job.scheduleLabel else { return nil }
        return ScheduledJobRow.friendlyScheduleLabel(label)
    }

    static func friendlyScheduleLabel(_ raw: String) -> String {
        if raw.hasPrefix("once at "),
           let date = parseISODate(String(raw.dropFirst("once at ".count))) {
            return relativeDateTime(date)
        }
        if raw.hasPrefix("daily at "),
           let formatted = formatTimeOfDay(String(raw.dropFirst("daily at ".count))) {
            return "Daily at \(formatted)"
        }
        if raw.hasPrefix("weekly ") {
            let remainder = raw.dropFirst("weekly ".count)
            if let atRange = remainder.range(of: " at ") {
                let days = remainder[..<atRange.lowerBound]
                let timeText = remainder[atRange.upperBound...]
                if let formatted = formatTimeOfDay(String(timeText)) {
                    return "Weekly \(days) at \(formatted)"
                }
            }
        }
        if raw.hasPrefix("every ") {
            let token = String(raw.dropFirst("every ".count))
            switch token {
            case "30m": return "Every 30 min"
            case "1h":  return "Every 1 h"
            case "2h":  return "Every 2 h"
            default:    return "Every \(token)"
            }
        }
        if raw == "manual" {
            return "Manual"
        }
        return raw
    }

    private static let isoFormatter: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()

    private static let isoFractionalFormatter: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    private static let timeOfDayFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "HH:mm"
        return formatter
    }()

    private static let localTimeFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale.current
        formatter.timeZone = TimeZone.current
        formatter.timeStyle = .short
        formatter.dateStyle = .none
        return formatter
    }()

    private static let weekdayFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale.current
        formatter.timeZone = TimeZone.current
        formatter.dateFormat = "EEE"
        return formatter
    }()

    private static let monthDayFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale.current
        formatter.timeZone = TimeZone.current
        formatter.setLocalizedDateFormatFromTemplate("MMMd")
        return formatter
    }()

    private static func parseISODate(_ value: String) -> Date? {
        if let date = isoFormatter.date(from: value) {
            return date
        }
        return isoFractionalFormatter.date(from: value)
    }

    private static func formatTimeOfDay(_ value: String) -> String? {
        guard let parsed = timeOfDayFormatter.date(from: value) else { return nil }
        return localTimeFormatter.string(from: parsed)
    }

    private static func relativeDateTime(_ date: Date) -> String {
        let calendar = Calendar.current
        let timeText = localTimeFormatter.string(from: date)
        if calendar.isDateInToday(date) {
            return "Today at \(timeText)"
        }
        if calendar.isDateInTomorrow(date) {
            return "Tomorrow at \(timeText)"
        }
        let now = Date()
        if let days = calendar.dateComponents([.day], from: calendar.startOfDay(for: now), to: calendar.startOfDay(for: date)).day,
           days > 0 && days < 7 {
            return "\(weekdayFormatter.string(from: date)) at \(timeText)"
        }
        return "\(monthDayFormatter.string(from: date)) at \(timeText)"
    }
}

private struct MenuRowButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        MenuRowButton(configuration: configuration)
    }

    private struct MenuRowButton: View {
        let configuration: ButtonStyle.Configuration
        @Environment(\.isEnabled) private var isEnabled
        @State private var isHovering = false

        var body: some View {
            configuration.label
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 6)
                .padding(.vertical, 4)
                .contentShape(Rectangle())
                .foregroundStyle(isEnabled && isHovering ? Color.white : Color.primary)
                .background(
                    RoundedRectangle(cornerRadius: 5, style: .continuous)
                        .fill(backgroundFill)
                )
                .opacity(isEnabled ? 1.0 : 0.45)
                .onHover { hovering in
                    guard isEnabled else { return }
                    isHovering = hovering
                }
        }

        private var backgroundFill: Color {
            guard isEnabled, isHovering else { return .clear }
            return configuration.isPressed
                ? Color.accentColor.opacity(0.75)
                : Color.accentColor
        }
    }
}

private func cleanDisplayText(_ value: String?) -> String? {
    guard let value = value?.trimmingCharacters(in: .whitespacesAndNewlines), !value.isEmpty else {
        return nil
    }
    return value
}
