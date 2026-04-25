import Foundation

public struct EngineCommand: Equatable, Sendable {
    public var executable: String
    public var arguments: [String]
    public var environment: [String: String]

    public init(executable: String, arguments: [String] = [], environment: [String: String] = [:]) {
        self.executable = executable
        self.arguments = arguments
        self.environment = environment
    }
}

public enum EngineClientError: Error, LocalizedError, Equatable {
    case commandFailed(String)
    case invalidOutput(String)

    public var errorDescription: String? {
        switch self {
        case .commandFailed(let message):
            message
        case .invalidOutput(let message):
            message
        }
    }
}

public final class EngineClient: Sendable {
    public typealias ProcessRunner = @Sendable (EngineCommand) async throws -> ProcessResult

    private let commandResolver: @Sendable () -> EngineCommand
    private let runProcess: ProcessRunner
    private let decoder = JSONDecoder()

    public init(
        commandResolver: @escaping @Sendable () -> EngineCommand = EngineClient.defaultCommand,
        runProcess: @escaping ProcessRunner = EngineClient.run
    ) {
        self.commandResolver = commandResolver
        self.runProcess = runProcess
    }

    public func status() async throws -> AppStatus {
        try await runJSON(["status", "--json"], as: AppStatus.self)
    }

    public func setup(install: Bool = false, provider: String? = nil) async throws -> AppStatus {
        var args = ["setup", "--json"]
        if let provider, !provider.isEmpty {
            args.append(contentsOf: ["--provider", provider])
        }
        if install {
            args.append("--yes")
        } else {
            args.append("--no-install")
        }
        return try await runJSON(args, as: AppStatus.self)
    }

    public func startNow(cwd: String, provider: String? = nil) async throws -> RunResponse {
        var args = ["start-now", "--cwd", cwd]
        if let provider, !provider.isEmpty {
            args.append(contentsOf: ["--provider", provider])
        }
        args.append("--json")
        return try await runJSON(args, as: RunResponse.self)
    }

    public func startAtReset(
        cwd: String,
        provider: String? = nil,
        bufferMinutes: Int = 2
    ) async throws -> ScheduleAddResponse {
        var args = [
            "start-at-reset",
            "--cwd", cwd,
            "--buffer-minutes", String(bufferMinutes)
        ]
        if let provider, !provider.isEmpty {
            args.append(contentsOf: ["--provider", provider])
        }
        args.append("--json")
        return try await runJSON(args, as: ScheduleAddResponse.self)
    }

    public func addSchedule(
        name: String,
        cwd: String,
        prompt: String,
        provider: String? = nil,
        daily: String? = nil,
        weekly: String? = nil
    ) async throws -> ScheduleAddResponse {
        var args = ["add"]
        if let provider, !provider.isEmpty {
            args.append(contentsOf: ["--provider", provider])
        }
        args.append(contentsOf: ["--name", name, "--cwd", cwd])
        if let daily, !daily.isEmpty {
            args.append(contentsOf: ["--daily", daily])
        } else if let weekly, !weekly.isEmpty {
            args.append(contentsOf: ["--weekly", weekly])
        }
        args.append(contentsOf: ["--prompt", prompt, "--json"])
        return try await runJSON(args, as: ScheduleAddResponse.self)
    }

    public func removeSchedule(jobID: String) async throws -> ScheduleRemoveResponse {
        return try await runJSON(["remove", jobID, "--json"], as: ScheduleRemoveResponse.self)
    }

    public func logs(jobID: String? = nil) async throws -> LogsResponse {
        var args = ["logs", "--json"]
        if let jobID {
            args = ["logs", jobID, "--json"]
        }
        return try await runJSON(args, as: LogsResponse.self)
    }

    public func makeCommand(arguments: [String]) -> EngineCommand {
        var command = commandResolver()
        command.arguments.append(contentsOf: arguments)
        return command
    }

    private func runJSON<T: Decodable>(_ arguments: [String], as type: T.Type) async throws -> T {
        let command = makeCommand(arguments: arguments)
        let result = try await runProcess(command)
        guard !result.stdout.isEmpty else {
            throw EngineClientError.invalidOutput("The CLI returned no JSON output.")
        }
        do {
            return try decoder.decode(T.self, from: result.stdout)
        } catch {
            let text = String(data: result.stdout, encoding: .utf8) ?? ""
            if result.exitCode != 0,
               let response = try? decoder.decode(ErrorResponse.self, from: result.stdout) {
                throw EngineClientError.commandFailed(response.error ?? "The CLI command failed.")
            }
            throw EngineClientError.invalidOutput(text)
        }
    }

    public static func defaultCommand() -> EngineCommand {
        let environment = ProcessInfo.processInfo.environment
        if let override = environment["PROMPT_SCHEDULER_BIN"], !override.isEmpty {
            return EngineCommand(executable: override)
        }

        let candidates = [
            "/opt/homebrew/bin/prompt-scheduler",
            "/usr/local/bin/prompt-scheduler",
            "\(NSHomeDirectory())/.local/bin/prompt-scheduler"
        ]
        for candidate in candidates where FileManager.default.isExecutableFile(atPath: candidate) {
            return EngineCommand(executable: candidate)
        }

        let sourceFile = URL(fileURLWithPath: #filePath)
        let repoRoot = sourceFile
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let srcPath = repoRoot.appendingPathComponent("src").path
        return EngineCommand(
            executable: "/usr/bin/env",
            arguments: ["python3", "-m", "prompt_scheduler"],
            environment: ["PYTHONPATH": srcPath]
        )
    }

    public static func run(command: EngineCommand) async throws -> ProcessResult {
        try await Task.detached(priority: .userInitiated) {
            let process = Process()
            process.executableURL = URL(fileURLWithPath: command.executable)
            process.arguments = command.arguments

            var environment = ProcessInfo.processInfo.environment
            command.environment.forEach { environment[$0.key] = $0.value }
            process.environment = environment

            let stdout = Pipe()
            let stderr = Pipe()
            process.standardOutput = stdout
            process.standardError = stderr

            try process.run()
            process.waitUntilExit()

            return ProcessResult(
                exitCode: Int(process.terminationStatus),
                stdout: stdout.fileHandleForReading.readDataToEndOfFile(),
                stderr: stderr.fileHandleForReading.readDataToEndOfFile()
            )
        }.value
    }
}

public struct ProcessResult: Sendable {
    public var exitCode: Int
    public var stdout: Data
    public var stderr: Data

    public init(exitCode: Int, stdout: Data, stderr: Data = Data()) {
        self.exitCode = exitCode
        self.stdout = stdout
        self.stderr = stderr
    }
}

private struct ErrorResponse: Decodable {
    var ok: Bool
    var error: String?
}
