import XCTest
@testable import PromptSchedulerShared

final class EngineClientTests: XCTestCase {
    func testDecodesStatusJSON() throws {
        let data = """
        {
          "ok": true,
          "active_provider": "codex",
          "active_provider_label": "Codex",
          "providers": {
            "claude": {
              "available": true,
              "path": "/usr/local/bin/claude",
              "authenticated": true,
              "auth_method": "claude.ai",
              "label": "Claude Code"
            },
            "codex": {
              "available": true,
              "path": "/usr/local/bin/codex",
              "authenticated": true,
              "auth_method": "ChatGPT",
              "label": "Codex"
            }
          },
          "claude": {
            "available": true,
            "path": "/usr/local/bin/claude",
            "authenticated": true,
            "auth_method": "claude.ai"
          },
          "reset": {
            "next_reset_at": "2026-04-25T09:00:00-04:00",
            "next_estimated_reset_at": "2026-04-25T10:00:00-04:00",
            "last_estimated_window_started_at": "2026-04-25T05:00:00-04:00",
            "rate_limits": {
              "five_hour": {
                "used_percentage": 41.8,
                "resets_at_iso": "2026-04-25T09:00:00-04:00"
              }
            },
            "rate_limits_updated_at": "2026-04-25T06:00:00-04:00",
            "reset_source": "claude-code-statusline"
          },
          "jobs": [
            {
              "id": "job-1234",
              "name": "Morning",
              "cwd": "/tmp/project",
              "provider": "codex",
              "provider_label": "Codex",
              "schedule": {"type": "daily", "time": "09:00"},
              "schedule_label": "daily at 09:00",
              "status": "scheduled",
              "last_response_summary": "OK",
              "last_claude_response_summary": "OK",
              "run_count": 0
            }
          ],
          "paths": {
            "state": "/tmp/state",
            "logs": "/tmp/state/logs",
            "launch_agents": "/tmp/agents"
          },
          "checks": {
            "platform_macos": true,
            "launchctl": true,
            "data_dir": true,
            "launch_agents_dir": true
          }
        }
        """.data(using: .utf8)!

        let status = try JSONDecoder().decode(AppStatus.self, from: data)

        XCTAssertTrue(status.ok)
        XCTAssertEqual(status.activeProvider, "codex")
        XCTAssertEqual(status.activeProviderLabel, "Codex")
        XCTAssertTrue(status.providers?["codex"]?.available == true)
        XCTAssertTrue(status.claude.available)
        XCTAssertTrue(status.claude.authenticated == true)
        XCTAssertEqual(status.claude.authMethod, "claude.ai")
        XCTAssertEqual(status.reset.nextEstimatedResetAt, "2026-04-25T10:00:00-04:00")
        XCTAssertEqual(status.reset.rateLimits?.fiveHour?.usedPercentage, 41.8)
        XCTAssertEqual(status.reset.rateLimits?.fiveHour?.resetsAtIso, "2026-04-25T09:00:00-04:00")
        XCTAssertEqual(status.jobs.first?.scheduleLabel, "daily at 09:00")
        XCTAssertEqual(status.jobs.first?.provider, "codex")
        XCTAssertEqual(status.jobs.first?.lastResponseSummary, "OK")
        XCTAssertEqual(status.jobs.first?.lastClaudeResponseSummary, "OK")
        XCTAssertEqual(status.paths.launchAgents, "/tmp/agents")
    }

    func testBuildsStartNowCommand() async throws {
        let client = EngineClient(
            commandResolver: {
                EngineCommand(executable: "/usr/local/bin/prompt-scheduler")
            },
            runProcess: { command in
                XCTAssertEqual(command.executable, "/usr/local/bin/prompt-scheduler")
                XCTAssertEqual(
                    command.arguments,
                    [
                        "start-now",
                        "--cwd", "/tmp/project",
                        "--json"
                    ]
                )
                return ProcessResult(
                    exitCode: 0,
                    stdout: #"{"ok":true,"result":{"status":"success","exit_code":0,"log_path":"/tmp/run.log","message":"done","claude_response_summary":"OK"}}"#.data(using: .utf8)!
                )
            }
        )

        let response = try await client.startNow(cwd: "/tmp/project")

        XCTAssertTrue(response.ok)
        XCTAssertEqual(response.result?.status, "success")
        XCTAssertEqual(response.result?.claudeResponseSummary, "OK")
    }

    func testBuildsStartNowCommandWithProvider() async throws {
        let client = EngineClient(
            commandResolver: {
                EngineCommand(executable: "/usr/local/bin/prompt-scheduler")
            },
            runProcess: { command in
                XCTAssertEqual(
                    command.arguments,
                    [
                        "start-now",
                        "--cwd", "/tmp/project",
                        "--provider", "codex",
                        "--json"
                    ]
                )
                return ProcessResult(
                    exitCode: 0,
                    stdout: #"{"ok":true,"result":{"status":"success","exit_code":0,"log_path":"/tmp/run.log","provider":"codex","provider_label":"Codex","response_summary":"OK"}}"#.data(using: .utf8)!
                )
            }
        )

        let response = try await client.startNow(cwd: "/tmp/project", provider: "codex")

        XCTAssertTrue(response.ok)
        XCTAssertEqual(response.result?.provider, "codex")
        XCTAssertEqual(response.result?.providerLabel, "Codex")
        XCTAssertEqual(response.result?.responseSummary, "OK")
    }

    func testBuildsStartAtResetCommandWithProvider() async throws {
        let client = EngineClient(
            commandResolver: {
                EngineCommand(executable: "/usr/local/bin/prompt-scheduler")
            },
            runProcess: { command in
                XCTAssertEqual(
                    command.arguments,
                    [
                        "start-at-reset",
                        "--cwd", "/tmp/project",
                        "--buffer-minutes", "2",
                        "--provider", "both",
                        "--json"
                    ]
                )
                return ProcessResult(
                    exitCode: 0,
                    stdout: #"{"ok":true,"job":{"id":"job-1234","name":"start-window-at-reset","cwd":"/tmp/project","provider":"both","provider_label":"Codex + Claude Code","schedule_label":"once at 2026-04-25 09:02","status":"scheduled"}}"#.data(using: .utf8)!
                )
            }
        )

        let response = try await client.startAtReset(cwd: "/tmp/project", provider: "both")

        XCTAssertTrue(response.ok)
        XCTAssertEqual(response.job?.provider, "both")
        XCTAssertEqual(response.job?.scheduleLabel, "once at 2026-04-25 09:02")
    }

    func testBuildsStartWakeLoopCommand() async throws {
        let client = EngineClient(
            commandResolver: {
                EngineCommand(executable: "/usr/local/bin/prompt-scheduler")
            },
            runProcess: { command in
                XCTAssertEqual(
                    command.arguments,
                    [
                        "wake-loop", "start",
                        "--cwd", "/tmp/project",
                        "--every", "30m",
                        "--prompt", "Reply with exactly OK.",
                        "--provider", "both",
                        "--json"
                    ]
                )
                return ProcessResult(
                    exitCode: 0,
                    stdout: #"{"ok":true,"job":{"id":"wake-loop-1234","name":"wake-loop","cwd":"/tmp/project","provider":"both","provider_label":"Codex + Claude Code","schedule_label":"every 30m","status":"scheduled"}}"#.data(using: .utf8)!
                )
            }
        )

        let response = try await client.startWakeLoop(
            cwd: "/tmp/project",
            provider: "both",
            every: "30m",
            prompt: "Reply with exactly OK."
        )

        XCTAssertTrue(response.ok)
        XCTAssertEqual(response.job?.name, "wake-loop")
        XCTAssertEqual(response.job?.scheduleLabel, "every 30m")
    }

    func testBuildsStopWakeLoopCommand() async throws {
        let client = EngineClient(
            commandResolver: {
                EngineCommand(executable: "/usr/local/bin/prompt-scheduler")
            },
            runProcess: { command in
                XCTAssertEqual(
                    command.arguments,
                    ["wake-loop", "stop", "--json"]
                )
                return ProcessResult(
                    exitCode: 0,
                    stdout: #"{"ok":true,"removed":{"id":"wake-loop-1234","name":"wake-loop","status":"scheduled"}}"#.data(using: .utf8)!
                )
            }
        )

        let response = try await client.stopWakeLoop()

        XCTAssertTrue(response.ok)
        XCTAssertEqual(response.removed?.name, "wake-loop")
    }

    func testBuildsAddScheduleCommand() async throws {
        let client = EngineClient(
            commandResolver: {
                EngineCommand(executable: "/usr/local/bin/prompt-scheduler")
            },
            runProcess: { command in
                XCTAssertEqual(
                    command.arguments,
                    [
                        "add",
                        "--provider", "both",
                        "--name", "Morning",
                        "--cwd", "/tmp/project",
                        "--daily", "09:00",
                        "--prompt", "hello",
                        "--json"
                    ]
                )
                return ProcessResult(
                    exitCode: 0,
                    stdout: #"{"ok":true,"job":{"id":"job-1234","name":"Morning","cwd":"/tmp/project","provider":"both","provider_label":"Codex + Claude Code","schedule_label":"daily at 09:00","status":"scheduled"}}"#.data(using: .utf8)!
                )
            }
        )

        let response = try await client.addSchedule(
            name: "Morning",
            cwd: "/tmp/project",
            prompt: "hello",
            provider: "both",
            daily: "09:00"
        )

        XCTAssertTrue(response.ok)
        XCTAssertEqual(response.job?.provider, "both")
        XCTAssertEqual(response.job?.scheduleLabel, "daily at 09:00")
    }

    func testDefaultCommandUsesEnvironmentOverride() {
        let client = EngineClient(
            commandResolver: {
                EngineCommand(executable: "/tmp/prompt-scheduler")
            },
            runProcess: { _ in ProcessResult(exitCode: 0, stdout: Data()) }
        )

        let command = client.makeCommand(arguments: ["status", "--json"])

        XCTAssertEqual(command.executable, "/tmp/prompt-scheduler")
        XCTAssertEqual(command.arguments, ["status", "--json"])
    }

    func testDefaultProjectFolderName() {
        XCTAssertEqual(SchedulerDefaults.projectFolderName, "Prompt Scheduler Project")
        XCTAssertTrue(SchedulerDefaults.projectFolderPath.hasSuffix("/Prompt Scheduler Project"))
    }
}
