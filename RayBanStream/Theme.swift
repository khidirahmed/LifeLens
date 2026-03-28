import SwiftUI

// MARK: - LifeLens Theme

enum LifeLensTheme {
    // Primary colors - Light Pink & Navy Blue
    static let pink = Color(red: 1.0, green: 0.7, blue: 0.78)        // Soft pink
    static let pinkLight = Color(red: 1.0, green: 0.85, blue: 0.88)  // Lighter pink
    static let pinkDark = Color(red: 0.95, green: 0.55, blue: 0.65)  // Deeper pink

    static let navy = Color(red: 0.08, green: 0.1, blue: 0.18)       // Deep navy
    static let navyLight = Color(red: 0.12, green: 0.15, blue: 0.25) // Lighter navy
    static let navyDark = Color(red: 0.04, green: 0.05, blue: 0.1)   // Darker navy/black

    // Accent colors (using pink as primary accent)
    static let accentStart = pinkLight
    static let accentEnd = pinkDark

    // Background colors
    static let backgroundPrimary = navyDark
    static let backgroundSecondary = navy
    static let backgroundTertiary = navyLight

    // Status colors
    static let success = Color(red: 0.4, green: 0.85, blue: 0.6)
    static let warning = Color(red: 1.0, green: 0.75, blue: 0.35)
    static let error = Color(red: 1.0, green: 0.45, blue: 0.45)
    static let info = pink

    // Card styling
    static let cardBackground = navyLight
    static let cardBorderColor = pink.opacity(0.2)
    static let cardShadowColor = Color.black.opacity(0.3)

    // Spacing
    static let spacing: CGFloat = 16
    static let cornerRadius: CGFloat = 20
    static let cardPadding: CGFloat = 16
}

// MARK: - Animated Gradient Background

struct AnimatedMeshBackground: View {
    @State private var animate = false

    var body: some View {
        ZStack {
            // Base gradient - Navy to black
            LinearGradient(
                colors: [
                    LifeLensTheme.navy,
                    LifeLensTheme.navyDark,
                    Color(red: 0.02, green: 0.03, blue: 0.06)
                ],
                startPoint: .top,
                endPoint: .bottom
            )

            // Animated pink orbs
            Circle()
                .fill(
                    RadialGradient(
                        colors: [
                            LifeLensTheme.pink.opacity(0.25),
                            LifeLensTheme.pink.opacity(0.0)
                        ],
                        center: .center,
                        startRadius: 0,
                        endRadius: 180
                    )
                )
                .frame(width: 360, height: 360)
                .offset(x: animate ? -30 : 30, y: animate ? -80 : -40)
                .blur(radius: 50)

            Circle()
                .fill(
                    RadialGradient(
                        colors: [
                            LifeLensTheme.pinkDark.opacity(0.2),
                            LifeLensTheme.pinkDark.opacity(0.0)
                        ],
                        center: .center,
                        startRadius: 0,
                        endRadius: 200
                    )
                )
                .frame(width: 400, height: 400)
                .offset(x: animate ? 80 : 40, y: animate ? 350 : 420)
                .blur(radius: 60)

            // Subtle navy highlight
            Circle()
                .fill(
                    RadialGradient(
                        colors: [
                            LifeLensTheme.navyLight.opacity(0.4),
                            LifeLensTheme.navyLight.opacity(0.0)
                        ],
                        center: .center,
                        startRadius: 0,
                        endRadius: 150
                    )
                )
                .frame(width: 300, height: 300)
                .offset(x: animate ? 120 : 80, y: animate ? 150 : 200)
                .blur(radius: 40)
        }
        .ignoresSafeArea()
        .onAppear {
            withAnimation(.easeInOut(duration: 8).repeatForever(autoreverses: true)) {
                animate = true
            }
        }
    }
}

// MARK: - Glass Card Modifier

struct GlassCard: ViewModifier {
    var padding: CGFloat = LifeLensTheme.cardPadding

    func body(content: Content) -> some View {
        content
            .padding(padding)
            .background {
                RoundedRectangle(cornerRadius: 18)
                    .fill(LifeLensTheme.navyLight.opacity(0.7))
                    .overlay {
                        RoundedRectangle(cornerRadius: 18)
                            .stroke(
                                LinearGradient(
                                    colors: [
                                        LifeLensTheme.pink.opacity(0.25),
                                        LifeLensTheme.pink.opacity(0.05)
                                    ],
                                    startPoint: .topLeading,
                                    endPoint: .bottomTrailing
                                ),
                                lineWidth: 1
                            )
                    }
            }
    }
}

extension View {
    func glassCard(padding: CGFloat = LifeLensTheme.cardPadding) -> some View {
        modifier(GlassCard(padding: padding))
    }
}

// MARK: - Pulsing Status Indicator

struct PulsingStatusIndicator: View {
    let isActive: Bool
    let activeColor: Color
    let inactiveColor: Color

    @State private var isPulsing = false

    init(isActive: Bool, activeColor: Color = LifeLensTheme.success, inactiveColor: Color = LifeLensTheme.pink.opacity(0.5)) {
        self.isActive = isActive
        self.activeColor = activeColor
        self.inactiveColor = inactiveColor
    }

    var body: some View {
        ZStack {
            // Outer pulse ring (only when active)
            if isActive {
                Circle()
                    .stroke(activeColor.opacity(0.4), lineWidth: 1.5)
                    .frame(width: 18, height: 18)
                    .scaleEffect(isPulsing ? 1.5 : 1.0)
                    .opacity(isPulsing ? 0 : 0.6)
            }

            // Main indicator
            Circle()
                .fill(isActive ? activeColor : inactiveColor)
                .frame(width: 10, height: 10)
                .shadow(color: (isActive ? activeColor : inactiveColor).opacity(0.4), radius: 3)
        }
        .onAppear {
            if isActive {
                withAnimation(.easeInOut(duration: 1.5).repeatForever(autoreverses: false)) {
                    isPulsing = true
                }
            }
        }
        .onChange(of: isActive) { _, newValue in
            isPulsing = false
            if newValue {
                withAnimation(.easeInOut(duration: 1.5).repeatForever(autoreverses: false)) {
                    isPulsing = true
                }
            }
        }
    }
}

// MARK: - Gradient Button Style

struct GradientButtonStyle: ButtonStyle {
    var isDestructive: Bool = false

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.subheadline.weight(.semibold))
            .foregroundColor(isDestructive ? .white : LifeLensTheme.navyDark)
            .padding(.horizontal, 18)
            .padding(.vertical, 11)
            .background {
                RoundedRectangle(cornerRadius: 12)
                    .fill(
                        isDestructive
                        ? LinearGradient(colors: [LifeLensTheme.error, LifeLensTheme.error.opacity(0.8)], startPoint: .top, endPoint: .bottom)
                        : LinearGradient(colors: [LifeLensTheme.pinkLight, LifeLensTheme.pink], startPoint: .top, endPoint: .bottom)
                    )
                    .shadow(color: (isDestructive ? LifeLensTheme.error : LifeLensTheme.pink).opacity(0.35), radius: 8, y: 4)
            }
            .scaleEffect(configuration.isPressed ? 0.95 : 1.0)
            .animation(.spring(response: 0.3, dampingFraction: 0.6), value: configuration.isPressed)
    }
}

struct SecondaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.subheadline.weight(.medium))
            .foregroundColor(LifeLensTheme.pink)
            .padding(.horizontal, 14)
            .padding(.vertical, 9)
            .background {
                RoundedRectangle(cornerRadius: 10)
                    .fill(LifeLensTheme.pink.opacity(0.1))
                    .overlay {
                        RoundedRectangle(cornerRadius: 10)
                            .stroke(LifeLensTheme.pink.opacity(0.3), lineWidth: 1)
                    }
            }
            .scaleEffect(configuration.isPressed ? 0.95 : 1.0)
            .animation(.spring(response: 0.3, dampingFraction: 0.6), value: configuration.isPressed)
    }
}

// MARK: - Section Header

struct SectionHeader: View {
    let title: String
    let icon: String
    var iconColor: Color = LifeLensTheme.pink

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: icon)
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(
                    LinearGradient(
                        colors: [iconColor, iconColor.opacity(0.7)],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )
                .frame(width: 28, height: 28)
                .background {
                    Circle()
                        .fill(iconColor.opacity(0.15))
                }

            Text(title)
                .font(.subheadline.weight(.semibold))
                .foregroundColor(.white)

            Spacer()
        }
    }
}

// MARK: - Stat Counter View

struct StatCounter: View {
    let value: Int
    let label: String
    let icon: String

    var body: some View {
        VStack(spacing: 6) {
            Image(systemName: icon)
                .font(.system(size: 18))
                .foregroundStyle(
                    LinearGradient(
                        colors: [LifeLensTheme.pink, LifeLensTheme.pinkDark],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )

            Text("\(value)")
                .font(.system(size: 24, weight: .bold, design: .rounded))
                .foregroundColor(.white)
                .contentTransition(.numericText())

            Text(label)
                .font(.caption2)
                .foregroundColor(.white.opacity(0.5))
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 14)
        .background {
            RoundedRectangle(cornerRadius: 14)
                .fill(LifeLensTheme.navyLight.opacity(0.6))
                .overlay {
                    RoundedRectangle(cornerRadius: 14)
                        .stroke(LifeLensTheme.pink.opacity(0.15), lineWidth: 1)
                }
        }
    }
}

// MARK: - Modern Text Field

struct ModernTextField: View {
    let placeholder: String
    @Binding var text: String
    var keyboardType: UIKeyboardType = .default
    var width: CGFloat? = nil

    var body: some View {
        TextField(placeholder, text: $text)
            .keyboardType(keyboardType)
            .autocorrectionDisabled()
            .textInputAutocapitalization(.never)
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
            .background {
                RoundedRectangle(cornerRadius: 12)
                    .fill(LifeLensTheme.navy)
                    .overlay {
                        RoundedRectangle(cornerRadius: 12)
                            .stroke(LifeLensTheme.pink.opacity(0.2), lineWidth: 1)
                    }
            }
            .foregroundColor(.white)
            .frame(width: width)
    }
}

// MARK: - Status Badge

struct StatusBadge: View {
    let text: String
    var style: StatusStyle = .info

    enum StatusStyle {
        case success, warning, error, info

        var color: Color {
            switch self {
            case .success: return LifeLensTheme.success
            case .warning: return LifeLensTheme.warning
            case .error: return LifeLensTheme.error
            case .info: return LifeLensTheme.pink
            }
        }
    }

    var body: some View {
        Text(text)
            .font(.caption2.weight(.semibold))
            .foregroundColor(style.color)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background {
                Capsule()
                    .fill(style.color.opacity(0.15))
            }
    }
}

// MARK: - Animated Live Indicator

struct LiveIndicator: View {
    @State private var isAnimating = false

    var body: some View {
        HStack(spacing: 5) {
            Circle()
                .fill(LifeLensTheme.error)
                .frame(width: 6, height: 6)
                .scaleEffect(isAnimating ? 1.2 : 0.8)
                .opacity(isAnimating ? 1.0 : 0.6)

            Text("LIVE")
                .font(.caption2.weight(.bold))
                .foregroundColor(LifeLensTheme.error)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background {
            Capsule()
                .fill(LifeLensTheme.navyDark.opacity(0.8))
                .overlay {
                    Capsule()
                        .stroke(LifeLensTheme.error.opacity(0.4), lineWidth: 1)
                }
        }
        .onAppear {
            withAnimation(.easeInOut(duration: 0.8).repeatForever(autoreverses: true)) {
                isAnimating = true
            }
        }
    }
}
