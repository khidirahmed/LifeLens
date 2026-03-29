import Foundation

/// Backend base URL for the FastAPI + Supabase server (no trailing slash).
enum LifeLensConfig {
    static let userDefaultsKey = "lifelens_api_base_url"

    static var apiBaseURL: String {
        let s = UserDefaults.standard.string(forKey: userDefaultsKey)?.trimmingCharacters(in: .whitespacesAndNewlines)
        if let s, !s.isEmpty { return s.trimmingSuffixSlash() }
        return "http://127.0.0.1:8000"
    }

    static func setAPIBaseURL(_ url: String) {
        UserDefaults.standard.set(url.trimmingSuffixSlash(), forKey: userDefaultsKey)
    }

    /// Username of the person wearing glasses — used when fetching alerts as a caregiver.
    static let monitoredResidentKey = "lifelens_monitored_resident_username"

    static var monitoredResidentUsername: String {
        UserDefaults.standard.string(forKey: monitoredResidentKey)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    }

    static func setMonitoredResidentUsername(_ name: String) {
        UserDefaults.standard.set(name.trimmingCharacters(in: .whitespacesAndNewlines), forKey: monitoredResidentKey)
    }
}

private extension String {
    func trimmingSuffixSlash() -> String {
        var t = self
        while t.hasSuffix("/") { t.removeLast() }
        return t
    }
}
