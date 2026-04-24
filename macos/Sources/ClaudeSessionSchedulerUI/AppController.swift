import CSSShared
import Foundation

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
                detail: response.error ?? "The scheduler did not return run details.",
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
            logPath: result.logPath
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
                return (.success, "Send finished", "Scheduler status: \(status).")
            }
            return (.failure, "Send failed", "Scheduler status: \(status). Exit code \(exitCode).")
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
    @Published var showAddSchedule = false

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
            return "Claude Code is ready"
        }
        if status.claude.authenticated == false {
            return "Claude login required"
        }
        return "Claude login unknown"
    }

    var defaultFolder: String {
        SchedulerDefaults.projectFolderPath
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

    func addSchedule(_ input: ScheduleInput) async {
        await runTask {
            try ensureDefaultFolderIfNeeded(input.cwd)
            let response = try await engine.addSchedule(input)
            if response.ok {
                message = "Schedule saved."
                status = try await engine.status()
            } else {
                message = response.error ?? "Could not save schedule."
            }
        }
    }

    func removeJob(id: String) async {
        await runTask {
            _ = try await engine.removeJob(id: id)
            message = "Schedule removed."
            status = try await engine.status()
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
}
