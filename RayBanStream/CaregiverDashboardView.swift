import SwiftUI
import AVKit

/// Reports + optional clip playback (URLs from your pipeline; segments are often ~30s–30min depending on relay).
struct CaregiverDashboardView: View {
    @Bindable var session: SessionStore
    @State private var monitoredResident = LifeLensConfig.monitoredResidentUsername
    @State private var alerts: [AlertDTO] = []
    @State private var loading = false
    @State private var errorMessage: String?
    @State private var selectedVideoURL: URL?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Text("Caregiver")
                    .font(.largeTitle.bold())
                    .foregroundColor(.white)

                Text("Enter the resident’s login username (the account for the person wearing glasses). Pipeline alerts must use that same username as resident_username.")
                    .font(.caption)
                    .foregroundColor(.white.opacity(0.55))

                VStack(alignment: .leading, spacing: 6) {
                    Text("Monitored resident username")
                        .font(.caption)
                        .foregroundColor(.white.opacity(0.5))
                    TextField("e.g. alice", text: $monitoredResident)
                        .textFieldStyle(.plain)
                        .padding(12)
                        .background(LifeLensTheme.navyLight.opacity(0.5))
                        .cornerRadius(12)
                        .foregroundColor(.white)
                        .autocapitalization(.none)
                        .autocorrectionDisabled()
                        .onChange(of: monitoredResident) { _, new in
                            LifeLensConfig.setMonitoredResidentUsername(new)
                        }
                }

                HStack {
                    Button {
                        Task { await load() }
                    } label: {
                        Label(loading ? "Loading…" : "Refresh reports", systemImage: "arrow.clockwise")
                    }
                    .buttonStyle(SecondaryButtonStyle())
                    .disabled(loading || monitoredResident.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || session.accessToken == nil)

                    Spacer()
                }

                HStack {
                    Image(systemName: "info.circle")
                        .foregroundColor(LifeLensTheme.pink.opacity(0.7))
                    Text("Video links appear when your backend stores clips (HTTP / Supabase). Relay segments are often ~30s each; your server may aggregate up to ~30 minutes.")
                        .font(.caption2)
                        .foregroundColor(.white.opacity(0.4))
                }
                .padding(12)
                .background(LifeLensTheme.navy.opacity(0.4))
                .cornerRadius(12)

                if let errorMessage {
                    Text(errorMessage)
                        .font(.caption)
                        .foregroundColor(LifeLensTheme.error)
                }

                if alerts.isEmpty && !loading {
                    Text("No alerts in the last 24 hours.")
                        .font(.subheadline)
                        .foregroundColor(.white.opacity(0.45))
                        .frame(maxWidth: .infinity, alignment: .center)
                        .padding(.vertical, 40)
                }

                ForEach(alerts) { a in
                    alertCard(a)
                }
            }
            .padding(20)
        }
        .background(Color.clear)
        .sheet(isPresented: Binding(
            get: { selectedVideoURL != nil },
            set: { if !$0 { selectedVideoURL = nil } }
        )) {
            if let url = selectedVideoURL {
                NavigationStack {
                    VideoPlayer(player: AVPlayer(url: url))
                        .ignoresSafeArea()
                        .navigationTitle("Clip")
                        .navigationBarTitleDisplayMode(.inline)
                        .toolbar {
                            ToolbarItem(placement: .cancellationAction) {
                                Button("Done") { selectedVideoURL = nil }
                            }
                        }
                }
            }
        }
        .task {
            await load()
        }
    }

    private func alertCard(_ a: AlertDTO) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(a.severity.uppercased())
                    .font(.caption2.weight(.bold))
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(
                        Capsule().fill(severityColor(a.severity).opacity(0.25))
                    )
                    .foregroundColor(severityColor(a.severity))
                Spacer()
                Text(a.created_at.prefix(16).replacingOccurrences(of: "T", with: " "))
                    .font(.caption2)
                    .foregroundColor(.white.opacity(0.35))
            }

            Text(a.message)
                .font(.body)
                .foregroundColor(.white)

            if let urlStr = a.video_url, let url = URL(string: urlStr) {
                Button {
                    selectedVideoURL = url
                } label: {
                    Label("Play video", systemImage: "play.circle.fill")
                }
                .buttonStyle(SecondaryButtonStyle())
            }

            Button(role: .destructive) {
                Task { await dismiss(a) }
            } label: {
                Text("Dismiss")
                    .font(.caption)
            }
            .buttonStyle(.borderless)
        }
        .padding(16)
        .background(
            RoundedRectangle(cornerRadius: 16)
                .fill(LifeLensTheme.navyLight.opacity(0.45))
                .overlay(
                    RoundedRectangle(cornerRadius: 16)
                        .stroke(LifeLensTheme.pink.opacity(0.15), lineWidth: 1)
                )
        )
    }

    private func severityColor(_ s: String) -> Color {
        switch s.lowercased() {
        case "high": return LifeLensTheme.error
        case "medium": return LifeLensTheme.warning
        default: return LifeLensTheme.info
        }
    }

    private func load() async {
        guard let token = session.accessToken else { return }
        let resident = monitoredResident.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !resident.isEmpty else {
            errorMessage = "Set the resident username first."
            return
        }
        loading = true
        errorMessage = nil
        defer { loading = false }
        do {
            let rows = try await LifeLensAPI.fetchAlerts(token: token, residentUsername: resident)
            await MainActor.run { alerts = rows }
        } catch {
            await MainActor.run {
                errorMessage = error.localizedDescription
                alerts = []
            }
        }
    }

    private func dismiss(_ a: AlertDTO) async {
        guard let token = session.accessToken else { return }
        let resident = monitoredResident.trimmingCharacters(in: .whitespacesAndNewlines)
        do {
            try await LifeLensAPI.dismissAlert(token: token, alertId: a.id, residentUsername: resident)
            await load()
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }
}
