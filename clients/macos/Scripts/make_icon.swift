#!/usr/bin/env swift
// Renders AppIcon.icns from code, so the repo carries no binary art.
// Run via `make icon`; Scripts/package_app.sh calls it when the .icns is missing.
//
// Draws into an NSBitmapImageRep context rather than using NSImage.lockFocus —
// lockFocus needs a window-server context that a headless script doesn't have,
// and fails at tiffRepresentation.

import AppKit

let iconset = URL(fileURLWithPath: "build/AppIcon.iconset")
try? FileManager.default.removeItem(at: iconset)
try? FileManager.default.createDirectory(at: iconset, withIntermediateDirectories: true)

/// pixel size -> the iconset slots it fills
let plan: [(pixels: Int, names: [String])] = [
    (16, ["icon_16x16.png"]),
    (32, ["icon_16x16@2x.png", "icon_32x32.png"]),
    (64, ["icon_32x32@2x.png"]),
    (128, ["icon_128x128.png"]),
    (256, ["icon_128x128@2x.png", "icon_256x256.png"]),
    (512, ["icon_256x256@2x.png", "icon_512x512.png"]),
    (1024, ["icon_512x512@2x.png"]),
]

func render(_ pixels: Int) -> Data? {
    guard let rep = NSBitmapImageRep(
        bitmapDataPlanes: nil, pixelsWide: pixels, pixelsHigh: pixels,
        bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
        colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0),
          let context = NSGraphicsContext(bitmapImageRep: rep)
    else { return nil }

    rep.size = NSSize(width: pixels, height: pixels)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = context

    let side = CGFloat(pixels)
    let inset = side * 0.06
    let rect = NSRect(x: inset, y: inset, width: side - inset * 2, height: side - inset * 2)
    let radius = rect.width * 0.225
    let squircle = NSBezierPath(roundedRect: rect, xRadius: radius, yRadius: radius)

    NSGradient(colors: [
        NSColor(srgbRed: 0.36, green: 0.34, blue: 0.92, alpha: 1),
        NSColor(srgbRed: 0.55, green: 0.28, blue: 0.86, alpha: 1),
    ])?.draw(in: squircle, angle: -90)

    let configuration = NSImage.SymbolConfiguration(pointSize: side * 0.44, weight: .semibold)
        .applying(NSImage.SymbolConfiguration(paletteColors: [.white]))
    if let bell = NSImage(systemSymbolName: "bell.fill", accessibilityDescription: nil)?
        .withSymbolConfiguration(configuration) {
        bell.isTemplate = false
        let size = bell.size
        bell.draw(in: NSRect(x: (side - size.width) / 2,
                             y: (side - size.height) / 2,
                             width: size.width, height: size.height))
    }

    NSGraphicsContext.restoreGraphicsState()
    return rep.representation(using: .png, properties: [:])
}

for step in plan {
    guard let data = render(step.pixels) else {
        FileHandle.standardError.write(Data("failed to render \(step.pixels)px\n".utf8))
        exit(1)
    }
    for name in step.names {
        try data.write(to: iconset.appendingPathComponent(name))
    }
}

let iconutil = Process()
iconutil.executableURL = URL(fileURLWithPath: "/usr/bin/iconutil")
iconutil.arguments = ["-c", "icns", iconset.path, "-o", "build/AppIcon.icns"]
try iconutil.run()
iconutil.waitUntilExit()
guard iconutil.terminationStatus == 0 else {
    FileHandle.standardError.write(Data("iconutil failed\n".utf8))
    exit(1)
}
print("wrote build/AppIcon.icns")
