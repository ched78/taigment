// swift-tools-version: 6.0
import PackageDescription
let package = Package(
    name: "PonyKit",
    platforms: [.iOS("26.0"), .macOS("26.0")],
    products: [
        .library(name: "PonyCore", targets: ["PonyCore"]),
        .library(name: "PonyKit", targets: ["PonyKit"]),
    ],
    targets: [
        .target(name: "PonyCore", path: "Sources/PonyCore"),
        .target(name: "PonyKit", dependencies: ["PonyCore"], path: "Sources/PonyKit",
                resources: [.copy("Resources")]),
        .testTarget(name: "PonyCoreTests", dependencies: ["PonyCore"], path: "Tests/PonyCoreTests"),
    ],
    swiftLanguageModes: [.v5]
)
