import CSSShared
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

    static func sending(timestamp: Date = Date()) -> ManualSendStatus {
        ManualSendStatus(
            tone: .pending,
            title: "Sending prompt",
            detail: "Starting Claude with the OK prompt.",
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

        let mapped = map(status: result.status, exitCode: result.exitCode)
        let detail = cleanMessage(result.message) ?? mapped.detail
        return ManualSendStatus(
            tone: mapped.tone,
            title: mapped.title,
            detail: detail,
            timestamp: timestamp,
            rawStatus: result.status,
            exitCode: result.exitCode,
            logPath: result.logPath,
            responseText: cleanMessage(result.claudeResponseSummary)
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

    static func loginRequired(timestamp: Date = Date()) -> ManualSendStatus {
        ManualSendStatus(
            tone: .failure,
            title: "Claude login required",
            detail: "Sign in with Claude Code before sending prompts.",
            timestamp: timestamp,
            rawStatus: "auth_required"
        )
    }

    private static func map(status: String, exitCode: Int) -> (tone: Tone, title: String, detail: String) {
        switch status {
        case "success":
            return (.success, "Send succeeded", "Claude accepted the prompt.")
        case "auth_required":
            return (.failure, "Claude login required", "Sign in with Claude Code before sending prompts.")
        case "usage_limit":
            return (.warning, "Usage limit reached", "Claude reported a usage limit. Check the log for reset details.")
        case "overlap_skipped":
            return (.warning, "Send skipped", "Another Claude send is already running.")
        case "skipped":
            return (.skipped, "Send skipped", "Claude did not run for this request.")
        case "failed":
            return (.failure, "Send failed", "Claude exited with code \(exitCode).")
        case "timed_out":
            return (.failure, "Send timed out", "Claude did not finish within the timeout.")
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

    var isReady: Bool {
        status?.claude.available == true && status?.claude.authenticated == true
    }

    var readinessText: String {
        guard let status else {
            return "Checking setup"
        }
        if status.claude.available != true {
            return "Claude Code not installed"
        }
        if status.claude.authenticated == true {
            return "Claude CLI: signed in"
        }
        if status.claude.authenticated == false {
            return "Claude login required"
        }
        return "Claude login unknown"
    }

    var defaultFolder: String {
        SchedulerDefaults.projectFolderPath
    }

    var menuBarIconState: MenuBarIconState {
        if isLoading || lastManualSend?.tone == .pending || hasRunningJob {
            return .running
        }

        guard let status else {
            return .running
        }

        if status.claude.available != true || status.claude.authenticated != true {
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
            "Claude status idle"
        case .running:
            "Claude status running"
        case .success:
            "Claude status last run succeeded"
        case .warning:
            "Claude status needs attention"
        case .failure:
            "Claude status last run failed"
        }
    }

    func refresh() async {
        await runTask {
            status = try await engine.status()
        }
    }

    func installClaudeCode() async {
        await runTask {
            status = try await engine.setup(install: true)
            message = isReady ? "Claude Code is ready." : "Claude setup is incomplete."
        }
    }

    func startNow(cwd: String? = nil) async {
        if status?.claude.available == true && status?.claude.authenticated == false {
            let sendStatus = ManualSendStatus.loginRequired()
            lastManualSend = sendStatus
            message = sendStatus.title
            return
        }
        lastManualSend = .sending()
        await runTask(onError: { [weak self] error in
            let status = ManualSendStatus.failed(error.localizedDescription)
            self?.lastManualSend = status
            self?.message = status.title
        }) {
            let targetFolder = cwd ?? defaultFolder
            try ensureDefaultFolderIfNeeded(targetFolder)
            let response = try await engine.startNow(cwd: targetFolder)
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
