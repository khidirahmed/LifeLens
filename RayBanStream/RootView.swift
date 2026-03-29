import SwiftUI

struct RootView: View {
    var sdkConfigureError: String?
    @State private var session = SessionStore()

    var body: some View {
        ZStack {
            AnimatedMeshBackground()

            if !session.isLoggedIn {
                AuthView(session: session)
            } else if session.activePersona == nil {
                RolePickerView(session: session)
            } else {
                personaContent
            }
        }
        .preferredColorScheme(.dark)
    }

    @ViewBuilder
    private var personaContent: some View {
        switch session.activePersona {
        case .resident:
            NavigationStack {
                ElderlyDeviceHomeView(sdkConfigureError: sdkConfigureError)
                    .toolbar {
                        ToolbarItem(placement: .topBarTrailing) {
                            Menu {
                                Button("Switch role") {
                                    session.clearPersona()
                                }
                                Button("Sign out", role: .destructive) {
                                    session.logout()
                                }
                            } label: {
                                Image(systemName: "ellipsis.circle")
                            }
                        }
                    }
            }
        case .caregiver:
            NavigationStack {
                CaregiverDashboardView(session: session)
                    .toolbar {
                        ToolbarItem(placement: .topBarTrailing) {
                            Menu {
                                Button("Switch role") {
                                    session.clearPersona()
                                }
                                Button("Sign out", role: .destructive) {
                                    session.logout()
                                }
                            } label: {
                                Image(systemName: "ellipsis.circle")
                            }
                        }
                    }
            }
        case .none:
            EmptyView()
        }
    }
}

#Preview {
    RootView(sdkConfigureError: nil)
}
