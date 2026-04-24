import XCTest
@testable import CSSShared

final class EngineClientTests: XCTestCase {
    func testDecodesStatusJSON() throws {
        let data = """
        {
          "ok": true,
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
              "schedule": {"type": "daily", "time": "09:00"},
              "schedule_label": "daily at 09:00",
              "status": "scheduled",
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
        XCTAssertTrue(status.claude.available)
        XCTAssertTrue(status.claude.authenticated == true)
        XCTAssertEqual(status.claude.authMethod, "claude.ai")
        XCTAssertEqual(status.reset.nextEstimatedResetAt, "2026-04-25T10:00:00-04:00")
        XCTAssertEqual(status.reset.rateLimits?.fiveHour?.usedPercentage, 41.8)
        XCTAssertEqual(status.reset.rateLimits?.fiveHour?.resetsAtIso, "2026-04-25T09:00:00-04:00")
        XCTAssertEqual(status.jobs.first?.scheduleLabel, "daily at 09:00")
        XCTAssertEqual(status.jobs.first?.lastClaudeResponseSummary, "OK")
        XCTAssertEqual(status.paths.launchAgents, "/tmp/agents")
    }

    func testBuildsStartNowCommand() async throws {
        let client = EngineClient(
            commandResolver: {
                EngineCommand(executable: "/usr/local/bin/claude-session-scheduler")
            },
            runProcess: { command in
                XCTAssertEqual(command.executable, "/usr/local/bin/claude-session-scheduler")
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

    func testDefaultCommandUsesEnvironmentOverride() {
        let client = EngineClient(
            commandResolver: {
                EngineCommand(executable: "/tmp/css")
            },
            runProcess: { _ in ProcessResult(exitCode: 0, stdout: Data()) }
        )

        let command = client.makeCommand(arguments: ["status", "--json"])

        XCTAssertEqual(command.executable, "/tmp/css")
        XCTAssertEqual(command.arguments, ["status", "--json"])
    }

    func testDefaultProjectFolderName() {
        XCTAssertEqual(SchedulerDefaults.projectFolderName, "Claude Scheduler Project")
        XCTAssertTrue(SchedulerDefaults.projectFolderPath.hasSuffix("/Claude Scheduler Project"))
    }
}
