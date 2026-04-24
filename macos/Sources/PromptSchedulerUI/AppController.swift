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

    static func sending(providerLabel: String, timestamp: Date = Date()) -> ManualSendStatus {
        ManualSendStatus(
            tone: .pending,
            title: "Sending prompt",
            detail: "Starting \(providerLabel) with the OK prompt.",
            timestamp: timestamp
        )
    }

    static func finished(response: RunResponse, timestamp: Date = Date()) -> ManualSendStatus {
        guard let result = response.result else {
            return ManualSendStatus(
                tone: response.ok ? .success : .failure,
                title: response.ok ? "Send started" : "Send failed",
                detail: response.error ?? "The CLI did not return run details.",
                timestamp: timestamp
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
            responseText: cleanMessage(result.responseSummary ?? result.claudeResponseSummary)
        )
    }

    static func failed(_ message: String, timestamp: Date = Date()) -> ManualSendStatus {
        ManualSendStatus(
            tone: .failure,
            title: "Send failed",
            detail: message,
            timestamp: timestamp
        )
    }

    static func loginRequired(providerLabel: String, timestamp: Date = Date()) -> ManualSendStatus {
        ManualSendStatus(
            tone: .failure,
            title: "\(providerLabel) login required",
            detail: "Sign in with \(providerLabel) before sending prompts.",
            timestamp: timestamp,
            rawStatus: "auth_required"
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

@MainActor
final class AppController: ObservableObject {
    @Published var status: AppStatus?
    @Published var isLoading = false
    @Published var message: String?
    @Published var lastManualSend: ManualSendStatus?

    private let engine: EngineClient

    init(engine: EngineClient = EngineClient()) {
        self.engine = engine
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

    var loginCommand: String {
        activeProviderStatus?.loginCommand
            ?? (activeProvider == "codex" ? "codex login" : "claude auth login")
    }

    var isReady: Bool {
        activeProviderStatus?.available == true && activeProviderStatus?.authenticated == true
    }

    var readinessText: String {
        guard status != nil else {
            return "Checking setup"
        }
        let label = activeProviderLabel
        guard let providerStatus = activeProviderStatus else {
            return "No prompt provider configured"
        }
        if providerStatus.available != true {
            return "\(label) not installed"
        }
        if providerStatus.authenticated == true {
            return "\(label): signed in"
        }
        if providerStatus.authenticated == false {
            return "\(label) login required"
        }
        return "\(label) login unknown"
    }

    var providerStatusLines: [String] {
        guard status != nil else {
            return []
        }

        return providerStatusEntries.map { provider, providerStatus in
            let suffix = provider == activeProvider ? " (active)" : ""
            return "\(providerStatus.label ?? label(for: provider)): \(shortStatus(providerStatus))\(suffix)"
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

        if activeProviderStatus?.available != true || activeProviderStatus?.authenticated != true {
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
            "\(activeProviderLabel) status idle"
        case .running:
            "\(activeProviderLabel) status running"
        case .success:
            "\(activeProviderLabel) status last run succeeded"
        case .warning:
            "\(activeProviderLabel) status needs attention"
        case .failure:
            "\(activeProviderLabel) status last run failed"
        }
    }

    func refresh() async {
        await runTask {
            status = try await engine.status()
        }
    }

    func installActiveProvider() async {
        await runTask {
            status = try await engine.setup(install: true, provider: activeProvider)
            message = isReady ? "\(activeProviderLabel) is ready." : "\(activeProviderLabel) setup is incomplete."
        }
    }

    func startNow(cwd: String? = nil) async {
        if activeProviderStatus?.available == true && activeProviderStatus?.authenticated == false {
            let sendStatus = ManualSendStatus.loginRequired(providerLabel: activeProviderLabel)
            lastManualSend = sendStatus
            message = sendStatus.title
            return
        }
        let provider = activeProvider
        lastManualSend = .sending(providerLabel: activeProviderLabel)
        await runTask(onError: { [weak self] error in
            let status = ManualSendStatus.failed(error.localizedDescription)
            self?.lastManualSend = status
            self?.message = status.title
        }) {
            let targetFolder = cwd ?? defaultFolder
            try ensureDefaultFolderIfNeeded(targetFolder)
            let response = try await engine.startNow(cwd: targetFolder, provider: provider)
            let sendStatus = ManualSendStatus.finished(response: response)
            lastManualSend = sendStatus
            message = sendStatus.title
            do {
                status = try await engine.status()
            } catch {
                message = "\(sendStatus.title). Could not refresh status: \(error.localizedDescription)"
            }
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

    private var providerStatusEntries: [(String, ProviderStatus)] {
        let orderedProviders = ["codex", "claude"]
        if let providers = status?.providers {
            return orderedProviders.compactMap { provider in
                guard let status = providers[provider] else {
                    return nil
                }
                return (provider, status)
            }
        }

        var entries: [(String, ProviderStatus)] = []
        if let codex = status?.codex {
            entries.append(("codex", codex))
        }
        if let claude = status?.claude {
            entries.append(("claude", claude))
        }
        return entries
    }

    private func label(for provider: String) -> String {
        provider == "codex" ? "Codex" : "Claude Code"
    }

    private func shortStatus(_ status: ProviderStatus) -> String {
        if status.available != true {
            return "not installed"
        }
        if status.authenticated == true {
            return "signed in"
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
