import PromptSchedulerShared
import Foundation

enum MenuBarIconState: Equatable {
    case idle
    case running
    case success
    case warning
    case failure
}

struct ManualSendStatus: Equatable {
    enum Kind: Equatable {
        case send
        case schedule
    }

    enum Tone: Equatable {
        case pending
        case success
        case warning
        case failure
        case skipped
    }

    var tone: Tone
    var title: String
    var detail: String
    var timestamp: Date
    var rawStatus: String?
    var exitCode: Int?
    var logPath: String?
    var responseText: String?
    var provider: String?
    var kind: Kind

    static func sending(providerLabel: String, provider: String, timestamp: Date = Date()) -> ManualSendStatus {
        ManualSendStatus(
            tone: .pending,
            title: "Sending prompt",
            detail: "Starting \(providerLabel) with the OK prompt.",
            timestamp: timestamp,
            provider: provider,
            kind: .send
        )
    }

    static func finished(
        response: RunResponse,
        provider fallbackProvider: String? = nil,
        timestamp: Date = Date()
    ) -> ManualSendStatus {
        guard let result = response.result else {
            return ManualSendStatus(
                tone: response.ok ? .success : .failure,
                title: response.ok ? "Send started" : "Send failed",
                detail: response.error ?? "The CLI did not return run details.",
                timestamp: timestamp,
                provider: fallbackProvider,
                kind: .send
            )
        }

        let providerLabel = result.providerLabel ?? "Provider"
        let mapped = map(status: result.status, exitCode: result.exitCode, providerLabel: providerLabel)
        let detail = cleanMessage(result.message) ?? mapped.detail
        return ManualSendStatus(
            tone: mapped.tone,
            title: mapped.title,
            detail: detail,
            timestamp: timestamp,
            rawStatus: result.status,
            exitCode: result.exitCode,
            logPath: result.logPath,
            responseText: cleanMessage(result.responseSummary ?? result.claudeResponseSummary),
            provider: result.provider ?? fallbackProvider,
            kind: .send
        )
    }

    static func failed(
        _ message: String,
        timestamp: Date = Date(),
        provider: String? = nil,
        kind: Kind = .send
    ) -> ManualSendStatus {
        ManualSendStatus(
            tone: .failure,
            title: "Send failed",
            detail: message,
            timestamp: timestamp,
            provider: provider,
            kind: kind
        )
    }

    static func loginRequired(providerLabel: String, provider: String, timestamp: Date = Date()) -> ManualSendStatus {
        ManualSendStatus(
            tone: .failure,
            title: "\(providerLabel) login required",
            detail: "Sign in with \(providerLabel) before sending prompts.",
            timestamp: timestamp,
            rawStatus: "auth_required",
            provider: provider,
            kind: .send
        )
    }

    private static func map(
        status: String,
        exitCode: Int,
        providerLabel: String
    ) -> (tone: Tone, title: String, detail: String) {
        switch status {
        case "success":
            return (.success, "Send succeeded", "\(providerLabel) accepted the prompt.")
        case "partial_success":
            return (
                .warning,
                "Send partially succeeded",
                "At least one selected provider accepted the prompt."
            )
        case "auth_required":
            return (.failure, "\(providerLabel) login required", "Sign in with \(providerLabel) before sending prompts.")
        case "usage_limit":
            return (.warning, "Usage limit reached", "\(providerLabel) reported a usage limit. Check the log for reset details.")
        case "overlap_skipped":
            return (.warning, "Send skipped", "Another \(providerLabel) send is already running.")
        case "skipped":
            return (.skipped, "Send skipped", "\(providerLabel) did not run for this request.")
        case "failed":
            return (.failure, "Send failed", "\(providerLabel) exited with code \(exitCode).")
        case "timed_out":
            return (.failure, "Send timed out", "\(providerLabel) did not finish within the timeout.")
        default:
            if exitCode == 0 {
                return (.success, "Send finished", "Command status: \(status).")
            }
            return (.failure, "Send failed", "Command status: \(status). Exit code \(exitCode).")
        }
    }

    private static func cleanMessage(_ message: String?) -> String? {
        guard let value = message?.trimmingCharacters(in: .whitespacesAndNewlines), !value.isEmpty else {
            return nil
        }
        return value
    }
}

enum SimpleScheduleKind: String, CaseIterable, Identifiable {
    case daily
    case weekly

    var id: String { rawValue }

    var label: String {
        switch self {
        case .daily:
            "Daily"
        case .weekly:
            "Weekly"
        }
    }
}

enum WakeLoopInterval: String, CaseIterable, Identifiable {
    case off
    case every30Min = "30m"
    case everyHour = "1h"
    case every2Hours = "2h"

    var id: String { rawValue }

    var label: String {
        switch self {
        case .off:
            "Off"
        case .every30Min:
            "30 min"
        case .everyHour:
            "1 h"
        case .every2Hours:
            "2 h"
        }
    }

    init?(scheduleLabel: String?) {
        guard let label = scheduleLabel else { return nil }
        switch label {
        case "every 30m":
            self = .every30Min
        case "every 1h":
            self = .everyHour
        case "every 2h":
            self = .every2Hours
        default:
            return nil
        }
    }
}

enum SimpleScheduleWeekday: String, CaseIterable, Identifiable {
    case mon = "Mon"
    case tue = "Tue"
    case wed = "Wed"
    case thu = "Thu"
    case fri = "Fri"
    case sat = "Sat"
    case sun = "Sun"

    var id: String { rawValue }

    var label: String {
        switch self {
        case .mon:
            "Monday"
        case .tue:
            "Tuesday"
        case .wed:
            "Wednesday"
        case .thu:
            "Thursday"
        case .fri:
            "Friday"
        case .sat:
            "Saturday"
        case .sun:
            "Sunday"
        }
    }
}

struct SimpleScheduleDraft: Equatable {
    var name: String
    var cwd: String
    var prompt: String
    var provider: String
    var kind: SimpleScheduleKind
    var time: String
    var weekday: SimpleScheduleWeekday
    var claudeModel: String
    var codexModel: String

    var daily: String? {
        kind == .daily ? time : nil
    }

    var weekly: String? {
        kind == .weekly ? "\(weekday.rawValue) \(time)" : nil
    }

    var claudeModelOrNil: String? {
        let trimmed = claudeModel.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    var codexModelOrNil: String? {
        let trimmed = codexModel.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }
}

enum SimpleScheduleSaveResult: Equatable {
    case success(String)
    case failure(String)
}

struct ProviderRunSummary: Equatable, Identifiable {
    var id: String { provider }

    var provider: String
    var title: String
    var status: String
    var nextUsageStart: String
    var lastSentTime: String
    var lastSentStatus: String
}

@MainActor
final class AppController: ObservableObject {
    @Published var status: AppStatus?
    @Published var isLoading = false
    @Published var message: String?
    @Published var lastManualSend: ManualSendStatus?
    @Published private var selectedSendProvider: String?
    @Published var wakeLoopPrompt: String
    @Published var claudeModelDefault: String
    @Published var codexModelDefault: String

    private let engine: EngineClient
    private static let sendProviderDefaultsKey = "PromptScheduler.SendProvider"
    private static let sendProviderChoices = ["codex", "claude", "both"]
    static let wakeLoopPromptDefaultsKey = "PromptScheduler.WakeLoopPrompt"
    static let defaultWakeLoopPrompt = "Reply with exactly OK."
    static let claudeModelDefaultsKey = "PromptScheduler.ClaudeModel"
    static let codexModelDefaultsKey = "PromptScheduler.CodexModel"
    static let defaultCodexModel = "gpt-5.4-mini"
    private static let summaryDateFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateStyle = .short
        formatter.timeStyle = .short
        return formatter
    }()

    init(engine: EngineClient = EngineClient()) {
        self.engine = engine
        self.selectedSendProvider = Self.validSendProvider(
            UserDefaults.standard.string(forKey: Self.sendProviderDefaultsKey)
        )
        let storedPrompt = UserDefaults.standard.string(forKey: Self.wakeLoopPromptDefaultsKey)
        self.wakeLoopPrompt = (storedPrompt?.isEmpty == false ? storedPrompt! : Self.defaultWakeLoopPrompt)
        self.claudeModelDefault = UserDefaults.standard.string(forKey: Self.claudeModelDefaultsKey) ?? ""
        self.codexModelDefault = UserDefaults.standard.string(forKey: Self.codexModelDefaultsKey) ?? Self.defaultCodexModel
    }

    func setClaudeModelDefault(_ value: String) {
        claudeModelDefault = value
        UserDefaults.standard.set(value, forKey: Self.claudeModelDefaultsKey)
    }

    func setCodexModelDefault(_ value: String) {
        codexModelDefault = value
        UserDefaults.standard.set(value, forKey: Self.codexModelDefaultsKey)
    }

    var activeProvider: String? {
        if let explicit = status?.activeProvider, !explicit.isEmpty {
            return explicit
        }
        if status?.codex?.available == true {
            return "codex"
        }
        return "claude"
    }

    var activeProviderStatus: ProviderStatus? {
        guard let provider = activeProvider else {
            return nil
        }
        if let providerStatus = status?.providers?[provider] {
            return providerStatus
        }
        if provider == "codex" {
            return status?.codex
        }
        return status?.claude
    }

    var activeProviderLabel: String {
        activeProviderStatus?.label
            ?? status?.activeProviderLabel
            ?? (activeProvider == "codex" ? "Codex" : "Claude Code")
    }

    var sendProviderSelection: String {
        selectedSendProvider ?? "both"
    }

    var sendProviderLabel: String {
        label(for: sendProviderSelection)
    }

    var loginCommand: String {
        loginCommands.joined(separator: " && ")
    }

    var shouldShowLoginCommand: Bool {
        !loginCommands.isEmpty
    }

    var installProvider: String? {
        providerKeys(for: sendProviderSelection).first { provider in
            providerStatus(for: provider)?.available != true
        }
    }

    var installProviderLabel: String? {
        installProvider.map { label(for: $0) }
    }

    var isReady: Bool {
        let providers = providerKeys(for: sendProviderSelection)
        let entries = sendProviderStatusEntries
        return entries.count == providers.count && entries.allSatisfy { _, providerStatus in
            providerStatus.available == true && providerStatus.authenticated == true
        }
    }

    var providerSummaries: [ProviderRunSummary] {
        providerDisplayOrder.map { providerSummary(for: $0) }
    }

    var currentWakeLoopInterval: WakeLoopInterval {
        let jobs = status?.jobs ?? []
        for job in jobs {
            guard job.name == "wake-loop", (job.status ?? "") == "scheduled" else { continue }
            if let interval = WakeLoopInterval(scheduleLabel: job.scheduleLabel) {
                return interval
            }
        }
        return .off
    }

    var providerStatusLines: [String] {
        guard status != nil else {
            return providerDisplayOrder.map { "\(shortLabel(for: $0)): checking" }
        }

        return providerDisplayOrder.map { provider in
            guard let providerStatus = providerStatus(for: provider) else {
                return "\(shortLabel(for: provider)): unavailable"
            }
            return "\(shortLabel(for: provider)): \(shortStatus(providerStatus))"
        }
    }

    var defaultFolder: String {
        SchedulerDefaults.projectFolderPath
    }

    var menuBarIconState: MenuBarIconState {
        if isLoading || lastManualSend?.tone == .pending || hasRunningJob {
            return .running
        }

        guard status != nil else {
            return .running
        }

        if !isReady {
            return .warning
        }

        if let sendStatus = lastManualSend {
            return Self.iconState(for: sendStatus.tone)
        }

        if let jobStatus = latestJobStatus {
            return Self.iconState(forStatus: jobStatus)
        }

        return .idle
    }

    var menuBarIconAccessibilityLabel: String {
        switch menuBarIconState {
        case .idle:
            "\(sendProviderLabel) status idle"
        case .running:
            "\(sendProviderLabel) status running"
        case .success:
            "\(sendProviderLabel) status last run succeeded"
        case .warning:
            "\(sendProviderLabel) status needs attention"
        case .failure:
            "\(sendProviderLabel) status last run failed"
        }
    }

    func refresh() async {
        await runTask {
            status = try await engine.status()
        }
    }

    var scheduledJobs: [ScheduleJob] {
        (status?.jobs ?? [])
            .filter { ($0.status ?? "") == "scheduled" }
            .sorted {
                ($0.scheduleLabel ?? "") < ($1.scheduleLabel ?? "")
            }
    }

    func removeSchedule(_ jobID: String) async {
        await runTask {
            let response = try await engine.removeSchedule(jobID: jobID)
            if !response.ok {
                message = response.error ?? "Could not cancel the scheduled job."
                return
            }
            message = "Cancelled scheduled job."
            status = try await engine.status()
        }
    }

    func installActiveProvider() async {
        await runTask {
            let provider = installProvider ?? activeProvider ?? "claude"
            status = try await engine.setup(install: true, provider: provider)
            message = isReady
                ? "\(sendProviderLabel) is ready."
                : "\(label(for: provider)) setup is incomplete."
        }
    }

    func startNow(cwd: String? = nil) async {
        if !isReady {
            let detail = sendProviderReadinessIssue ?? "\(sendProviderLabel) is not ready."
            let sendStatus = ManualSendStatus.failed(detail, provider: sendProviderSelection)
            lastManualSend = sendStatus
            message = sendStatus.title
            return
        }
        let provider = sendProviderSelection
        lastManualSend = .sending(providerLabel: sendProviderLabel, provider: provider)
        await runTask(onError: { [weak self, provider] error in
            let status = ManualSendStatus.failed(error.localizedDescription, provider: provider)
            self?.lastManualSend = status
            self?.message = status.title
        }) {
            let targetFolder = cwd ?? defaultFolder
            try ensureDefaultFolderIfNeeded(targetFolder)
            let response = try await engine.startNow(cwd: targetFolder, provider: provider)
            let sendStatus = ManualSendStatus.finished(response: response, provider: provider)
            lastManualSend = sendStatus
            message = sendStatus.title
            do {
                status = try await engine.status()
            } catch {
                message = "\(sendStatus.title). Could not refresh status: \(error.localizedDescription)"
            }
        }
    }

    func setWakeLoopInterval(_ interval: WakeLoopInterval) async {
        let provider = sendProviderSelection
        await runTask {
            if interval == .off {
                let response = try await engine.stopWakeLoop()
                if !response.ok {
                    message = response.error ?? "Could not stop the wake-up loop."
                    return
                }
                message = "Wake-up loop stopped."
            } else {
                let targetFolder = defaultFolder
                try ensureDefaultFolderIfNeeded(targetFolder)
                let response = try await engine.startWakeLoop(
                    cwd: targetFolder,
                    provider: provider,
                    every: interval.rawValue,
                    prompt: wakeLoopPrompt
                )
                if !response.ok {
                    message = response.error ?? "Could not start the wake-up loop."
                    return
                }
                message = "Wake-up loop set to \(interval.label)."
            }
            do {
                status = try await engine.status()
            } catch {
                message = "Wake-up loop updated. Could not refresh status: \(error.localizedDescription)"
            }
        }
    }

    func setWakeLoopPrompt(_ text: String) async {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        let next = trimmed.isEmpty ? Self.defaultWakeLoopPrompt : trimmed
        wakeLoopPrompt = next
        UserDefaults.standard.set(next, forKey: Self.wakeLoopPromptDefaultsKey)
        let active = currentWakeLoopInterval
        if active != .off {
            await setWakeLoopInterval(active)
        }
    }

    func setSendProviderSelection(_ provider: String) {
        guard let value = Self.validSendProvider(provider) else {
            return
        }
        selectedSendProvider = value
        UserDefaults.standard.set(value, forKey: Self.sendProviderDefaultsKey)
    }

    func createSimpleSchedule(_ draft: SimpleScheduleDraft) async -> SimpleScheduleSaveResult {
        let name = draft.name.trimmingCharacters(in: .whitespacesAndNewlines)
        let cwd = draft.cwd.trimmingCharacters(in: .whitespacesAndNewlines)
        let prompt = draft.prompt.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty else {
            return .failure("Name is required.")
        }
        guard !cwd.isEmpty else {
            return .failure("Project folder is required.")
        }
        guard !prompt.isEmpty else {
            return .failure("Message is required.")
        }

        isLoading = true
        defer { isLoading = false }

        do {
            try ensureDefaultFolderIfNeeded(cwd)
            let response = try await engine.addSchedule(
                name: name,
                cwd: cwd,
                prompt: prompt,
                provider: draft.provider,
                daily: draft.daily,
                weekly: draft.weekly,
                claudeModel: draft.claudeModelOrNil,
                codexModel: draft.codexModelOrNil
            )
            guard response.ok else {
                return .failure(response.error ?? "Could not create the schedule.")
            }
            let scheduleLabel = response.job?.scheduleLabel ?? draft.time
            message = "Scheduled \(scheduleLabel)."
            do {
                status = try await engine.status()
            } catch {
                message = "Scheduled \(scheduleLabel). Could not refresh status: \(error.localizedDescription)"
            }
            return .success("Scheduled \(scheduleLabel).")
        } catch {
            message = error.localizedDescription
            return .failure(error.localizedDescription)
        }
    }

    private func runTask(
        onError: ((Error) -> Void)? = nil,
        _ operation: () async throws -> Void
    ) async {
        isLoading = true
        defer { isLoading = false }
        do {
            try await operation()
        } catch {
            if let onError {
                onError(error)
            } else {
                message = error.localizedDescription
            }
        }
    }

    private func ensureDefaultFolderIfNeeded(_ path: String) throws {
        let defaultPath = SchedulerDefaults.projectFolderPath
        if (path as NSString).standardizingPath == (defaultPath as NSString).standardizingPath {
            _ = try SchedulerDefaults.ensureProjectFolder()
        }
    }

    private var hasRunningJob: Bool {
        (status?.jobs ?? []).contains { job in
            let normalized = (job.status ?? "").lowercased()
            return normalized.contains("running") || normalized.contains("in_progress")
        }
    }

    private var providerDisplayOrder: [String] {
        ["claude", "codex"]
    }

    private func providerSummary(for provider: String) -> ProviderRunSummary {
        let statusText: String
        if status == nil {
            statusText = "checking"
        } else if let providerStatus = providerStatus(for: provider) {
            statusText = shortStatus(providerStatus)
        } else {
            statusText = "unavailable"
        }

        let lastSent = latestSentState(for: provider)
        return ProviderRunSummary(
            provider: provider,
            title: shortLabel(for: provider),
            status: statusText,
            nextUsageStart: nextUsageStartText(for: provider),
            lastSentTime: lastSent?.time ?? "Never",
            lastSentStatus: lastSent?.status ?? "Never"
        )
    }

    private func nextUsageStartText(for provider: String) -> String {
        guard let date = nextUsageStartDate(for: provider) else {
            return "Unknown"
        }
        return Self.summaryDateFormatter.string(from: date)
    }

    private func nextUsageStartDate(for provider: String) -> Date? {
        switch provider {
        case "claude":
            return Self.parseISODate(status?.reset.nextResetAt)
        case "codex":
            return Self.parseISODate(status?.reset.codexNextResetAt)
        default:
            return nil
        }
    }

    private func latestSentState(for provider: String) -> (time: String, status: String)? {
        let manual = latestManualSendState(for: provider)
        let job = latestJobState(for: provider)

        if let manual, let job {
            return manual.date >= job.date ? (manual.time, manual.status) : (job.time, job.status)
        }
        if let manual {
            return (manual.time, manual.status)
        }
        if let job {
            return (job.time, job.status)
        }
        return nil
    }

    private func latestManualSendState(for provider: String) -> (date: Date, time: String, status: String)? {
        guard let send = lastManualSend,
              send.kind == .send,
              providerSelection(send.provider, includes: provider) else {
            return nil
        }
        return (
            send.timestamp,
            Self.summaryDateFormatter.string(from: send.timestamp),
            send.title
        )
    }

    private func latestJobState(for provider: String) -> (date: Date, time: String, status: String)? {
        guard let job = (status?.jobs ?? [])
            .filter({
                providerSelection($0.provider, includes: provider)
                    && ($0.lastRunAt != nil || $0.lastStatus != nil)
            })
            .sorted(by: { (left, right) in
                (Self.parseISODate(left.lastRunAt) ?? .distantPast)
                    > (Self.parseISODate(right.lastRunAt) ?? .distantPast)
            })
            .first else {
            return nil
        }

        let date = Self.parseISODate(job.lastRunAt) ?? .distantPast
        return (
            date,
            Self.displayTimestamp(job.lastRunAt) ?? "Unknown",
            job.lastStatus ?? job.status ?? "Unknown"
        )
    }

    private var sendProviderStatusEntries: [(String, ProviderStatus)] {
        providerKeys(for: sendProviderSelection).compactMap { provider in
            guard let status = providerStatus(for: provider) else {
                return nil
            }
            return (provider, status)
        }
    }

    private var sendProviderReadinessIssue: String? {
        for provider in providerKeys(for: sendProviderSelection) {
            guard let status = providerStatus(for: provider) else {
                return "\(label(for: provider)) status unknown"
            }
            if status.available != true {
                return "\(label(for: provider)) not installed"
            }
            if status.authenticated == false {
                return "\(label(for: provider)) login required"
            }
            if status.authenticated != true {
                return "\(label(for: provider)) login unknown"
            }
        }
        return nil
    }

    private var loginCommands: [String] {
        providerKeys(for: sendProviderSelection).compactMap { provider in
            guard providerStatus(for: provider)?.authenticated == false else {
                return nil
            }
            return providerStatus(for: provider)?.loginCommand ?? loginCommand(for: provider)
        }
    }

    private func label(for provider: String) -> String {
        if provider == "both" {
            return "Codex + Claude Code"
        }
        return provider == "codex" ? "Codex" : "Claude Code"
    }

    private func shortLabel(for provider: String) -> String {
        provider == "codex" ? "Codex" : "Claude"
    }

    private func providerKeys(for selection: String) -> [String] {
        selection == "both" ? ["codex", "claude"] : [selection]
    }

    private func providerSelection(_ selection: String?, includes provider: String) -> Bool {
        guard let selection else {
            return false
        }
        return selection == "both" || selection == provider
    }

    private func providerStatus(for provider: String) -> ProviderStatus? {
        if let status = status?.providers?[provider] {
            return status
        }
        if provider == "codex" {
            return status?.codex
        }
        if provider == "claude" {
            return status?.claude
        }
        return nil
    }

    private func loginCommand(for provider: String) -> String {
        provider == "codex" ? "codex login" : "claude auth login"
    }

    private static func validSendProvider(_ provider: String?) -> String? {
        guard let provider = provider?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(),
              sendProviderChoices.contains(provider) else {
            return nil
        }
        return provider
    }

    private static func displayTimestamp(_ value: String?) -> String? {
        guard let value = value?.trimmingCharacters(in: .whitespacesAndNewlines),
              !value.isEmpty else {
            return nil
        }
        guard let date = parseISODate(value) else {
            return value
        }
        return summaryDateFormatter.string(from: date)
    }

    private static func parseISODate(_ value: String?) -> Date? {
        guard let value = value?.trimmingCharacters(in: .whitespacesAndNewlines),
              !value.isEmpty else {
            return nil
        }

        let fractionalFormatter = ISO8601DateFormatter()
        fractionalFormatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = fractionalFormatter.date(from: value) {
            return date
        }

        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.date(from: value)
    }

    private func shortStatus(_ status: ProviderStatus) -> String {
        if status.available != true {
            return "not installed"
        }
        if status.authenticated == true {
            return "ready"
        }
        if status.authenticated == false {
            return "login required"
        }
        return "login unknown"
    }

    private var latestJobStatus: String? {
        (status?.jobs ?? [])
            .filter { $0.lastRunAt != nil || $0.lastStatus != nil }
            .sorted { ($0.lastRunAt ?? "") > ($1.lastRunAt ?? "") }
            .compactMap(Self.jobStatusValue)
            .first
    }

    private static func jobStatusValue(_ job: ScheduleJob) -> String {
        job.lastStatus ?? job.status ?? ""
    }

    private static func iconState(for tone: ManualSendStatus.Tone) -> MenuBarIconState {
        switch tone {
        case .pending:
            .running
        case .success:
            .success
        case .warning, .skipped:
            .warning
        case .failure:
            .failure
        }
    }

    private static func iconState(forStatus status: String) -> MenuBarIconState {
        let normalized = status.lowercased()
        if normalized.contains("running") || normalized.contains("in_progress") {
            return .running
        }
        if normalized.contains("partial") {
            return .warning
        }
        if normalized.contains("success") || normalized.contains("ok") || normalized.contains("complete") {
            return .success
        }
        if normalized.contains("fail")
            || normalized.contains("error")
            || normalized.contains("timed")
            || normalized.contains("auth") {
            return .failure
        }
        if normalized.contains("skip") || normalized.contains("limit") || normalized.contains("warn") {
            return .warning
        }
        return .idle
    }
}
