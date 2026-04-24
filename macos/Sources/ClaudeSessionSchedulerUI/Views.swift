import CSSShared
import SwiftUI
import AppKit

struct MenuBarContent: View {
    @ObservedObject var controller: AppController
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        Group {
            Text(readinessLine)

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
                openWindow(id: "status")
                Task { await controller.refresh() }
            } label: {
                Label("Open Status", systemImage: "list.bullet.rectangle")
            }

            Button {
                Task { await controller.refresh() }
            } label: {
                Label("Refresh", systemImage: "arrow.clockwise")
            }
            .disabled(controller.isLoading)

            if controller.status?.claude.available != true, controller.status != nil {
                Divider()

                Button {
                    Task { await controller.installClaudeCode() }
                } label: {
                    Label("Install Claude Code", systemImage: "square.and.arrow.down")
                }
                .disabled(controller.isLoading)
            }

            if controller.status?.claude.available == true,
               controller.status?.claude.authenticated == false {
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

        if let response = cleanDisplayText(latestJob?.lastClaudeResponseSummary) {
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
        NSPasteboard.general.setString("claude auth login", forType: .string)
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

struct StatusWindow: View {
    @ObservedObject var controller: AppController
    @State private var selectedPane: StatusPane? = .overview

    var body: some View {
        NavigationSplitView {
            StatusSidebar(
                controller: controller,
                selection: $selectedPane
            )
            .navigationSplitViewColumnWidth(min: 210, ideal: 230, max: 280)
        } detail: {
            StatusDetail(
                controller: controller,
                pane: selectedPane ?? .overview
            )
        }
        .navigationSplitViewStyle(.balanced)
        .background(Color(nsColor: .windowBackgroundColor))
        .toolbar {
            ToolbarItemGroup {
                Button {
                    Task { await controller.startNow() }
                } label: {
                    Label("Send Now", systemImage: "paperplane.fill")
                }
                .buttonStyle(.borderedProminent)
                .disabled(controller.isLoading || !controller.isReady)
                .help("Send the default prompt now")

                Button {
                    Task { await controller.refresh() }
                } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
                .disabled(controller.isLoading)
                .help("Refresh Claude status")
            }
        }
    }
}

private enum StatusPane: String, CaseIterable, Identifiable {
    case overview
    case activity

    var id: Self { self }

    var title: String {
        switch self {
        case .overview:
            "General"
        case .activity:
            "Activity"
        }
    }

    var subtitle: String {
        switch self {
        case .overview:
            "Claude Code setup, reset times, and quick actions."
        case .activity:
            "Recent prompt runs and delivery status."
        }
    }

    var systemImage: String {
        switch self {
        case .overview:
            "gearshape"
        case .activity:
            "clock.arrow.circlepath"
        }
    }
}

private struct StatusSidebar: View {
    @ObservedObject var controller: AppController
    @Binding var selection: StatusPane?

    var body: some View {
        VStack(spacing: 0) {
            SidebarHeader(controller: controller)
                .padding(.horizontal, 14)
                .padding(.top, 16)
                .padding(.bottom, 10)

            List(selection: $selection) {
                Section {
                    ForEach(StatusPane.allCases) { pane in
                        Label(pane.title, systemImage: pane.systemImage)
                            .tag(pane)
                    }
                }
            }
            .listStyle(.sidebar)
            .scrollContentBackground(.hidden)

            SidebarStatusSummary(
                claudeCodeText: claudeCodeText,
                claudeCodeTone: claudeCodeTone
            )
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
        }
        .background(.bar)
    }

    private var claudeCodeText: String {
        guard let status = controller.status else {
            return "Checking"
        }
        return status.claude.available == true ? "Ready" : "Needs setup"
    }

    private var claudeCodeTone: StatusTone {
        guard let status = controller.status else {
            return .info
        }
        return status.claude.available == true ? .success : .warning
    }
}

private struct SidebarHeader: View {
    @ObservedObject var controller: AppController

    var body: some View {
        HStack(spacing: 10) {
            AppMark(size: 36)

            VStack(alignment: .leading, spacing: 3) {
                Text("Claude Sessions")
                    .font(.headline.weight(.semibold))
                    .lineLimit(1)
                Text(controller.readinessText)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct SidebarStatusSummary: View {
    var claudeCodeText: String
    var claudeCodeTone: StatusTone

    var body: some View {
        VStack(spacing: 0) {
            Divider()
                .padding(.bottom, 10)

            VStack(spacing: 7) {
                SidebarStatusRow(
                    title: "Claude Code",
                    value: claudeCodeText,
                    tone: claudeCodeTone
                )
            }
        }
    }
}

private struct SidebarStatusRow: View {
    var title: String
    var value: String
    var tone: StatusTone

    var body: some View {
        HStack(spacing: 8) {
            Circle()
                .fill(tone.tint)
                .frame(width: 7, height: 7)
            Text(title)
                .lineLimit(1)
            Spacer(minLength: 6)
            Text(value)
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .minimumScaleFactor(0.75)
        }
        .font(.caption)
    }
}

private struct StatusDetail: View {
    @ObservedObject var controller: AppController
    var pane: StatusPane

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                DetailHeader(
                    title: pane.title,
                    subtitle: pane.subtitle
                ) {
                    headerTrailing
                }

                switch pane {
                case .overview:
                    OverviewPane(controller: controller)
                case .activity:
                    ActivityPane(controller: controller)
                }
            }
            .padding(.horizontal, 34)
            .padding(.vertical, 28)
            .frame(maxWidth: 760, alignment: .topLeading)
            .frame(maxWidth: .infinity, alignment: .top)
        }
        .background(Color(nsColor: .windowBackgroundColor))
    }

    @ViewBuilder
    private var headerTrailing: some View {
        switch pane {
        case .overview:
            StatusPill(text: controller.isReady ? "Ready" : "Needs Setup", tone: headerTone)
        case .activity:
            Button {
                Task { await controller.refresh() }
            } label: {
                Label("Refresh", systemImage: "arrow.clockwise")
            }
            .disabled(controller.isLoading)
        }
    }

    private var headerTone: StatusTone {
        guard controller.status != nil else {
            return .info
        }
        return controller.isReady ? .success : .warning
    }
}

private struct DetailHeader<Trailing: View>: View {
    var title: String
    var subtitle: String
    private var trailing: Trailing

    init(
        title: String,
        subtitle: String,
        @ViewBuilder trailing: () -> Trailing
    ) {
        self.title = title
        self.subtitle = subtitle
        self.trailing = trailing()
    }

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 16) {
            VStack(alignment: .leading, spacing: 5) {
                Text(title)
                    .font(.largeTitle.weight(.semibold))
                Text(subtitle)
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Spacer(minLength: 12)

            trailing
        }
    }
}

private struct OverviewPane: View {
    @ObservedObject var controller: AppController

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            SettingsGroup("Setup") {
                SettingsStatusRow(
                    title: "Claude Code",
                    detail: "Command line tool",
                    value: claudeCodeText,
                    systemImage: "terminal",
                    tone: claudeCodeTone
                )
                SettingsDivider()
                SettingsStatusRow(
                    title: "Claude Login",
                    detail: "Account authentication",
                    value: loginStatusText,
                    systemImage: "person.crop.circle",
                    tone: loginStatusTone
                )
                SettingsDivider()
                SettingsValueRow(
                    title: "Observed Reset",
                    detail: "Detected from Claude output",
                    value: controller.status?.reset.nextResetAt ?? "Unknown",
                    systemImage: "timer",
                    tone: controller.status?.reset.nextResetAt == nil ? .neutral : .info
                )
                SettingsDivider()
                SettingsValueRow(
                    title: "Estimated Reset",
                    detail: "Calculated from recent usage",
                    value: controller.status?.reset.nextEstimatedResetAt ?? "Unknown",
                    systemImage: "clock.arrow.circlepath",
                    tone: controller.status?.reset.nextEstimatedResetAt == nil ? .neutral : .info
                )
            }

            setupMessages

            SettingsGroup("Quick Actions") {
                SettingsActionRow(
                    title: "Send Prompt Now",
                    detail: "Runs Claude in the default project folder.",
                    actionTitle: "Send",
                    systemImage: "paperplane.fill",
                    tone: controller.isReady ? .info : .neutral,
                    isProminent: true,
                    isDisabled: controller.isLoading || !controller.isReady
                ) {
                    Task { await controller.startNow() }
                }
                SettingsDivider()
                SettingsActionRow(
                    title: "Refresh Status",
                    detail: "Updates setup and reset information.",
                    actionTitle: "Refresh",
                    systemImage: "arrow.clockwise",
                    tone: .neutral,
                    isProminent: false,
                    isDisabled: controller.isLoading
                ) {
                    Task { await controller.refresh() }
                }
            }

            SettingsGroup("Default Project") {
                SettingsValueRow(
                    title: "Folder",
                    detail: "Used for manual sends.",
                    value: controller.defaultFolder,
                    systemImage: "folder",
                    tone: .neutral
                )
            }
        }
    }

    @ViewBuilder
    private var setupMessages: some View {
        if controller.status?.claude.available != true, controller.status != nil {
            SettingsGroup {
                SettingsActionRow(
                    title: "Install Claude Code",
                    detail: "Install the Claude CLI before sending prompts.",
                    actionTitle: "Install",
                    systemImage: "square.and.arrow.down",
                    tone: .warning,
                    isProminent: false,
                    isDisabled: controller.isLoading
                ) {
                    Task { await controller.installClaudeCode() }
                }
            }
        }

        if shouldShowLoginPanel {
            LoginRequiredPanel()
        }

        if let sendStatus = controller.lastManualSend {
            ManualSendStatusPanel(status: sendStatus)
        }

        if let message = controller.message, message != controller.lastManualSend?.title {
            InlineMessage(text: message)
        }
    }

    private var claudeCodeText: String {
        guard let status = controller.status else {
            return "Checking"
        }
        return status.claude.available == true ? "Ready" : "Not installed"
    }

    private var claudeCodeTone: StatusTone {
        guard let status = controller.status else {
            return .info
        }
        return status.claude.available == true ? .success : .warning
    }

    private var loginStatusText: String {
        guard let claude = controller.status?.claude else {
            return "Checking"
        }
        if claude.available != true {
            return "Unavailable"
        }
        if claude.authenticated == true {
            return claude.authMethod.map { "Signed in (\($0))" } ?? "Signed in"
        }
        if claude.authenticated == false {
            return "Sign in required"
        }
        return "Unknown"
    }

    private var loginStatusTone: StatusTone {
        guard let claude = controller.status?.claude else {
            return .info
        }
        if claude.available != true {
            return .neutral
        }
        if claude.authenticated == true {
            return .success
        }
        if claude.authenticated == false {
            return .warning
        }
        return .neutral
    }

    private var shouldShowLoginPanel: Bool {
        controller.status?.claude.available == true
            && controller.status?.claude.authenticated == false
            && controller.lastManualSend == nil
    }
}

private struct ActivityPane: View {
    @ObservedObject var controller: AppController

    var body: some View {
        let jobs = Array(
            (controller.status?.jobs ?? [])
                .filter { $0.lastRunAt != nil || $0.lastStatus != nil }
                .sorted { ($0.lastRunAt ?? "") > ($1.lastRunAt ?? "") }
                .prefix(8)
        )

        VStack(alignment: .leading, spacing: 18) {
            if jobs.isEmpty {
                SettingsGroup {
                    SettingsValueRow(
                        title: "No Recent Activity",
                        detail: "Runs will appear here after prompts are sent from the menu bar or CLI.",
                        value: "Idle",
                        systemImage: "clock",
                        tone: .neutral
                    )
                }
            } else {
                SettingsGroup {
                    ForEach(Array(jobs.enumerated()), id: \.element.id) { index, job in
                        ActivitySettingsRow(job: job)
                        if index < jobs.count - 1 {
                            SettingsDivider()
                        }
                    }
                }
            }

            if let sendStatus = controller.lastManualSend {
                ManualSendStatusPanel(status: sendStatus)
            }
        }
    }
}

private struct ActivitySettingsRow: View {
    var job: ScheduleJob

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack(spacing: 12) {
                SettingsIcon(systemImage: "smallcircle.filled.circle", tone: statusTone)

                VStack(alignment: .leading, spacing: 4) {
                    Text(job.name ?? job.id)
                        .font(.body.weight(.medium))
                        .lineLimit(1)
                    Text(job.lastStatus ?? "Not run yet")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }

                Spacer(minLength: 12)

                HStack(spacing: 8) {
                    Text(job.lastRunAt ?? "Never")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .minimumScaleFactor(0.75)

                    if let logPath = job.lastLogPath {
                        Button {
                            revealLog(logPath)
                        } label: {
                            Label("Reveal Log", systemImage: "doc.text.magnifyingglass")
                        }
                        .labelStyle(.iconOnly)
                        .buttonStyle(.borderless)
                        .help("Reveal run log in Finder")
                    }
                }
            }

            if let responseText {
                ClaudeResponseSnippet(title: "Claude Response", text: responseText)
                    .padding(.leading, 44)
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
    }

    private var statusTone: StatusTone {
        StatusTone.status(for: job.lastStatus ?? job.status ?? "")
    }

    private var responseText: String? {
        cleanDisplayText(job.lastClaudeResponseSummary)
    }

    private func revealLog(_ path: String) {
        NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: path)])
    }
}

private struct SettingsGroup<Content: View>: View {
    private var title: String?
    private var content: Content

    init(_ title: String? = nil, @ViewBuilder content: () -> Content) {
        self.title = title
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let title {
                Text(title)
                    .font(.headline)
                    .foregroundStyle(.primary)
                    .padding(.horizontal, 2)
            }

            VStack(spacing: 0) {
                content
            }
            .background(
                Color(nsColor: .controlBackgroundColor),
                in: RoundedRectangle(cornerRadius: 12, style: .continuous)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .stroke(Color(nsColor: .separatorColor).opacity(0.35), lineWidth: 0.5)
            )
        }
    }
}

private struct SettingsDivider: View {
    var body: some View {
        Divider()
            .padding(.leading, 58)
    }
}

private struct SettingsStatusRow: View {
    var title: String
    var detail: String
    var value: String
    var systemImage: String
    var tone: StatusTone

    var body: some View {
        HStack(spacing: 12) {
            SettingsIcon(systemImage: systemImage, tone: tone)

            VStack(alignment: .leading, spacing: 3) {
                Text(title)
                    .font(.body)
                Text(detail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }

            Spacer(minLength: 12)

            StatusPill(text: value, tone: tone)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
    }
}

private struct SettingsValueRow: View {
    var title: String
    var detail: String
    var value: String
    var systemImage: String
    var tone: StatusTone

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            SettingsIcon(systemImage: systemImage, tone: tone)

            VStack(alignment: .leading, spacing: 3) {
                Text(title)
                    .font(.body)
                Text(detail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }

            Spacer(minLength: 12)

            SettingsTrailingValue(value: value)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
    }
}

private struct SettingsActionRow: View {
    var title: String
    var detail: String
    var actionTitle: String
    var systemImage: String
    var tone: StatusTone
    var isProminent: Bool
    var isDisabled: Bool
    var action: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            SettingsIcon(systemImage: systemImage, tone: tone)

            VStack(alignment: .leading, spacing: 3) {
                Text(title)
                    .font(.body)
                Text(detail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }

            Spacer(minLength: 12)

            actionButton
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
    }

    @ViewBuilder
    private var actionButton: some View {
        if isProminent {
            Button(actionTitle, action: action)
                .buttonStyle(.borderedProminent)
                .disabled(isDisabled)
        } else {
            Button(actionTitle, action: action)
                .buttonStyle(.bordered)
                .disabled(isDisabled)
        }
    }
}

private struct SettingsIcon: View {
    var systemImage: String
    var tone: StatusTone

    var body: some View {
        Image(systemName: systemImage)
            .symbolRenderingMode(.hierarchical)
            .font(.system(size: 16, weight: .semibold))
            .foregroundStyle(tone.tint)
            .frame(width: 32, height: 32)
            .background(tone.background, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
    }
}

private struct SettingsTrailingValue: View {
    var value: String

    var body: some View {
        let rows = TimestampRows.rows(for: value)

        VStack(alignment: .trailing, spacing: 1) {
            ForEach(rows.indices, id: \.self) { index in
                Text(rows[index])
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.72)
            }
        }
        .frame(maxWidth: 250, alignment: .trailing)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(rows.joined(separator: " "))
    }
}

struct LoginRequiredPanel: View {
    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: "person.crop.circle.badge.exclamationmark")
                .font(.title3)
                .foregroundStyle(Color.orange)
                .frame(width: 24, height: 24)

            VStack(alignment: .leading, spacing: 4) {
                Text("Claude login required")
                    .font(.callout.weight(.semibold))
                Text("Run `claude auth login`, then refresh.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Spacer(minLength: 8)

            Button {
                copyLoginCommand()
            } label: {
                Label("Copy Login Command", systemImage: "doc.on.doc")
            }
            .labelStyle(.iconOnly)
            .buttonStyle(.borderless)
            .help("Copy login command")
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(StatusTone.warning.background, in: RoundedRectangle(cornerRadius: 8))
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(StatusTone.warning.tint.opacity(0.22), lineWidth: 1)
        )
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Claude login required. Run claude auth login, then refresh.")
    }

    private func copyLoginCommand() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString("claude auth login", forType: .string)
    }
}

struct ManualSendStatusPanel: View {
    var status: ManualSendStatus

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: iconName)
                .font(.title3)
                .foregroundStyle(tone.tint)
                .frame(width: 24, height: 24)

            VStack(alignment: .leading, spacing: 4) {
                Text(status.title)
                    .font(.callout.weight(.semibold))
                    .foregroundStyle(.primary)
                    .fixedSize(horizontal: false, vertical: true)

                Text(status.detail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)

                if let responseText = cleanDisplayText(status.responseText) {
                    ClaudeResponseSnippet(title: "Claude Response", text: responseText)
                        .padding(.top, 2)
                }

                HStack(spacing: 8) {
                    Text("Updated \(Formatters.statusTime.string(from: status.timestamp))")
                    if let rawStatus = status.rawStatus {
                        Text(rawStatus)
                    }
                    if let exitCode = status.exitCode {
                        Text("exit \(exitCode)")
                    }
                }
                .font(.caption2.weight(.medium))
                .foregroundStyle(.secondary)
                .lineLimit(1)
            }

            Spacer(minLength: 8)

            if let logPath = status.logPath {
                Button {
                    revealLog(logPath)
                } label: {
                    Label("Reveal Log", systemImage: "doc.text.magnifyingglass")
                }
                .labelStyle(.iconOnly)
                .buttonStyle(.borderless)
                .help("Reveal send log in Finder")
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(tone.background, in: RoundedRectangle(cornerRadius: 8))
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(tone.tint.opacity(0.22), lineWidth: 1)
        )
        .accessibilityElement(children: .combine)
        .accessibilityLabel(accessibilityLabel)
    }

    private var tone: StatusTone {
        switch status.tone {
        case .pending:
            .info
        case .success:
            .success
        case .warning:
            .warning
        case .failure:
            .danger
        case .skipped:
            .neutral
        }
    }

    private var iconName: String {
        switch status.tone {
        case .pending:
            "paperplane"
        case .success:
            "checkmark.circle.fill"
        case .warning:
            "exclamationmark.triangle.fill"
        case .failure:
            "xmark.octagon.fill"
        case .skipped:
            "forward.end.circle.fill"
        }
    }

    private var accessibilityLabel: String {
        "\(status.title). \(status.detail)"
    }

    private func revealLog(_ path: String) {
        NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: path)])
    }
}

private struct ClaudeResponseSnippet: View {
    var title: String
    var text: String

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.secondary)

            Text(text)
                .font(.callout)
                .foregroundStyle(.primary)
                .lineLimit(6)
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private func cleanDisplayText(_ value: String?) -> String? {
    guard let value = value?.trimmingCharacters(in: .whitespacesAndNewlines), !value.isEmpty else {
        return nil
    }
    return value
}

private struct InlineMessage: View {
    var text: String

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "info.circle")
                .foregroundStyle(.secondary)
            Text(text)
                .foregroundStyle(.secondary)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .font(.callout)
        .padding(.vertical, 8)
    }
}

private struct AppMark: View {
    var size: CGFloat

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: size * 0.22, style: .continuous)
                .fill(Color(red: 0.98, green: 0.96, blue: 0.93))

            RoundedRectangle(cornerRadius: size * 0.22, style: .continuous)
                .stroke(Color.black.opacity(0.08), lineWidth: max(1, size * 0.025))

            Circle()
                .stroke(
                    Color(red: 0.17, green: 0.16, blue: 0.15),
                    style: StrokeStyle(
                        lineWidth: max(2, size * 0.095),
                        lineCap: .round
                    )
                )
                .frame(width: size * 0.55, height: size * 0.55)

            AppMarkCheck()
                .stroke(
                    Color(red: 0.93, green: 0.43, blue: 0.16),
                    style: StrokeStyle(
                        lineWidth: max(2, size * 0.095),
                        lineCap: .round,
                        lineJoin: .round
                    )
                )
                .frame(width: size * 0.48, height: size * 0.36)
                .offset(y: -size * 0.01)
        }
        .frame(width: size, height: size)
    }
}

private struct AppMarkCheck: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.minX + rect.width * 0.12, y: rect.minY + rect.height * 0.56))
        path.addLine(to: CGPoint(x: rect.minX + rect.width * 0.42, y: rect.minY + rect.height * 0.80))
        path.addLine(to: CGPoint(x: rect.minX + rect.width * 0.90, y: rect.minY + rect.height * 0.20))
        return path
    }
}

struct StatusPill: View {
    var text: String
    var tone: StatusTone

    var body: some View {
        HStack(spacing: 6) {
            Circle()
                .fill(tone.tint)
                .frame(width: 6, height: 6)
            Text(text)
                .font(.caption.weight(.semibold))
                .lineLimit(1)
                .minimumScaleFactor(0.8)
        }
        .padding(.horizontal, 9)
        .padding(.vertical, 5)
        .background(tone.background, in: Capsule())
        .foregroundStyle(tone.tint)
    }
}

enum StatusTone {
    case success
    case warning
    case danger
    case info
    case neutral

    static func status(for value: String) -> StatusTone {
        let normalized = value.lowercased()
        if normalized.contains("success") || normalized.contains("ok") || normalized.contains("complete") {
            return .success
        }
        if normalized.contains("fail") || normalized.contains("error") || normalized.contains("timed") {
            return .danger
        }
        if normalized.contains("skip") || normalized.contains("limit") || normalized.contains("warn") {
            return .warning
        }
        return .neutral
    }

    var tint: Color {
        switch self {
        case .success:
            Color.green
        case .warning:
            Color.orange
        case .danger:
            Color.red
        case .info:
            Color.accentColor
        case .neutral:
            Color.secondary
        }
    }

    var background: Color {
        tint.opacity(self == .neutral ? 0.10 : 0.12)
    }
}

enum Formatters {
    static let statusTime: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateStyle = .none
        formatter.timeStyle = .short
        return formatter
    }()
}
