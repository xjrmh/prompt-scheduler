import PromptSchedulerShared
import SwiftUI
import AppKit

struct MenuBarContent: View {
    @ObservedObject var controller: AppController

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            ForEach(Array(controller.providerSummaries.enumerated()), id: \.element.id) { index, summary in
                if index > 0 {
                    popoverHairline
                }
                PopoverProviderSection(summary: summary)
            }

            popoverSectionSeparator

            VStack(alignment: .leading, spacing: 2) {
                PopoverSectionHeader("Send With")
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
                .frame(maxWidth: .infinity)
                .padding(.horizontal, 12)
            }
            .padding(.bottom, 4)

            if let statusDetailLine {
                popoverInlineMessage(statusDetailLine)
            }

            if let responseLine {
                popoverInlineMessage(responseLine)
            }

            PopoverSecondaryRow(title: "Send Prompt Now", systemImage: "paperplane.fill") {
                Task { await controller.startNow() }
            }
            .disabled(controller.isLoading || !controller.isReady)

            VStack(alignment: .leading, spacing: 2) {
                PopoverSectionHeader("Send Wake-Up Prompt Every")
                Picker("Wake Up Every", selection: Binding(
                    get: { controller.currentWakeLoopInterval },
                    set: { newValue in
                        Task { await controller.setWakeLoopInterval(newValue) }
                    }
                )) {
                    Text("Off").tag(WakeLoopInterval.off)
                    Text("30 min").tag(WakeLoopInterval.every30Min)
                    Text("1 h").tag(WakeLoopInterval.everyHour)
                    Text("2 h").tag(WakeLoopInterval.every2Hours)
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .frame(maxWidth: .infinity)
                .padding(.horizontal, 12)
                .disabled(controller.isLoading || !controller.isReady)
            }
            .padding(.bottom, 4)

            popoverSectionSeparator

            PopoverSecondaryRow(
                title: "More Options...",
                systemImage: "slider.horizontal.3",
                showsChevron: true
            ) {
                MoreOptionsHost.shared.show(controller: controller)
            }
            .disabled(controller.isLoading)

            PopoverSecondaryRow(title: "Refresh", systemImage: "arrow.clockwise") {
                Task { await controller.refresh() }
            }
            .disabled(controller.isLoading)

            if hasConditionalRows {
                popoverSectionSeparator

                if let installProviderLabel = controller.installProviderLabel,
                   controller.status != nil {
                    PopoverSecondaryRow(
                        title: "Install \(installProviderLabel)",
                        systemImage: "square.and.arrow.down"
                    ) {
                        Task { await controller.installActiveProvider() }
                    }
                    .disabled(controller.isLoading)
                }

                if controller.shouldShowLoginCommand {
                    PopoverSecondaryRow(title: "Copy Login Command", systemImage: "doc.on.doc") {
                        copyLoginCommand()
                    }
                }

                if let logPath = lastLogPath {
                    PopoverSecondaryRow(title: "Reveal Last Log", systemImage: "doc.text.magnifyingglass") {
                        revealLog(logPath)
                    }
                }
            }

            if !controller.scheduledJobs.isEmpty {
                popoverSectionSeparator

                PopoverSectionHeader("Scheduled")

                VStack(spacing: 0) {
                    ForEach(controller.scheduledJobs) { job in
                        ScheduledJobRow(job: job, controller: controller)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 4)
                    }
                }
            }

            popoverSectionSeparator

            PopoverSecondaryRow(title: "Quit", systemImage: "power", iconTint: .red) {
                NSApplication.shared.terminate(nil)
            }
            .keyboardShortcut("q", modifiers: .command)
        }
        .padding(.vertical, 6)
        .frame(width: 320, alignment: .leading)
        .task {
            await controller.refresh()
        }
    }

    private var hasConditionalRows: Bool {
        (controller.installProviderLabel != nil && controller.status != nil)
            || controller.shouldShowLoginCommand
            || lastLogPath != nil
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

    private func popoverInlineMessage(_ text: String) -> some View {
        Text(text)
            .font(.callout)
            .foregroundStyle(.secondary)
            .lineLimit(2)
            .padding(.horizontal, 12)
            .padding(.vertical, 2)
    }

    private var popoverHairline: some View {
        Rectangle()
            .fill(Color.primary.opacity(0.08))
            .frame(height: 1)
            .padding(.horizontal, 12)
    }

    private var popoverSectionSeparator: some View {
        Rectangle()
            .fill(Color.primary.opacity(0.08))
            .frame(height: 1)
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
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

private struct PopoverSectionHeader: View {
    let title: String

    init(_ title: String) {
        self.title = title
    }

    var body: some View {
        Text(title)
            .font(.caption2.weight(.semibold))
            .foregroundStyle(.secondary)
            .textCase(.uppercase)
            .kerning(0.5)
            .padding(.horizontal, 12)
            .padding(.top, 4)
            .padding(.bottom, 2)
            .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct PopoverSecondaryRow: View {
    let title: String
    let systemImage: String
    var iconTint: Color? = nil
    var showsChevron: Bool = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 10) {
                Image(systemName: systemImage)
                    .symbolRenderingMode(.hierarchical)
                    .foregroundStyle(iconTint ?? Color.secondary)
                    .frame(width: 16, alignment: .center)
                Text(title)
                    .foregroundStyle(.primary)
                Spacer(minLength: 4)
                if showsChevron {
                    Image(systemName: "chevron.right")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.tertiary)
                }
            }
            .padding(.horizontal, 6)
            .padding(.vertical, 6)
            .contentShape(Rectangle())
        }
        .buttonStyle(PopoverRowButtonStyle())
    }
}

private struct PopoverRowButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        PopoverRowButton(configuration: configuration)
    }

    private struct PopoverRowButton: View {
        let configuration: ButtonStyle.Configuration
        @Environment(\.isEnabled) private var isEnabled
        @Environment(\.colorScheme) private var colorScheme
        @State private var isHovering = false

        var body: some View {
            configuration.label
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(
                    RoundedRectangle(cornerRadius: 6, style: .continuous)
                        .fill(fill)
                )
                .opacity(isEnabled ? 1.0 : 0.45)
                .padding(.horizontal, 6)
                .onHover { hovering in
                    guard isEnabled else { return }
                    isHovering = hovering
                }
        }

        private var fill: Color {
            guard isEnabled, isHovering else { return .clear }
            let base: Double = colorScheme == .dark ? 0.10 : 0.07
            let opacity = configuration.isPressed ? base + 0.05 : base
            return Color.primary.opacity(opacity)
        }
    }
}

private struct PopoverProviderSection: View {
    var summary: ProviderRunSummary

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(summary.title)
                .font(.headline)

            Grid(alignment: .leadingFirstTextBaseline, horizontalSpacing: 12, verticalSpacing: 4) {
                row("Status", summary.status)
                row("Next Usage Reset", summary.nextUsageStart)
                row("Last Sent Time", summary.lastSentTime)
                row("Last Sent Status", summary.lastSentStatus)
            }
            .font(.callout)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
    }

    private func row(_ label: String, _ value: String) -> GridRow<some View> {
        GridRow {
            Text(label)
            Text(value)
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .truncationMode(.middle)
                .monospacedDigit()
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

@MainActor
private final class MoreOptionsHost {
    static let shared = MoreOptionsHost()

    private var window: NSWindow?

    func show(controller: AppController) {
        if let window, window.isVisible {
            window.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return
        }

        let rootView = MoreOptionsView(controller: controller) { [weak self] in
            self?.close()
        }
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 520, height: 600),
            styleMask: [.titled, .closable, .miniaturizable],
            backing: .buffered,
            defer: false
        )
        window.title = "More Options"
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

private struct MoreOptionsView: View {
    @ObservedObject var controller: AppController
    var onClose: () -> Void

    @State private var wakePrompt: String
    @State private var wakeFeedback: String?
    @State private var isSavingWake = false

    @State private var name = "Scheduled message"
    @State private var prompt = ""
    @State private var cwd = SchedulerDefaults.projectFolderPath
    @State private var kind = SimpleScheduleKind.daily
    @State private var weekday = SimpleScheduleWeekday.mon
    @State private var time = MoreOptionsView.defaultTime()
    @State private var claudeModel: String
    @State private var codexModel: String
    @State private var feedbackText: String?
    @State private var feedbackIsError = false
    @State private var isSaving = false

    init(controller: AppController, onClose: @escaping () -> Void) {
        self.controller = controller
        self.onClose = onClose
        _wakePrompt = State(initialValue: controller.wakeLoopPrompt)
        _claudeModel = State(initialValue: controller.claudeModelDefault)
        _codexModel = State(initialValue: controller.codexModelDefault)
    }

    private static let claudeModelSuggestions: [(label: String, value: String)] = [
        ("Default", ""),
        ("Opus", "opus"),
        ("Sonnet", "sonnet"),
        ("Haiku", "haiku"),
    ]

    private static let codexModelSuggestions: [(label: String, value: String)] = [
        ("gpt-5.4-mini (cheapest)", "gpt-5.4-mini"),
        ("gpt-5.3-codex", "gpt-5.3-codex"),
        ("gpt-5.4", "gpt-5.4"),
        ("gpt-5.5", "gpt-5.5"),
    ]

    private var showClaudeModel: Bool {
        controller.sendProviderSelection == "claude" || controller.sendProviderSelection == "both"
    }

    private var showCodexModel: Bool {
        controller.sendProviderSelection == "codex" || controller.sendProviderSelection == "both"
    }

    var body: some View {
        VStack(spacing: 0) {
            Form {
                Section {
                    TextField("Wake prompt", text: $wakePrompt, axis: .vertical)
                        .lineLimit(3...6)
                        .labelsHidden()

                    HStack(spacing: 8) {
                        if let wakeFeedback {
                            Text(wakeFeedback)
                                .font(.callout)
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                        }
                        Spacer()
                        Button("Save Wake Prompt") {
                            saveWakePrompt()
                        }
                        .disabled(isSavingWake || wakePrompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    }
                } header: {
                    Text("Wake-up Prompt")
                } footer: {
                    Text("Sent on every wake-up tick. Saving while a loop is running re-installs it with the new prompt.")
                }

                Section("Schedule a Message") {
                    TextField("Name", text: $name, prompt: Text("Required"))

                    TextField("Message", text: $prompt, prompt: Text("Required"), axis: .vertical)
                        .lineLimit(3...8)

                    Picker("Repeats", selection: $kind) {
                        ForEach(SimpleScheduleKind.allCases) { option in
                            Text(option.label).tag(option)
                        }
                    }
                    .pickerStyle(.segmented)

                    DatePicker("Time", selection: $time, displayedComponents: .hourAndMinute)

                    if kind == .weekly {
                        Picker("Day", selection: $weekday) {
                            ForEach(SimpleScheduleWeekday.allCases) { option in
                                Text(option.label).tag(option)
                            }
                        }
                    }

                    LabeledContent("Project Folder") {
                        HStack(spacing: 6) {
                            TextField("", text: $cwd)
                                .labelsHidden()
                                .truncationMode(.middle)
                            Button {
                                chooseFolder()
                            } label: {
                                Image(systemName: "folder")
                            }
                            .buttonStyle(.borderless)
                            .help("Choose project folder")
                        }
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

                    if showClaudeModel {
                        modelField(
                            label: "Claude model",
                            text: $claudeModel,
                            placeholder: "Default",
                            suggestions: Self.claudeModelSuggestions,
                            onChange: { controller.setClaudeModelDefault($0) }
                        )
                    }

                    if showCodexModel {
                        modelField(
                            label: "Codex model",
                            text: $codexModel,
                            placeholder: AppController.defaultCodexModel,
                            suggestions: Self.codexModelSuggestions,
                            onChange: { controller.setCodexModelDefault($0) }
                        )
                    }
                }

                if let feedbackText {
                    Section {
                        Text(feedbackText)
                            .font(.callout)
                            .foregroundStyle(feedbackIsError ? .red : .secondary)
                    }
                }
            }
            .formStyle(.grouped)

            Divider()

            HStack {
                Button {
                    copyCLICommand()
                } label: {
                    Label("Copy CLI Command", systemImage: "terminal")
                }
                .buttonStyle(.bordered)

                Spacer()

                Button("Cancel") {
                    onClose()
                }
                .keyboardShortcut(.cancelAction)

                Button("Schedule") {
                    save()
                }
                .buttonStyle(.borderedProminent)
                .keyboardShortcut(.defaultAction)
                .disabled(!canSave)
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
        }
        .frame(width: 520, height: 600)
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
            weekday: weekday,
            claudeModel: showClaudeModel ? claudeModel : "",
            codexModel: showCodexModel ? codexModel : ""
        )
    }

    @ViewBuilder
    private func modelField(
        label: String,
        text: Binding<String>,
        placeholder: String,
        suggestions: [(label: String, value: String)],
        onChange: @escaping (String) -> Void
    ) -> some View {
        LabeledContent(label) {
            HStack(spacing: 6) {
                TextField(placeholder, text: text, prompt: Text(placeholder))
                    .labelsHidden()
                    .truncationMode(.tail)
                    .onChange(of: text.wrappedValue) { _, newValue in
                        onChange(newValue)
                    }
                Menu {
                    ForEach(suggestions, id: \.value) { option in
                        Button(option.label) {
                            text.wrappedValue = option.value
                            onChange(option.value)
                        }
                    }
                } label: {
                    Image(systemName: "chevron.down")
                }
                .menuStyle(.borderlessButton)
                .fixedSize()
                .help("Choose a preset")
            }
        }
    }

    private func saveWakePrompt() {
        isSavingWake = true
        wakeFeedback = nil
        Task { @MainActor in
            await controller.setWakeLoopPrompt(wakePrompt)
            wakePrompt = controller.wakeLoopPrompt
            isSavingWake = false
            wakeFeedback = "Saved."
        }
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
        if let claudeModel = currentDraft.claudeModelOrNil {
            args.append(contentsOf: ["--claude-model", claudeModel])
        }
        if let codexModel = currentDraft.codexModelOrNil {
            args.append(contentsOf: ["--codex-model", codexModel])
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

    @State private var isDeleteHovering = false

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            VStack(alignment: .leading, spacing: 1) {
                Text(displayTitle)
                    .font(.callout)
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
                    .foregroundStyle(isDeleteHovering ? .secondary : .tertiary)
            }
            .buttonStyle(.borderless)
            .help("Cancel")
            .onHover { isDeleteHovering = $0 }
        }
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

private func cleanDisplayText(_ value: String?) -> String? {
    guard let value = value?.trimmingCharacters(in: .whitespacesAndNewlines), !value.isEmpty else {
        return nil
    }
    return value
}
