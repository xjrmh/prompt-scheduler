import CSSShared
import SwiftUI
import AppKit

struct MenuBarContent: View {
    @ObservedObject var controller: AppController
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            MenuHeader(controller: controller)

            Button {
                Task { await controller.startNow() }
            } label: {
                HStack(spacing: 12) {
                    Image(systemName: "paperplane.fill")
                        .font(.system(size: 17, weight: .semibold))
                        .frame(width: 32, height: 32)
                        .background(Color.white.opacity(0.18), in: RoundedRectangle(cornerRadius: 8))

                    VStack(alignment: .leading, spacing: 2) {
                        Text("Send Prompt Now")
                            .font(.headline)
                        Text(primaryActionDetail)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }

                    Spacer(minLength: 10)

                    if controller.isLoading {
                        ProgressView()
                            .controlSize(.small)
                    } else {
                        Image(systemName: "chevron.right")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(.secondary)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .buttonStyle(PrimaryActionButtonStyle(tint: controller.isReady ? .accentColor : .secondary))
            .disabled(controller.isLoading || !controller.isReady)
            .help("Send prompt now")

            if controller.status?.claude.available != true, controller.status != nil {
                Button {
                    Task { await controller.installClaudeCode() }
                } label: {
                    Label("Install Claude Code", systemImage: "square.and.arrow.down")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(SecondaryActionButtonStyle())
                .disabled(controller.isLoading)
            }

            if shouldShowLoginPanel {
                LoginRequiredPanel()
            }

            if let sendStatus = controller.lastManualSend {
                ManualSendStatusPanel(status: sendStatus)
            }

            MenuSummary(
                observedReset: controller.status?.reset.nextResetAt ?? "Unknown",
                estimatedReset: controller.status?.reset.nextEstimatedResetAt ?? "Unknown",
                rateLimits: controller.status?.reset.rateLimits,
                scheduleCount: controller.status?.jobs.count ?? 0
            )

            HStack(spacing: 8) {
                Button {
                    openWindow(id: "scheduler")
                    Task { await controller.refresh() }
                } label: {
                    Label("Scheduler", systemImage: "calendar")
                        .frame(maxWidth: .infinity)
                }

                Button {
                    Task { await controller.refresh() }
                } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                        .frame(maxWidth: .infinity)
                }
                .disabled(controller.isLoading)
            }
            .buttonStyle(SecondaryActionButtonStyle())

            Divider()

            HStack {
                Text(controller.readinessText)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)

                Spacer()

                Button {
                    NSApplication.shared.terminate(nil)
                } label: {
                    Label("Quit", systemImage: "power")
                }
                .buttonStyle(.borderless)
                .controlSize(.small)
            }
        }
        .padding(16)
        .task {
            await controller.refresh()
        }
    }

    private var primaryActionDetail: String {
        guard let status = controller.status else {
            return "Checking setup"
        }
        if status.claude.available != true {
            return "Claude Code is not installed"
        }
        if status.claude.authenticated == false {
            return "Claude login required"
        }
        return "Default project folder"
    }

    private var shouldShowLoginPanel: Bool {
        controller.status?.claude.available == true
            && controller.status?.claude.authenticated == false
            && controller.lastManualSend == nil
    }
}

private struct MenuHeader: View {
    @ObservedObject var controller: AppController

    var body: some View {
        HStack(spacing: 12) {
            AppMark(size: 42)

            VStack(alignment: .leading, spacing: 3) {
                Text("Claude Scheduler")
                    .font(.title3.weight(.semibold))
                    .lineLimit(1)
                Text(headerDetail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }

            Spacer(minLength: 8)

            StatusPill(text: pillText, tone: readinessTone)
        }
    }

    private var headerDetail: String {
        guard let status = controller.status else {
            return "Checking setup"
        }
        if status.claude.available != true {
            return "Setup needed"
        }
        if status.claude.authenticated == false {
            return "Sign in required"
        }
        return "\(status.jobs.count) \(status.jobs.count == 1 ? "schedule" : "schedules")"
    }

    private var pillText: String {
        guard controller.status != nil else {
            return "Checking"
        }
        return controller.isReady ? "Ready" : "Needs Setup"
    }

    private var readinessTone: StatusTone {
        guard let status = controller.status else {
            return .info
        }
        if status.claude.available == true && status.claude.authenticated == true {
            return .success
        }
        return .warning
    }
}

private struct MenuSummary: View {
    var observedReset: String
    var estimatedReset: String
    var rateLimits: RateLimits?
    var scheduleCount: Int

    var body: some View {
        VStack(spacing: 8) {
            ResetSummaryTile(
                observedReset: observedReset,
                estimatedReset: estimatedReset,
                rateLimits: rateLimits
            )

            SummaryTile(
                title: "Schedules",
                value: scheduleCount == 1 ? "1 schedule" : "\(scheduleCount) schedules",
                systemImage: "calendar.badge.clock",
                tone: scheduleCount > 0 ? .success : .neutral
            )
        }
    }
}

private struct ResetSummaryTile: View {
    var observedReset: String
    var estimatedReset: String
    var rateLimits: RateLimits?

    var body: some View {
        HStack(alignment: .top, spacing: 9) {
            Image(systemName: "clock.arrow.circlepath")
                .font(.callout.weight(.semibold))
                .foregroundStyle(tone.tint)
                .frame(width: 24, height: 24)

            HStack(alignment: .top, spacing: 14) {
                ResetSummaryColumn(
                    title: primaryTitle,
                    value: primaryValue
                )

                Divider()
                    .frame(height: 44)

                ResetSummaryColumn(
                    title: secondaryTitle,
                    value: secondaryValue
                )
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            Spacer(minLength: 0)
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 8))
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(Color.secondary.opacity(0.12), lineWidth: 1)
        )
    }

    private var tone: StatusTone {
        hasFiveHourUsage || observedReset != "Unknown" || estimatedReset != "Unknown" ? .info : .neutral
    }

    private var hasFiveHourUsage: Bool {
        rateLimits?.fiveHour != nil
    }

    private var primaryTitle: String {
        hasFiveHourUsage ? "5h usage" : "Observed reset"
    }

    private var primaryValue: String {
        guard let fiveHour = rateLimits?.fiveHour else {
            return observedReset
        }
        guard let usedPercentage = fiveHour.usedPercentage else {
            return "Unknown"
        }
        return "\(Int(usedPercentage.rounded()))% used"
    }

    private var secondaryTitle: String {
        hasFiveHourUsage ? "Fresh at" : "Estimated reset"
    }

    private var secondaryValue: String {
        if let fiveHour = rateLimits?.fiveHour {
            return fiveHour.resetsAtIso ?? "Unknown"
        }
        return estimatedReset
    }
}

private struct ResetSummaryColumn: View {
    var title: String
    var value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(title)
                .font(.caption2)
                .foregroundStyle(.secondary)
            SummaryValueText(
                value: value,
                font: .caption.weight(.semibold),
                minimumScaleFactor: 0.75
            )
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct SummaryTile: View {
    var title: String
    var value: String
    var systemImage: String
    var tone: StatusTone

    var body: some View {
        HStack(spacing: 9) {
            Image(systemName: systemImage)
                .font(.callout.weight(.semibold))
                .foregroundStyle(tone.tint)
                .frame(width: 24, height: 24)

            VStack(alignment: .leading, spacing: 1) {
                Text(title)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                SummaryValueText(
                    value: value,
                    font: .caption.weight(.semibold),
                    minimumScaleFactor: 0.75
                )
            }

            Spacer(minLength: 0)
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 8))
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(Color.secondary.opacity(0.12), lineWidth: 1)
        )
    }
}

private struct SummaryValueText: View {
    var value: String
    var font: Font
    var minimumScaleFactor: CGFloat

    var body: some View {
        let rows = TimestampRows.rows(for: value)

        VStack(alignment: .leading, spacing: 0) {
            ForEach(rows.indices, id: \.self) { index in
                Text(rows[index])
                    .font(font)
                    .lineLimit(1)
                    .minimumScaleFactor(minimumScaleFactor)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(rows.joined(separator: " "))
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

struct SchedulerWindow: View {
    @ObservedObject var controller: AppController
    @State private var selectedPane: SchedulerPane? = .overview

    var body: some View {
        NavigationSplitView {
            SchedulerSidebar(
                controller: controller,
                selection: $selectedPane
            )
            .navigationSplitViewColumnWidth(min: 210, ideal: 230, max: 280)
        } detail: {
            SchedulerDetail(
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
                .help("Refresh Claude Scheduler status")
            }
        }
        .sheet(isPresented: $controller.showAddSchedule) {
            AddScheduleView(controller: controller)
        }
    }
}

private enum SchedulerPane: String, CaseIterable, Identifiable {
    case overview
    case schedules
    case activity

    var id: Self { self }

    var title: String {
        switch self {
        case .overview:
            "General"
        case .schedules:
            "Schedules"
        case .activity:
            "Activity"
        }
    }

    var subtitle: String {
        switch self {
        case .overview:
            "Claude Code setup, reset times, and quick actions."
        case .schedules:
            "Create and manage automated prompt sessions."
        case .activity:
            "Recent scheduler runs and delivery status."
        }
    }

    var systemImage: String {
        switch self {
        case .overview:
            "gearshape"
        case .schedules:
            "calendar"
        case .activity:
            "clock.arrow.circlepath"
        }
    }
}

private struct SchedulerSidebar: View {
    @ObservedObject var controller: AppController
    @Binding var selection: SchedulerPane?

    var body: some View {
        VStack(spacing: 0) {
            SidebarHeader(controller: controller)
                .padding(.horizontal, 14)
                .padding(.top, 16)
                .padding(.bottom, 10)

            List(selection: $selection) {
                Section {
                    ForEach(SchedulerPane.allCases) { pane in
                        Label(pane.title, systemImage: pane.systemImage)
                            .tag(pane)
                    }
                }
            }
            .listStyle(.sidebar)
            .scrollContentBackground(.hidden)

            SidebarStatusSummary(
                claudeCodeText: claudeCodeText,
                claudeCodeTone: claudeCodeTone,
                scheduleCountText: scheduleCountText,
                scheduleTone: (controller.status?.jobs ?? []).isEmpty ? .neutral : .success
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

    private var scheduleCountText: String {
        let count = controller.status?.jobs.count ?? 0
        return count == 1 ? "1 schedule" : "\(count) schedules"
    }
}

private struct SidebarHeader: View {
    @ObservedObject var controller: AppController

    var body: some View {
        HStack(spacing: 10) {
            AppMark(size: 36)

            VStack(alignment: .leading, spacing: 3) {
                Text("Claude Scheduler")
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
    var scheduleCountText: String
    var scheduleTone: StatusTone

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
                SidebarStatusRow(
                    title: "Schedules",
                    value: scheduleCountText,
                    tone: scheduleTone
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

private struct SchedulerDetail: View {
    @ObservedObject var controller: AppController
    var pane: SchedulerPane

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
                case .schedules:
                    SchedulesPane(controller: controller)
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
        case .schedules:
            Button {
                controller.showAddSchedule = true
            } label: {
                Label("Add Schedule", systemImage: "plus")
            }
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
                    detail: "Updates setup, reset, and schedule information.",
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
                    detail: "Used for manual sends and new schedules.",
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
                    detail: "Install the Claude CLI before adding schedules.",
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

private struct SchedulesPane: View {
    @ObservedObject var controller: AppController

    var body: some View {
        let jobs = controller.status?.jobs ?? []

        VStack(alignment: .leading, spacing: 18) {
            if jobs.isEmpty {
                EmptySchedulesView {
                    controller.showAddSchedule = true
                }
            } else {
                SettingsGroup {
                    ForEach(Array(jobs.enumerated()), id: \.element.id) { index, job in
                        ScheduleSettingsRow(job: job) {
                            Task { await controller.removeJob(id: job.id) }
                        }
                        if index < jobs.count - 1 {
                            SettingsDivider()
                        }
                    }
                }
            }

            SettingsGroup("About Scheduling") {
                SettingsValueRow(
                    title: "Default Prompt",
                    detail: "New schedules start with a concise OK prompt.",
                    value: "Reply with exactly OK.",
                    systemImage: "text.bubble",
                    tone: .neutral
                )
            }
        }
    }
}

private struct EmptySchedulesView: View {
    var addSchedule: () -> Void

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "calendar.badge.plus")
                .symbolRenderingMode(.hierarchical)
                .font(.system(size: 42, weight: .regular))
                .foregroundStyle(Color.accentColor)

            VStack(spacing: 4) {
                Text("No Schedules")
                    .font(.title3.weight(.semibold))
                Text("Add a schedule to start Claude automatically at a specific time.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Button {
                addSchedule()
            } label: {
                Label("Add Schedule", systemImage: "plus")
            }
            .buttonStyle(.borderedProminent)
            .padding(.top, 2)
        }
        .padding(28)
        .frame(maxWidth: .infinity, minHeight: 220)
        .background(
            Color(nsColor: .controlBackgroundColor),
            in: RoundedRectangle(cornerRadius: 12, style: .continuous)
        )
    }
}

private struct ScheduleSettingsRow: View {
    var job: ScheduleJob
    var remove: () -> Void

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            SettingsIcon(systemImage: "clock", tone: statusTone)

            VStack(alignment: .leading, spacing: 4) {
                Text(job.name ?? "Schedule")
                    .font(.body.weight(.medium))
                    .lineLimit(1)

                Text(job.scheduleLabel ?? "Scheduled")
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)

                if let cwd = job.cwd {
                    Text(cwd)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                }
            }

            Spacer(minLength: 12)

            VStack(alignment: .trailing, spacing: 6) {
                StatusPill(text: statusText, tone: statusTone)
                Text(job.lastRunAt ?? "Never run")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
            }

            Button(role: .destructive, action: remove) {
                Label("Remove", systemImage: "trash")
            }
            .labelStyle(.iconOnly)
            .buttonStyle(.borderless)
            .help("Remove schedule")
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
    }

    private var statusText: String {
        job.lastStatus ?? job.status ?? "Not run yet"
    }

    private var statusTone: StatusTone {
        StatusTone.status(for: statusText)
    }
}

private struct ActivityPane: View {
    @ObservedObject var controller: AppController

    var body: some View {
        let jobs = Array((controller.status?.jobs ?? []).prefix(8))

        VStack(alignment: .leading, spacing: 18) {
            if jobs.isEmpty {
                SettingsGroup {
                    SettingsValueRow(
                        title: "No Recent Activity",
                        detail: "Runs will appear here after schedules start.",
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

            Text(job.lastRunAt ?? "Never")
                .font(.callout)
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .minimumScaleFactor(0.75)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
    }

    private var statusTone: StatusTone {
        StatusTone.status(for: job.lastStatus ?? job.status ?? "")
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

struct AddScheduleView: View {
    @ObservedObject var controller: AppController
    @Environment(\.dismiss) private var dismiss

    @State private var name = ""
    @State private var folder = SchedulerDefaults.projectFolderPath
    @State private var kind: ScheduleKind = .daily
    @State private var time = Date()
    @State private var onceDate = Date().addingTimeInterval(3600)
    @State private var weeklyDays: Set<Weekday> = [.mon, .tue, .wed, .thu, .fri]
    @State private var prompt = "Reply with exactly OK."

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                AppMark(size: 40)

                VStack(alignment: .leading, spacing: 3) {
                    Text("Add Schedule")
                        .font(.title2.weight(.semibold))
                    Text(scheduleSummary)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Spacer()
            }
            .padding(22)

            Divider()

            Form {
                LabeledContent("Name") {
                    TextField("Schedule name", text: $name)
                }

                LabeledContent("Project") {
                    HStack(spacing: 8) {
                        TextField("Project folder", text: $folder)
                            .truncationMode(.middle)
                        Button {
                            chooseFolder()
                        } label: {
                            Label("Choose Folder", systemImage: "folder")
                        }
                    }
                }

                LabeledContent("When") {
                    Picker("When", selection: $kind) {
                        Text("Once").tag(ScheduleKind.once)
                        Text("Daily").tag(ScheduleKind.daily)
                        Text("Custom Days").tag(ScheduleKind.weekly)
                    }
                    .labelsHidden()
                    .pickerStyle(.segmented)
                    .frame(maxWidth: 360)
                }

                if kind == .once {
                    LabeledContent("Run at") {
                        DatePicker("Run at", selection: $onceDate)
                            .labelsHidden()
                    }
                } else {
                    LabeledContent("Time") {
                        DatePicker("Time", selection: $time, displayedComponents: .hourAndMinute)
                            .labelsHidden()
                    }

                    if kind == .weekly {
                        LabeledContent("Days") {
                            WeekdayPicker(selection: $weeklyDays)
                        }
                    }
                }

                LabeledContent("Prompt") {
                    TextField("Prompt", text: $prompt, axis: .vertical)
                        .lineLimit(3...6)
                }
            }
            .formStyle(.grouped)
            .padding(22)

            Divider()

            HStack {
                Spacer()
                Button("Cancel") {
                    dismiss()
                }
                Button {
                    save()
                } label: {
                    Label("Save Schedule", systemImage: "checkmark")
                }
                .keyboardShortcut(.defaultAction)
                .disabled(!canSave)
            }
            .padding(18)
        }
        .frame(width: 580)
    }

    private var canSave: Bool {
        !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !folder.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && (kind != .weekly || !weeklyDays.isEmpty)
    }

    private var scheduleSummary: String {
        switch kind {
        case .once:
            return "Once at \(Formatters.once.string(from: onceDate))"
        case .daily:
            return "Daily at \(Formatters.displayTime.string(from: time))"
        case .weekly:
            let days = Weekday.ordered
                .filter { weeklyDays.contains($0) }
                .map(\.rawValue)
                .joined(separator: ", ")
            return days.isEmpty ? "Custom days" : "\(days) at \(Formatters.displayTime.string(from: time))"
        }
    }

    private func chooseFolder() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        if panel.runModal() == .OK, let url = panel.url {
            folder = url.path
        }
    }

    private func save() {
        let input = ScheduleInput(
            name: name.trimmingCharacters(in: .whitespacesAndNewlines),
            cwd: folder.trimmingCharacters(in: .whitespacesAndNewlines),
            prompt: prompt.trimmingCharacters(in: .whitespacesAndNewlines),
            kind: kind,
            value: scheduleValue()
        )
        Task {
            await controller.addSchedule(input)
            dismiss()
        }
    }

    private func scheduleValue() -> String {
        switch kind {
        case .once:
            return Formatters.once.string(from: onceDate)
        case .daily:
            return Formatters.time.string(from: time)
        case .weekly:
            let days = Weekday.ordered
                .filter { weeklyDays.contains($0) }
                .map(\.rawValue)
                .joined(separator: ",")
            return "\(days) \(Formatters.time.string(from: time))"
        }
    }
}

struct WeekdayPicker: View {
    @Binding var selection: Set<Weekday>

    var body: some View {
        HStack(spacing: 6) {
            ForEach(Weekday.ordered, id: \.self) { day in
                Toggle(day.rawValue, isOn: Binding(
                    get: { selection.contains(day) },
                    set: { isOn in
                        if isOn {
                            selection.insert(day)
                        } else {
                            selection.remove(day)
                        }
                    }
                ))
                .toggleStyle(.button)
                .controlSize(.small)
            }
        }
    }
}

enum Weekday: String, CaseIterable {
    case mon = "Mon"
    case tue = "Tue"
    case wed = "Wed"
    case thu = "Thu"
    case fri = "Fri"
    case sat = "Sat"
    case sun = "Sun"

    static let ordered: [Weekday] = [.mon, .tue, .wed, .thu, .fri, .sat, .sun]
}

struct SectionTitle: View {
    var title: String
    var systemImage: String

    init(_ title: String, systemImage: String) {
        self.title = title
        self.systemImage = systemImage
    }

    var body: some View {
        Label(title, systemImage: systemImage)
            .font(.headline)
            .foregroundStyle(.primary)
    }
}

struct StatusBadge: View {
    var title: String
    var value: String
    var systemImage: String
    var tone: StatusTone

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: systemImage)
                .font(.callout.weight(.semibold))
                .foregroundStyle(tone.tint)
                .frame(width: 28, height: 28)
                .background(tone.background, in: RoundedRectangle(cornerRadius: 8))

            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                SummaryValueText(
                    value: value,
                    font: .callout.weight(.medium),
                    minimumScaleFactor: 0.8
                )
            }

            Spacer(minLength: 0)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 8))
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(tone.tint.opacity(0.16), lineWidth: 1)
        )
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

struct PrimaryActionButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled
    var tint: Color

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .padding(12)
            .background(
                tint.opacity(configuration.isPressed ? 0.18 : 0.12),
                in: RoundedRectangle(cornerRadius: 8)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(tint.opacity(0.24), lineWidth: 1)
            )
            .opacity(isEnabled ? 1 : 0.55)
            .contentShape(RoundedRectangle(cornerRadius: 8))
    }
}

struct SecondaryActionButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.callout.weight(.medium))
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .background(
                Color(nsColor: .controlBackgroundColor).opacity(configuration.isPressed ? 0.65 : 1),
                in: RoundedRectangle(cornerRadius: 8)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(Color.secondary.opacity(0.12), lineWidth: 1)
            )
            .opacity(isEnabled ? 1 : 0.5)
            .contentShape(RoundedRectangle(cornerRadius: 8))
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
    static let time: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "HH:mm"
        return formatter
    }()

    static let displayTime: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateStyle = .none
        formatter.timeStyle = .short
        return formatter
    }()

    static let once: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd HH:mm"
        return formatter
    }()

    static let statusTime: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateStyle = .none
        formatter.timeStyle = .short
        return formatter
    }()
}
