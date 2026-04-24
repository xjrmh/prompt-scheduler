// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "PromptSchedulerMac",
    platforms: [.macOS(.v14)],
    products: [
        .library(name: "PromptSchedulerShared", targets: ["PromptSchedulerShared"]),
        .executable(name: "PromptSchedulerUI", targets: ["PromptSchedulerUI"])
    ],
    targets: [
        .target(name: "PromptSchedulerShared"),
        .executableTarget(
            name: "PromptSchedulerUI",
            dependencies: ["PromptSchedulerShared"],
            resources: [
                .copy("Resources/AppLogo.png"),
                .copy("Resources/AppIcon.icns")
            ]
        ),
        .testTarget(
            name: "PromptSchedulerSharedTests",
            dependencies: ["PromptSchedulerShared"]
        )
    ]
)
