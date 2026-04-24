import Foundation

public enum JSONValue: Codable, Equatable, Sendable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case object([String: JSONValue])
    case array([JSONValue])
    case null

    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? container.decode(Double.self) {
            self = .number(value)
        } else if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode([String: JSONValue].self) {
            self = .object(value)
        } else {
            self = .array(try container.decode([JSONValue].self))
        }
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let value):
            try container.encode(value)
        case .number(let value):
            try container.encode(value)
        case .bool(let value):
            try container.encode(value)
        case .object(let value):
            try container.encode(value)
        case .array(let value):
            try container.encode(value)
        case .null:
            try container.encodeNil()
        }
    }
}

public struct AppStatus: Codable, Equatable, Sendable {
    public var ok: Bool
    public var activeProvider: String?
    public var activeProviderLabel: String?
    public var providers: [String: ProviderStatus]?
    public var claude: ProviderStatus
    public var codex: ProviderStatus?
    public var reset: ResetStatus
    public var jobs: [ScheduleJob]
    public var paths: SchedulerPaths
    public var checks: SetupChecks?
    public var error: String?
    public var nextCommands: [String]?

    enum CodingKeys: String, CodingKey {
        case ok, providers, claude, codex, reset, jobs, paths, checks, error
        case activeProvider = "active_provider"
        case activeProviderLabel = "active_provider_label"
        case nextCommands = "next_commands"
    }
}

public typealias ClaudeStatus = ProviderStatus

public struct ProviderStatus: Codable, Equatable, Sendable {
    public var available: Bool
    public var path: String?
    public var authenticated: Bool?
    public var authMethod: String?
    public var authError: String?
    public var loginCommand: String?
    public var installCommand: String?
    public var label: String?

    enum CodingKeys: String, CodingKey {
        case available, path, authenticated
        case authMethod = "auth_method"
        case authError = "auth_error"
        case loginCommand = "login_command"
        case installCommand = "install_command"
        case label
    }
}

public struct ResetStatus: Codable, Equatable, Sendable {
    public var nextResetAt: String?
    public var nextEstimatedResetAt: String?
    public var lastEstimatedWindowStartedAt: String?
    public var rateLimits: RateLimits?
    public var rateLimitsUpdatedAt: String?
    public var resetSource: String?

    enum CodingKeys: String, CodingKey {
        case nextResetAt = "next_reset_at"
        case nextEstimatedResetAt = "next_estimated_reset_at"
        case lastEstimatedWindowStartedAt = "last_estimated_window_started_at"
        case rateLimits = "rate_limits"
        case rateLimitsUpdatedAt = "rate_limits_updated_at"
        case resetSource = "reset_source"
    }
}

public struct RateLimits: Codable, Equatable, Sendable {
    public var fiveHour: RateLimitWindow?
    public var sevenDay: RateLimitWindow?

    enum CodingKeys: String, CodingKey {
        case fiveHour = "five_hour"
        case sevenDay = "seven_day"
    }
}

public struct RateLimitWindow: Codable, Equatable, Sendable {
    public var usedPercentage: Double?
    public var resetsAtIso: String?

    enum CodingKeys: String, CodingKey {
        case usedPercentage = "used_percentage"
        case resetsAtIso = "resets_at_iso"
    }
}

public struct SchedulerPaths: Codable, Equatable, Sendable {
    public var state: String
    public var logs: String
    public var launchAgents: String

    enum CodingKeys: String, CodingKey {
        case state, logs
        case launchAgents = "launch_agents"
    }
}

public struct SetupChecks: Codable, Equatable, Sendable {
    public var platformMacos: Bool
    public var launchctl: Bool
    public var launchctlPath: String?
    public var dataDir: Bool
    public var launchAgentsDir: Bool

    enum CodingKeys: String, CodingKey {
        case platformMacos = "platform_macos"
        case launchctl
        case launchctlPath = "launchctl_path"
        case dataDir = "data_dir"
        case launchAgentsDir = "launch_agents_dir"
    }
}

public struct ScheduleJob: Codable, Equatable, Identifiable, Sendable {
    public var id: String
    public var name: String?
    public var cwd: String?
    public var provider: String?
    public var providerLabel: String?
    public var schedule: JSONValue?
    public var scheduleLabel: String?
    public var status: String?
    public var lastStatus: String?
    public var lastRunAt: String?
    public var lastLogPath: String?
    public var lastResponseSummary: String?
    public var lastClaudeResponseSummary: String?
    public var runCount: Int?

    enum CodingKeys: String, CodingKey {
        case id, name, cwd, provider, schedule, status
        case providerLabel = "provider_label"
        case scheduleLabel = "schedule_label"
        case lastStatus = "last_status"
        case lastRunAt = "last_run_at"
        case lastLogPath = "last_log_path"
        case lastResponseSummary = "last_response_summary"
        case lastClaudeResponseSummary = "last_claude_response_summary"
        case runCount = "run_count"
    }
}

public struct RunResponse: Codable, Equatable, Sendable {
    public var ok: Bool
    public var result: RunResult?
    public var error: String?
}

public struct RunResult: Codable, Equatable, Sendable {
    public var status: String
    public var exitCode: Int
    public var logPath: String
    public var provider: String?
    public var providerLabel: String?
    public var reset: JSONValue?
    public var message: String?
    public var responseSummary: String?
    public var claudeResponseSummary: String?

    enum CodingKeys: String, CodingKey {
        case status, provider, reset, message
        case exitCode = "exit_code"
        case logPath = "log_path"
        case providerLabel = "provider_label"
        case responseSummary = "response_summary"
        case claudeResponseSummary = "claude_response_summary"
    }
}

public struct LogsResponse: Codable, Equatable, Sendable {
    public var ok: Bool
    public var logs: [String]?
    public var log: LogContent?
    public var error: String?
}

public struct LogContent: Codable, Equatable, Sendable {
    public var path: String
    public var content: String
}
