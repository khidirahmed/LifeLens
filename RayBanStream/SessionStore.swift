import Foundation
import Observation

/// Logged-in session + which experience the user chose for this app session (caregiver vs resident).
@Observable
@MainActor
final class SessionStore {
    var accessToken: String?
    var refreshToken: String?
    var username: String?
    var email: String?
    var fullName: String?
    /// From Supabase profile: `caregiver` | `resident`
    var serverRole: String?

    /// After login, user picks how to use the app (can match or differ from account type for testing).
    var activePersona: Persona?

    enum Persona: String, CaseIterable, Identifiable {
        case caregiver
        case resident

        var id: String { rawValue }

        var title: String {
            switch self {
            case .caregiver: return "Caregiver"
            case .resident: return "Resident"
            }
        }

        var subtitle: String {
            switch self {
            case .caregiver: return "Reports & recent video"
            case .resident: return "Glasses & live stream"
            }
        }

        var systemImage: String {
            switch self {
            case .caregiver: return "chart.bar.doc.horizontal"
            case .resident: return "eyeglasses"
            }
        }
    }

    var isLoggedIn: Bool { accessToken != nil }

    init() {}

    func applyAuth(_ r: AuthResponse) {
        accessToken = r.token
        refreshToken = r.refresh_token
        username = r.username
        email = r.email
        fullName = r.full_name
        serverRole = r.role
        activePersona = nil
    }

    func logout() {
        accessToken = nil
        refreshToken = nil
        username = nil
        email = nil
        fullName = nil
        serverRole = nil
        activePersona = nil
    }

    /// Return to caregiver / resident picker without clearing tokens.
    func clearPersona() {
        activePersona = nil
    }

    /// Suggested default persona from server role.
    var suggestedPersona: Persona? {
        switch serverRole {
        case "caregiver": return .caregiver
        case "resident": return .resident
        default: return nil
        }
    }
}
