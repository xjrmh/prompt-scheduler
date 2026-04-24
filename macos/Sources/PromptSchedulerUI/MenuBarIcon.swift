import AppKit

enum MenuBarIcon {
    private static let canvasSize: CGFloat = 128
    private static let renderedSize: CGFloat = 20
    private static let verticalArtworkOffset: CGFloat = -canvasSize * 0.05

    static func image(for state: MenuBarIconState) -> NSImage {
        let image = NSImage(size: NSSize(width: canvasSize, height: canvasSize))
        image.lockFocus()
        NSGraphicsContext.current?.imageInterpolation = .high

        drawPromptSchedulerMark()
        drawStatusBadge(state)

        image.unlockFocus()
        image.isTemplate = true
        image.size = NSSize(width: renderedSize, height: renderedSize)
        return image
    }

    private static func drawPromptSchedulerMark() {
        let frame = NSRect(
            x: canvasSize * 0.16,
            y: canvasSize * 0.27 + verticalArtworkOffset,
            width: canvasSize * 0.58,
            height: canvasSize * 0.54
        )
        let panel = NSBezierPath(
            roundedRect: frame,
            xRadius: canvasSize * 0.08,
            yRadius: canvasSize * 0.08
        )
        panel.lineWidth = canvasSize * 0.07
        NSColor.black.setStroke()
        panel.stroke()

        let header = NSBezierPath()
        header.lineCapStyle = .round
        header.lineWidth = canvasSize * 0.06
        header.move(to: NSPoint(x: frame.minX + frame.width * 0.18, y: frame.maxY - frame.height * 0.27))
        header.line(to: NSPoint(x: frame.maxX - frame.width * 0.18, y: frame.maxY - frame.height * 0.27))
        header.stroke()

        let prompt = NSBezierPath()
        prompt.lineCapStyle = .round
        prompt.lineJoinStyle = .round
        prompt.lineWidth = canvasSize * 0.065
        prompt.move(to: NSPoint(x: frame.minX + frame.width * 0.22, y: frame.minY + frame.height * 0.34))
        prompt.line(to: NSPoint(x: frame.minX + frame.width * 0.34, y: frame.minY + frame.height * 0.45))
        prompt.line(to: NSPoint(x: frame.minX + frame.width * 0.22, y: frame.minY + frame.height * 0.56))
        prompt.move(to: NSPoint(x: frame.minX + frame.width * 0.45, y: frame.minY + frame.height * 0.34))
        prompt.line(to: NSPoint(x: frame.minX + frame.width * 0.64, y: frame.minY + frame.height * 0.34))
        prompt.stroke()

        let binding = NSBezierPath()
        binding.lineCapStyle = .round
        binding.lineWidth = canvasSize * 0.07
        binding.move(to: NSPoint(x: frame.minX + frame.width * 0.28, y: frame.maxY + canvasSize * 0.04))
        binding.line(to: NSPoint(x: frame.minX + frame.width * 0.28, y: frame.maxY - canvasSize * 0.08))
        binding.move(to: NSPoint(x: frame.minX + frame.width * 0.56, y: frame.maxY + canvasSize * 0.04))
        binding.line(to: NSPoint(x: frame.minX + frame.width * 0.56, y: frame.maxY - canvasSize * 0.08))
        binding.stroke()
    }

    private static func drawStatusBadge(_ state: MenuBarIconState) {
        let center = NSPoint(x: canvasSize * 0.69, y: canvasSize * 0.34 + verticalArtworkOffset)
        let cutoutRadius = canvasSize * 0.25
        let badgeRadius = canvasSize * 0.18

        clear(
            NSBezierPath(ovalIn: NSRect(
                x: center.x - cutoutRadius,
                y: center.y - cutoutRadius,
                width: cutoutRadius * 2,
                height: cutoutRadius * 2
            ))
        )

        switch state {
        case .idle:
            drawClockBadge(center: center, radius: badgeRadius)
        case .running:
            drawRunningBadge(center: center, radius: badgeRadius)
        case .success:
            drawSuccessBadge(center: center, radius: badgeRadius)
        case .warning:
            drawWarningBadge(center: center, radius: badgeRadius)
        case .failure:
            drawFailureBadge(center: center, radius: badgeRadius)
        }
    }

    private static func drawClockBadge(center: NSPoint, radius: CGFloat) {
        let clock = NSBezierPath(ovalIn: NSRect(
            x: center.x - radius,
            y: center.y - radius,
            width: radius * 2,
            height: radius * 2
        ))
        clock.lineWidth = canvasSize * 0.058
        NSColor.black.setStroke()
        clock.stroke()

        let hands = NSBezierPath()
        hands.lineCapStyle = .round
        hands.lineJoinStyle = .round
        hands.lineWidth = canvasSize * 0.05
        hands.move(to: center)
        hands.line(to: NSPoint(x: center.x, y: center.y + radius * 0.52))
        hands.move(to: center)
        hands.line(to: NSPoint(x: center.x + radius * 0.48, y: center.y - radius * 0.18))
        hands.stroke()
    }

    private static func drawRunningBadge(center: NSPoint, radius: CGFloat) {
        let ring = NSBezierPath()
        ring.lineCapStyle = .round
        ring.lineWidth = canvasSize * 0.06
        ring.appendArc(
            withCenter: center,
            radius: radius * 0.82,
            startAngle: 35,
            endAngle: 325
        )
        NSColor.black.setStroke()
        ring.stroke()

        let arrow = NSBezierPath()
        arrow.move(to: NSPoint(x: center.x + radius * 0.88, y: center.y + radius * 0.52))
        arrow.line(to: NSPoint(x: center.x + radius * 0.36, y: center.y + radius * 0.50))
        arrow.line(to: NSPoint(x: center.x + radius * 0.70, y: center.y + radius * 0.12))
        arrow.close()
        NSColor.black.setFill()
        arrow.fill()
    }

    private static func drawSuccessBadge(center: NSPoint, radius: CGFloat) {
        drawFilledCircle(center: center, radius: radius)

        let check = NSBezierPath()
        check.lineCapStyle = .round
        check.lineJoinStyle = .round
        check.lineWidth = canvasSize * 0.062
        check.move(to: NSPoint(x: center.x - radius * 0.46, y: center.y - radius * 0.02))
        check.line(to: NSPoint(x: center.x - radius * 0.15, y: center.y - radius * 0.34))
        check.line(to: NSPoint(x: center.x + radius * 0.50, y: center.y + radius * 0.36))
        clearStroke(check)
    }

    private static func drawWarningBadge(center: NSPoint, radius: CGFloat) {
        let triangle = NSBezierPath()
        triangle.move(to: NSPoint(x: center.x, y: center.y + radius * 1.05))
        triangle.line(to: NSPoint(x: center.x - radius * 1.05, y: center.y - radius * 0.85))
        triangle.line(to: NSPoint(x: center.x + radius * 1.05, y: center.y - radius * 0.85))
        triangle.close()
        NSColor.black.setFill()
        triangle.fill()

        let mark = NSBezierPath()
        mark.lineCapStyle = .round
        mark.lineWidth = canvasSize * 0.058
        mark.move(to: NSPoint(x: center.x, y: center.y + radius * 0.44))
        mark.line(to: NSPoint(x: center.x, y: center.y - radius * 0.22))
        clearStroke(mark)
        clear(NSBezierPath(ovalIn: NSRect(
            x: center.x - radius * 0.12,
            y: center.y - radius * 0.58,
            width: radius * 0.24,
            height: radius * 0.24
        )))
    }

    private static func drawFailureBadge(center: NSPoint, radius: CGFloat) {
        drawFilledCircle(center: center, radius: radius)

        let cross = NSBezierPath()
        cross.lineCapStyle = .round
        cross.lineWidth = canvasSize * 0.064
        cross.move(to: NSPoint(x: center.x - radius * 0.38, y: center.y - radius * 0.38))
        cross.line(to: NSPoint(x: center.x + radius * 0.38, y: center.y + radius * 0.38))
        cross.move(to: NSPoint(x: center.x - radius * 0.38, y: center.y + radius * 0.38))
        cross.line(to: NSPoint(x: center.x + radius * 0.38, y: center.y - radius * 0.38))
        clearStroke(cross)
    }

    private static func drawFilledCircle(center: NSPoint, radius: CGFloat) {
        let circle = NSBezierPath(ovalIn: NSRect(
            x: center.x - radius,
            y: center.y - radius,
            width: radius * 2,
            height: radius * 2
        ))
        NSColor.black.setFill()
        circle.fill()
    }

    private static func clear(_ path: NSBezierPath) {
        let context = NSGraphicsContext.current
        let previous = context?.compositingOperation
        context?.compositingOperation = .clear
        path.fill()
        context?.compositingOperation = previous ?? .sourceOver
    }

    private static func clearStroke(_ path: NSBezierPath) {
        let context = NSGraphicsContext.current
        let previous = context?.compositingOperation
        context?.compositingOperation = .clear
        path.stroke()
        context?.compositingOperation = previous ?? .sourceOver
    }
}
