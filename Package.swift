// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "pmsetly",
    platforms: [.macOS(.v13)],
    targets: [
        .executableTarget(name: "pmsetly"),
        .testTarget(name: "pmsetlyTests", dependencies: ["pmsetly"]),
    ]
)
