import SwiftUI

struct ElderlyDeviceHomeView: View {
    var sdkConfigureError: String? = nil
    @State private var manager = GlassesStreamManager()
    @State private var serverIP: String = ""
    @State private var serverPort: String = "8765"
    @State private var showingSettings = false
    @State private var appearAnimation = false

    var body: some View {
        ZStack {
            // Animated background
            AnimatedMeshBackground()

            ScrollView(showsIndicators: false) {
                VStack(spacing: 16) {
                    // Header
                    headerView
                        .opacity(appearAnimation ? 1 : 0)
                        .offset(y: appearAnimation ? 0 : -20)

                    // SDK init error banner
                    if let err = sdkConfigureError {
                        HStack(spacing: 8) {
                            Image(systemName: "exclamationmark.triangle.fill")
                            Text("SDK init failed: \(err)")
                                .font(.caption)
                        }
                        .foregroundColor(.black)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 8)
                        .background(LifeLensTheme.warning)
                        .cornerRadius(10)
                        .opacity(appearAnimation ? 1 : 0)
                    }

                    // Preview Section
                    previewSection
                        .opacity(appearAnimation ? 1 : 0)
                        .offset(y: appearAnimation ? 0 : 20)

                    // Stats Section
                    statsSection
                        .opacity(appearAnimation ? 1 : 0)
                        .offset(y: appearAnimation ? 0 : 20)

                    // Connection Card
                    connectionSection
                        .opacity(appearAnimation ? 1 : 0)
                        .offset(y: appearAnimation ? 0 : 20)

                    // Glasses Card
                    glassesSection
                        .opacity(appearAnimation ? 1 : 0)
                        .offset(y: appearAnimation ? 0 : 20)

                    // Stream Control Card
                    streamSection
                        .opacity(appearAnimation ? 1 : 0)
                        .offset(y: appearAnimation ? 0 : 20)

                    Spacer(minLength: 30)
                }
                .padding(.horizontal, 16)
                .padding(.top, 8)
            }
            .safeAreaInset(edge: .top) {
                Color.clear.frame(height: 0)
            }
        }
        .preferredColorScheme(.dark)
        .onAppear {
            manager.startObserving()
            withAnimation(.spring(response: 0.8, dampingFraction: 0.8).delay(0.1)) {
                appearAnimation = true
            }
        }
        .onOpenURL { url in
            manager.handleURL(url)
        }
    }

    // MARK: - Header

    private var headerView: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text("LifeLens")
                    .font(.system(size: 26, weight: .bold, design: .rounded))
                    .foregroundStyle(
                        LinearGradient(
                            colors: [.white, LifeLensTheme.pink.opacity(0.9)],
                            startPoint: .leading,
                            endPoint: .trailing
                        )
                    )

                Text("Glasses · live stream to your Mac")
                    .font(.caption)
                    .foregroundColor(.white.opacity(0.5))
            }

            Spacer()

            // Connection status orb
            ZStack {
                Circle()
                    .fill(
                        RadialGradient(
                            colors: [
                                (manager.relay.isConnected ? LifeLensTheme.success : LifeLensTheme.pink).opacity(0.25),
                                .clear
                            ],
                            center: .center,
                            startRadius: 0,
                            endRadius: 20
                        )
                    )
                    .frame(width: 44, height: 44)

                Image(systemName: manager.relay.isConnected ? "wifi" : "wifi.slash")
                    .font(.system(size: 18, weight: .medium))
                    .foregroundColor(manager.relay.isConnected ? LifeLensTheme.success : LifeLensTheme.pink.opacity(0.6))
            }
        }
        .padding(.vertical, 8)
    }

    // MARK: - Preview Section

    private var previewSection: some View {
        VStack(spacing: 0) {
            if let preview = manager.latestPreview {
                ZStack(alignment: .topTrailing) {
                    Image(uiImage: preview)
                        .resizable()
                        .aspectRatio(contentMode: .fill)
                        .frame(height: 180)
                        .clipped()
                        .cornerRadius(20)
                        .overlay {
                            RoundedRectangle(cornerRadius: 20)
                                .stroke(
                                    LinearGradient(
                                        colors: [LifeLensTheme.pink.opacity(0.4), LifeLensTheme.pink.opacity(0.1)],
                                        startPoint: .topLeading,
                                        endPoint: .bottomTrailing
                                    ),
                                    lineWidth: 1
                                )
                        }
                        .shadow(color: LifeLensTheme.pink.opacity(0.2), radius: 16, y: 8)

                    if manager.isStreaming {
                        LiveIndicator()
                            .padding(10)
                    }
                }
            } else {
                ZStack {
                    RoundedRectangle(cornerRadius: 20)
                        .fill(
                            LinearGradient(
                                colors: [
                                    LifeLensTheme.navyLight.opacity(0.6),
                                    LifeLensTheme.navy.opacity(0.4)
                                ],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )
                        )
                        .frame(height: 180)
                        .overlay {
                            RoundedRectangle(cornerRadius: 20)
                                .stroke(LifeLensTheme.pink.opacity(0.15), lineWidth: 1)
                        }

                    VStack(spacing: 10) {
                        Image(systemName: "eye.slash")
                            .font(.system(size: 32, weight: .light))
                            .foregroundColor(LifeLensTheme.pink.opacity(0.4))

                        Text("No preview available")
                            .font(.subheadline)
                            .foregroundColor(.white.opacity(0.4))

                        Text("Start streaming to see live view")
                            .font(.caption2)
                            .foregroundColor(.white.opacity(0.25))
                    }
                }
            }
        }
    }

    // MARK: - Stats Section

    private var statsSection: some View {
        HStack(spacing: 10) {
            StatCounter(
                value: manager.framesReceived,
                label: "Received",
                icon: "arrow.down.circle.fill"
            )

            StatCounter(
                value: manager.relay.framesSent,
                label: "Sent",
                icon: "arrow.up.circle.fill"
            )
        }
        .animation(.spring(response: 0.3), value: manager.framesReceived)
        .animation(.spring(response: 0.3), value: manager.relay.framesSent)
    }

    // MARK: - Connection Section

    private var connectionSection: some View {
        VStack(spacing: 14) {
            SectionHeader(title: "Connection", icon: "network", iconColor: LifeLensTheme.pink)

            VStack(spacing: 12) {
                HStack(spacing: 8) {
                    ModernTextField(
                        placeholder: "Mac IP address",
                        text: $serverIP,
                        keyboardType: .decimalPad
                    )

                    Text(":")
                        .foregroundColor(LifeLensTheme.pink.opacity(0.4))
                        .font(.body)

                    ModernTextField(
                        placeholder: "Port",
                        text: $serverPort,
                        keyboardType: .numberPad,
                        width: 72
                    )
                }

                HStack {
                    PulsingStatusIndicator(isActive: manager.relay.isConnected)

                    Text(manager.relay.isConnecting ? "Connecting..." :
                         manager.relay.isConnected  ? "Connected"     : "Disconnected")
                        .font(.caption)
                        .foregroundColor(.white.opacity(0.6))

                    Spacer()

                    if manager.relay.isConnected {
                        Button("Disconnect") {
                            withAnimation(.spring(response: 0.4)) {
                                manager.relay.disconnect()
                            }
                        }
                        .buttonStyle(GradientButtonStyle(isDestructive: true))
                    } else {
                        Button(manager.relay.isConnecting ? "Connecting..." : "Connect") {
                            UIApplication.shared.sendAction(
                                #selector(UIResponder.resignFirstResponder),
                                to: nil, from: nil, for: nil
                            )
                            let url = "ws://\(serverIP):\(serverPort)"
                            withAnimation(.spring(response: 0.4)) {
                                manager.relay.connect(to: url)
                            }
                        }
                        .buttonStyle(GradientButtonStyle())
                        .disabled(serverIP.isEmpty || manager.relay.isConnecting)
                        .opacity(serverIP.isEmpty ? 0.5 : 1.0)
                    }
                }

                if let error = manager.relay.connectionError {
                    HStack(spacing: 5) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .font(.caption2)
                        Text(error)
                            .font(.caption2)
                    }
                    .foregroundColor(LifeLensTheme.warning)
                }
            }
        }
        .glassCard()
    }

    // MARK: - Glasses Section

    private var glassesSection: some View {
        VStack(spacing: 14) {
            SectionHeader(title: "Ray-Ban Meta", icon: "eyeglasses", iconColor: LifeLensTheme.pinkDark)

            VStack(spacing: 12) {
                // Registration status
                HStack {
                    VStack(alignment: .leading, spacing: 3) {
                        HStack(spacing: 6) {
                            Text("Registration")
                                .font(.caption)
                                .foregroundColor(.white.opacity(0.6))

                            StatusBadge(
                                text: formatStatus(manager.registrationState),
                                style: statusStyle(for: manager.registrationState)
                            )
                        }

                        if manager.deviceName != "No device" {
                            Text(manager.deviceName)
                                .font(.caption2)
                                .foregroundColor(.white.opacity(0.4))
                                .lineLimit(1)
                        }
                    }

                    Spacer()

                    Button("Register") {
                        manager.register()
                    }
                    .buttonStyle(SecondaryButtonStyle())
                }

                Divider()
                    .background(LifeLensTheme.pink.opacity(0.15))

                // Camera permission
                HStack {
                    VStack(alignment: .leading, spacing: 3) {
                        HStack(spacing: 6) {
                            Text("Camera")
                                .font(.caption)
                                .foregroundColor(.white.opacity(0.6))

                            StatusBadge(
                                text: formatStatus(manager.cameraPermission),
                                style: statusStyle(for: manager.cameraPermission)
                            )
                        }
                    }

                    Spacer()

                    HStack(spacing: 6) {
                        Button {
                            manager.checkCameraPermission()
                        } label: {
                            Image(systemName: "arrow.clockwise")
                        }
                        .buttonStyle(SecondaryButtonStyle())

                        Button("Grant") {
                            manager.requestCameraPermission()
                        }
                        .buttonStyle(SecondaryButtonStyle())
                    }
                }
            }
        }
        .glassCard()
    }

    // MARK: - Stream Section

    private var streamSection: some View {
        VStack(spacing: 14) {
            HStack {
                SectionHeader(
                    title: "Stream Control",
                    icon: manager.isStreaming ? "video.fill" : "video",
                    iconColor: manager.isStreaming ? LifeLensTheme.success : LifeLensTheme.pink.opacity(0.6)
                )

                if manager.isStreaming {
                    Spacer()
                    StatusBadge(text: "Active", style: .success)
                }
            }

            VStack(spacing: 12) {
                HStack {
                    VStack(alignment: .leading, spacing: 3) {
                        Text("Status")
                            .font(.caption)
                            .foregroundColor(.white.opacity(0.6))

                        Text(formatStreamState(manager.streamState))
                            .font(.caption2)
                            .foregroundColor(.white.opacity(0.4))
                    }

                    Spacer()
                }

                HStack(spacing: 10) {
                    if manager.isStreaming {
                        Button {
                            withAnimation(.spring(response: 0.4)) {
                                manager.stopStream()
                            }
                        } label: {
                            HStack(spacing: 6) {
                                Image(systemName: "stop.fill")
                                Text("Stop")
                            }
                        }
                        .buttonStyle(GradientButtonStyle(isDestructive: true))

                        Button {
                            manager.capturePhoto()
                        } label: {
                            HStack(spacing: 6) {
                                Image(systemName: "camera.fill")
                                Text("Capture")
                            }
                        }
                        .buttonStyle(SecondaryButtonStyle())
                    } else {
                        Button {
                            withAnimation(.spring(response: 0.4)) {
                                manager.startStream()
                            }
                        } label: {
                            HStack(spacing: 6) {
                                Image(systemName: "play.fill")
                                Text("Start Stream")
                            }
                            .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(GradientButtonStyle())
                        .disabled(!manager.relay.isConnected)
                        .opacity(!manager.relay.isConnected ? 0.5 : 1.0)
                    }
                }

                if !manager.relay.isConnected && !manager.isStreaming {
                    HStack(spacing: 5) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .font(.caption2)

                        Text("Connect to your Mac first to start streaming")
                            .font(.caption2)
                    }
                    .foregroundColor(LifeLensTheme.warning)
                    .padding(.top, 2)
                }
            }
        }
        .glassCard()
    }

    // MARK: - Helpers

    private func formatStatus(_ status: String) -> String {
        if status.lowercased().contains("granted") { return "Granted" }
        if status.lowercased().contains("denied") { return "Denied" }
        if status.lowercased().contains("registered") { return "Ready" }
        if status.lowercased().contains("notregistered") { return "Not Set" }
        if status.lowercased().contains("registering") { return "Pairing..." }
        if status.lowercased().contains("unknown") { return "Unknown" }
        if status.lowercased().contains("no device") { return "No Device" }
        if status.lowercased().hasPrefix("error:") { return String(status.dropFirst(7)) }
        return status
    }

    private func statusStyle(for status: String) -> StatusBadge.StatusStyle {
        let lower = status.lowercased()
        if lower.contains("granted") || lower.contains("registered") { return .success }
        if lower.contains("denied") || lower.contains("error") { return .error }
        if lower.contains("registering") { return .warning }
        return .info
    }

    private func formatStreamState(_ state: String) -> String {
        if state.lowercased().contains("streaming") { return "Streaming live video" }
        if state.lowercased().contains("stopped") { return "Stream stopped" }
        if state.lowercased().contains("starting") { return "Starting stream..." }
        return state
    }
}

#Preview {
    ElderlyDeviceHomeView(sdkConfigureError: nil)
}
