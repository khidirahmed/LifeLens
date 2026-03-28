import SwiftUI

struct ContentView: View {
    @State private var manager = GlassesStreamManager()
    @State private var serverIP: String = ""
    @State private var serverPort: String = "8765"

    var body: some View {
        NavigationView {
            ScrollView {
                VStack(spacing: 24) {
                    previewSection
                    serverSection
                    registrationSection
                    permissionSection
                    streamSection
                    statsSection
                }
                .padding()
            }
            .navigationTitle("RayBan Stream")
            .onAppear {
                manager.startObserving()
            }
            .onOpenURL { url in
                manager.handleURL(url)
            }
        }
    }

    // MARK: - Subviews

    private var previewSection: some View {
        VStack {
            if let preview = manager.latestPreview {
                Image(uiImage: preview)
                    .resizable()
                    .aspectRatio(contentMode: .fit)
                    .frame(maxHeight: 240)
                    .cornerRadius(12)
                    .overlay(
                        RoundedRectangle(cornerRadius: 12)
                            .stroke(Color.secondary.opacity(0.3))
                    )
            } else {
                RoundedRectangle(cornerRadius: 12)
                    .fill(Color.secondary.opacity(0.1))
                    .frame(height: 200)
                    .overlay(
                        Text("No preview")
                            .foregroundColor(.secondary)
                    )
            }
        }
    }

    private var serverSection: some View {
        GroupBox("Computer connection") {
            VStack(spacing: 12) {
                HStack {
                    TextField("Mac IP address", text: $serverIP)
                        .textFieldStyle(.roundedBorder)
                        .keyboardType(.decimalPad)
                        .autocorrectionDisabled()

                    Text(":")

                    TextField("Port", text: $serverPort)
                        .textFieldStyle(.roundedBorder)
                        .keyboardType(.numberPad)
                        .frame(width: 70)
                }

                HStack {
                    Circle()
                        .fill(manager.relay.isConnected ? Color.green : Color.red)
                        .frame(width: 10, height: 10)

                    Text(manager.relay.isConnected ? "Connected" : "Disconnected")
                        .font(.caption)
                        .foregroundColor(.secondary)

                    Spacer()

                    if manager.relay.isConnected {
                        Button("Disconnect") {
                            manager.relay.disconnect()
                        }
                        .buttonStyle(.bordered)
                        .tint(.red)
                    } else {
                        Button("Connect") {
                            let url = "ws://\(serverIP):\(serverPort)"
                            manager.relay.connect(to: url)
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(serverIP.isEmpty)
                    }
                }
            }
            .padding(.vertical, 4)
        }
    }

    private var registrationSection: some View {
        GroupBox("Glasses registration") {
            VStack(spacing: 12) {
                HStack {
                    VStack(alignment: .leading) {
                        Text("Status: \(manager.registrationState)")
                            .font(.caption)
                        Text("Device: \(manager.deviceName)")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }

                    Spacer()

                    Button("Register") {
                        manager.register()
                    }
                    .buttonStyle(.borderedProminent)
                }
            }
            .padding(.vertical, 4)
        }
    }

    private var permissionSection: some View {
        GroupBox("Camera permission") {
            HStack {
                Text("Camera: \(manager.cameraPermission)")
                    .font(.caption)

                Spacer()

                Button("Check") {
                    manager.checkCameraPermission()
                }
                .buttonStyle(.bordered)

                Button("Request") {
                    manager.requestCameraPermission()
                }
                .buttonStyle(.borderedProminent)
            }
            .padding(.vertical, 4)
        }
    }

    private var streamSection: some View {
        GroupBox("Stream") {
            VStack(spacing: 12) {
                Text("State: \(manager.streamState)")
                    .font(.caption)
                    .frame(maxWidth: .infinity, alignment: .leading)

                HStack {
                    if manager.isStreaming {
                        Button("Stop stream") {
                            manager.stopStream()
                        }
                        .buttonStyle(.bordered)
                        .tint(.red)

                        Button("Capture photo") {
                            manager.capturePhoto()
                        }
                        .buttonStyle(.bordered)
                    } else {
                        Button("Start stream") {
                            manager.startStream()
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(!manager.relay.isConnected)
                    }
                }
            }
            .padding(.vertical, 4)
        }
    }

    private var statsSection: some View {
        GroupBox("Stats") {
            HStack {
                VStack(alignment: .leading) {
                    Text("Frames from glasses: \(manager.framesReceived)")
                    Text("Frames sent to Mac: \(manager.relay.framesSent)")
                }
                .font(.caption)
                .foregroundColor(.secondary)

                Spacer()
            }
            .padding(.vertical, 4)
        }
    }
}

#Preview {
    ContentView()
}
