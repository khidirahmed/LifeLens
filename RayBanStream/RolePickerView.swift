import SwiftUI

struct RolePickerView: View {
    @Bindable var session: SessionStore
    @State private var choice: SessionStore.Persona?
    @State private var monitoredResidentUsername: String = LifeLensConfig.monitoredResidentUsername

    var body: some View {
        ScrollView {
            VStack(spacing: 24) {
                Text("How are you using LifeLens?")
                    .font(.title2.weight(.bold))
                    .foregroundColor(.white)
                    .multilineTextAlignment(.center)

                Text("You can switch later by signing out.")
                    .font(.caption)
                    .foregroundColor(.white.opacity(0.45))
                    .multilineTextAlignment(.center)

                VStack(spacing: 14) {
                    ForEach(SessionStore.Persona.allCases) { p in
                        Button {
                            withAnimation(.spring(response: 0.35)) {
                                choice = p
                            }
                        } label: {
                            HStack(spacing: 16) {
                                Image(systemName: p.systemImage)
                                    .font(.title2)
                                    .foregroundColor(LifeLensTheme.pink)
                                    .frame(width: 44)

                                VStack(alignment: .leading, spacing: 4) {
                                    Text(p.title)
                                        .font(.headline)
                                        .foregroundColor(.white)
                                    Text(p.subtitle)
                                        .font(.caption)
                                        .foregroundColor(.white.opacity(0.5))
                                }

                                Spacer()

                                if choice == p {
                                    Image(systemName: "checkmark.circle.fill")
                                        .foregroundColor(LifeLensTheme.success)
                                }
                            }
                            .padding(18)
                            .background(
                                RoundedRectangle(cornerRadius: 18)
                                    .fill(
                                        (choice == p ? LifeLensTheme.pink : LifeLensTheme.navyLight).opacity(choice == p ? 0.22 : 0.35)
                                    )
                                    .overlay(
                                        RoundedRectangle(cornerRadius: 18)
                                            .stroke(
                                                choice == p ? LifeLensTheme.pink.opacity(0.6) : LifeLensTheme.pink.opacity(0.12),
                                                lineWidth: 1
                                            )
                                    )
                            )
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.top, 8)

                // If user chooses caregiver, let them specify which resident they monitor.
                if choice == .caregiver {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Resident username to monitor")
                            .font(.caption)
                            .foregroundColor(.white.opacity(0.5))
                        TextField("e.g. alice", text: $monitoredResidentUsername)
                            .textFieldStyle(.plain)
                            .padding(12)
                            .background(LifeLensTheme.navyLight.opacity(0.5))
                            .cornerRadius(12)
                            .foregroundColor(.white)
                            .autocapitalization(.none)
                            .autocorrectionDisabled()
                    }
                    .padding(.top, 2)
                }

                Button {
                    let resolved = choice ?? session.suggestedPersona ?? .resident
                    if resolved == .caregiver {
                        LifeLensConfig.setMonitoredResidentUsername(monitoredResidentUsername)
                    }
                    session.activePersona = resolved
                } label: {
                    Text("Continue")
                        .fontWeight(.semibold)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 16)
                }
                .buttonStyle(GradientButtonStyle())
                .disabled(choice == nil && session.suggestedPersona == nil)
                .opacity((choice == nil && session.suggestedPersona == nil) ? 0.5 : 1)

                if let role = session.serverRole {
                    Text("Account type: \(role)")
                        .font(.caption2)
                        .foregroundColor(.white.opacity(0.35))
                }
            }
            .padding(24)
        }
        .onAppear {
            choice = session.suggestedPersona
            if monitoredResidentUsername.isEmpty, let u = session.username {
                monitoredResidentUsername = u
            }
        }
    }
}
