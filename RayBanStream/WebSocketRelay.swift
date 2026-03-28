import Foundation
import UIKit
import Observation

/// Manages a WebSocket connection to the Python receiver on your Mac.
/// Sends JPEG-encoded video frames from the glasses camera.
@MainActor
@Observable
final class WebSocketRelay: NSObject {
    var isConnected = false
    var framesSent: Int = 0
    var serverURL: String = ""

    private var webSocket: URLSessionWebSocketTask?
    private var session: URLSession?

    /// JPEG compression quality (0.0 - 1.0). Lower = smaller frames, faster throughput.
    var jpegQuality: CGFloat = 0.5

    override init() {
        super.init()
        self.session = URLSession(
            configuration: .default,
            delegate: self,
            delegateQueue: .main
        )
    }

    func connect(to url: String) {
        guard let wsURL = URL(string: url) else {
            print("[WebSocket] Invalid URL: \(url)")
            return
        }

        serverURL = url
        webSocket?.cancel(with: .goingAway, reason: nil)
        webSocket = session?.webSocketTask(with: wsURL)
        webSocket?.resume()
        listenForMessages()
    }

    func disconnect() {
        webSocket?.cancel(with: .normalClosure, reason: nil)
        webSocket = nil
        isConnected = false
    }

    /// Send a UIImage frame as JPEG bytes over the WebSocket.
    nonisolated func sendFrame(_ image: UIImage) {
        guard let data = image.jpegData(compressionQuality: 0.5) else {
            return
        }

        Task { @MainActor in
            guard isConnected else { return }
            webSocket?.send(.data(data)) { [weak self] error in
                if let error = error {
                    print("[WebSocket] Send error: \(error.localizedDescription)")
                    DispatchQueue.main.async {
                        self?.isConnected = false
                    }
                } else {
                    DispatchQueue.main.async {
                        self?.framesSent += 1
                    }
                }
            }
        }
    }

    /// Send a text status message.
    nonisolated func sendStatus(_ message: String) {
        Task { @MainActor in
            guard isConnected else { return }
            webSocket?.send(.string(message)) { error in
                if let error = error {
                    print("[WebSocket] Status send error: \(error)")
                }
            }
        }
    }

    private func listenForMessages() {
        webSocket?.receive { [weak self] result in
            switch result {
            case .success(let message):
                switch message {
                case .string(let text):
                    print("[WebSocket] Received: \(text)")
                case .data(let data):
                    print("[WebSocket] Received \(data.count) bytes")
                @unknown default:
                    break
                }
                DispatchQueue.main.async {
                    self?.listenForMessages()
                }
            case .failure(let error):
                print("[WebSocket] Receive error: \(error)")
                DispatchQueue.main.async {
                    self?.isConnected = false
                }
            }
        }
    }
}

// MARK: - URLSessionWebSocketDelegate

extension WebSocketRelay: URLSessionWebSocketDelegate {
    nonisolated func urlSession(
        _ session: URLSession,
        webSocketTask: URLSessionWebSocketTask,
        didOpenWithProtocol protocol: String?
    ) {
        DispatchQueue.main.async {
            self.isConnected = true
            self.framesSent = 0
            print("[WebSocket] Connected to \(self.serverURL)")
        }
    }

    nonisolated func urlSession(
        _ session: URLSession,
        webSocketTask: URLSessionWebSocketTask,
        didCloseWith closeCode: URLSessionWebSocketTask.CloseCode,
        reason: Data?
    ) {
        DispatchQueue.main.async {
            self.isConnected = false
            print("[WebSocket] Disconnected (code: \(closeCode))")
        }
    }
}
