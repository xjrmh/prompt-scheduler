// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "ClaudeSessionSchedulerMac",
    platforms: [.macOS(.v14)],
    products: [
        .library(name: "CSSShared", targets: ["CSSShared"]),
        .executable(name: "ClaudeSessionSchedulerUI", targets: ["ClaudeSessionSchedulerUI"])
    ],
    targets: [
        .target(name: "CSSShared"),
        .executableTarget(
            name: "ClaudeSessionSchedulerUI",
            dependencies: ["CSSShared"],
            resources: [
                .copy("Resources/AppLogo.png"),
                .copy("Resources/AppIcon.icns")
            ]
        ),
        .testTarget(
            name: "CSSSharedTests",
            dependencies: ["CSSShared"]
        )
    ]
)
