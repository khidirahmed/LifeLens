import SwiftUI

struct AuthView: View {
    @Bindable var session: SessionStore
    @State private var mode: AuthMode = .signIn
    @State private var username = ""
    @State private var email = ""
    @State private var password = ""
    @State private var fullName = ""
    @State private var registerRole: SessionStore.Persona = .resident
    @State private var apiBase = LifeLensConfig.apiBaseURL
    @State private var busy = false
    @State private var errorMessage: String?

    enum AuthMode: String, CaseIterable {
        case signIn = "Sign in"
        case signUp = "Sign up"
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 20) {
                Text("LifeLens")
                    .font(.system(size: 32, weight: .bold, design: .rounded))
                    .foregroundStyle(
                        LinearGradient(
                            colors: [.white, LifeLensTheme.pink.opacity(0.9)],
                            startPoint: .leading,
                            endPoint: .trailing
                        )
                    )

                Text("Supabase backend")
                    .font(.caption)
                    .foregroundColor(.white.opacity(0.45))

                Picker("", selection: $mode) {
                    ForEach(AuthMode.allCases, id: \.self) { m in
                        Text(m.rawValue).tag(m)
                    }
                }
                .pickerStyle(.segmented)
                .padding(.top, 8)

                VStack(alignment: .leading, spacing: 10) {
                    Text("API base URL")
                        .font(.caption)
                        .foregroundColor(.white.opacity(0.5))
                    TextField("https://your-api.example.com", text: $apiBase)
                        .textFieldStyle(.plain)
                        .padding(12)
                        .background(LifeLensTheme.navyLight.opacity(0.5))
                        .cornerRadius(12)
                        .foregroundColor(.white)
                        .autocapitalization(.none)
                        .autocorrectionDisabled()
#if os(iOS)
                        .keyboardType(.URL)
#endif
                }

                ModernTextField(placeholder: "Username", text: $username, keyboardType: .default)

                if mode == .signUp {
                    ModernTextField(placeholder: "Email", text: $email, keyboardType: .emailAddress)
                    ModernTextField(placeholder: "Full name (optional)", text: $fullName, keyboardType: .default)

                    VStack(alignment: .leading, spacing: 8) {
                        Text("Account type")
                            .font(.caption)
                            .foregroundColor(.white.opacity(0.5))
                        HStack(spacing: 12) {
                            ForEach(SessionStore.Persona.allCases) { p in
                                Button {
                                    registerRole = p
                                } label: {
                                    Text(p.title)
                                        .font(.subheadline.weight(.medium))
                                        .frame(maxWidth: .infinity)
                                        .padding(.vertical, 10)
                                        .background(
                                            registerRole == p
                                                ? LifeLensTheme.pink.opacity(0.35)
                                                : LifeLensTheme.navyLight.opacity(0.4)
                                        )
                                        .cornerRadius(12)
                                }
                                .buttonStyle(.plain)
                                .foregroundColor(.white)
                            }
                        }
                    }
                }

                SecureField(
                    "",
                    text: $password,
                    prompt: Text("Password").foregroundColor(.white.opacity(0.35))
                )
                .padding(14)
                .background(LifeLensTheme.navyLight.opacity(0.5))
                .cornerRadius(14)
                .foregroundColor(.white)

                if let errorMessage {
                    Text(errorMessage)
                        .font(.caption)
                        .foregroundColor(LifeLensTheme.error)
                        .multilineTextAlignment(.center)
                }

                Button {
                    Task { await submit() }
                } label: {
                    HStack {
                        if busy { ProgressView().tint(.white) }
                        Text(mode == .signIn ? "Sign in" : "Create account")
                            .fontWeight(.semibold)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
                }
                .buttonStyle(GradientButtonStyle())
                .disabled(busy || username.isEmpty || password.isEmpty || (mode == .signUp && email.isEmpty))
                .opacity(username.isEmpty || password.isEmpty || (mode == .signUp && email.isEmpty) ? 0.45 : 1)
            }
            .padding(24)
        }
    }

    private func submit() async {
        errorMessage = nil
        busy = true
        defer { busy = false }
        LifeLensConfig.setAPIBaseURL(apiBase)

        do {
            if mode == .signUp {
                let req = AuthRegisterRequest(
                    username: username.trimmingCharacters(in: .whitespacesAndNewlines),
                    email: email.trimmingCharacters(in: .whitespacesAndNewlines),
                    password: password,
                    full_name: fullName.isEmpty ? nil : fullName,
                    role: registerRole.rawValue
                )
                let r = try await LifeLensAPI.register(req)
                await MainActor.run {
                    session.applyAuth(r)
                    LifeLensConfig.setMonitoredResidentUsername(r.username)
                }
            } else {
                let req = AuthLoginRequest(
                    username: username.trimmingCharacters(in: .whitespacesAndNewlines),
                    password: password
                )
                let r = try await LifeLensAPI.login(req)
                await MainActor.run {
                    session.applyAuth(r)
                    LifeLensConfig.setMonitoredResidentUsername(r.username)
                }
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
