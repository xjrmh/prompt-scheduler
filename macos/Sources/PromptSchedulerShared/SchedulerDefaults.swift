import Foundation

public enum SchedulerDefaults {
    public static let projectFolderName = "Prompt Scheduler Project"

    public static var projectFolderPath: String {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(projectFolderName, isDirectory: true)
            .path
    }

    public static func ensureProjectFolder() throws -> String {
        let path = projectFolderPath
        try FileManager.default.createDirectory(
            atPath: path,
            withIntermediateDirectories: true
        )
        return path
    }
}
