import Foundation

struct AuthRegisterRequest: Encodable {
    let username: String
    let email: String
    let password: String
    let full_name: String?
    let role: String
}

struct AuthLoginRequest: Encodable {
    let username: String
    let password: String
}

struct AuthResponse: Decodable {
    let token: String
    let refresh_token: String
    let username: String
    let email: String
    let full_name: String?
    let role: String
    let message: String
}

struct AlertDTO: Decodable, Identifiable {
    let id: String
    let message: String
    let severity: String
    let video_url: String?
    let thumbnail_url: String?
    let timestamp: String
    let created_at: String
    let dismissed: Bool
}

enum LifeLensAPIError: LocalizedError {
    case invalidURL
    case http(Int, String)
    case decoding(String)

    var errorDescription: String? {
        switch self {
        case .invalidURL: return "Invalid API URL"
        case .http(let code, let body): return "Server error (\(code)): \(body)"
        case .decoding(let msg): return "Could not read response: \(msg)"
        }
    }
}

enum LifeLensAPI {
    static func register(_ body: AuthRegisterRequest) async throws -> AuthResponse {
        let data = try JSONEncoder().encode(body)
        return try await decode(path: "/auth/register", method: "POST", token: nil, body: data)
    }

    static func login(_ body: AuthLoginRequest) async throws -> AuthResponse {
        let data = try JSONEncoder().encode(body)
        return try await decode(path: "/auth/login", method: "POST", token: nil, body: data)
    }

    static func fetchAlerts(token: String, residentUsername: String?) async throws -> [AlertDTO] {
        var path = "/alerts"
        if let r = residentUsername, !r.isEmpty {
            let q = r.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? r
            path += "?resident_username=\(q)"
        }
        return try await decode(path: path, method: "GET", token: token, body: nil)
    }

    static func dismissAlert(token: String, alertId: String, residentUsername: String?) async throws {
        var path = "/alerts/\(alertId)"
        if let r = residentUsername, !r.isEmpty {
            let q = r.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? r
            path += "?resident_username=\(q)"
        }
        let (_, code) = try await rawRequest(path: path, method: "DELETE", token: token, body: nil)
        guard code == 204 || (200...299).contains(code) else {
            throw LifeLensAPIError.http(code, "")
        }
    }

    private static func decode<T: Decodable>(path: String, method: String, token: String?, body: Data?) async throws -> T {
        let (data, code) = try await rawRequest(path: path, method: method, token: token, body: body)
        guard (200...299).contains(code) else {
            throw LifeLensAPIError.http(code, String(data: data, encoding: .utf8) ?? "")
        }
        do {
            return try JSONDecoder().decode(T.self, from: data)
        } catch {
            throw LifeLensAPIError.decoding(error.localizedDescription)
        }
    }

    private static func rawRequest(path: String, method: String, token: String?, body: Data?) async throws -> (Data, Int) {
        let base = LifeLensConfig.apiBaseURL
        guard let url = URL(string: base + path) else { throw LifeLensAPIError.invalidURL }
        var req = URLRequest(url: url)
        req.httpMethod = method
        if body != nil {
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        if let token {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        req.httpBody = body
        let (data, resp) = try await URLSession.shared.data(for: req)
        let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
        return (data, code)
    }
}
