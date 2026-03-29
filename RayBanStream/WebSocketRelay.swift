import Foundation
import UIKit
import Observation

/// Manages a WebSocket connection to the Python receiver on your Mac.
/// Sends JPEG-encoded video frames from the glasses camera.
@MainActor
@Observable
final class WebSocketRelay: NSObject {
    var isConnected = false
    var isConnecting = false
    var connectionError: String?
    var framesSent: Int = 0
    var serverURL: String = ""

    private var webSocket: URLSessionWebSocketTask?
    private var session: URLSession?
    /// Backpressure flag: true while a frame send is in-flight.
    /// Prevents WebSocket send buffer from filling up and choking the stream.
    private var isSending = false

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
            connectionError = "Invalid URL"
            return
        }

        serverURL = url
        isConnecting = true
        connectionError = nil
        webSocket?.cancel(with: .goingAway, reason: nil)
        webSocket = session?.webSocketTask(with: wsURL)
        webSocket?.resume()
        listenForMessages()
    }

    func disconnect() {
        webSocket?.cancel(with: .normalClosure, reason: nil)
        webSocket = nil
        isConnected = false
        isConnecting = false
        isSending = false
        connectionError = nil
    }

    /// Send a UIImage frame as JPEG bytes over the WebSocket.
    nonisolated func sendFrame(_ image: UIImage) {
        guard let data = image.jpegData(compressionQuality: 0.5) else {
            return
        }

        Task { @MainActor in
            // Drop frame if not connected or a send is already in-flight.
            // This keeps the WebSocket send buffer from filling up and
            // choking the stream after ~12 seconds.
            guard isConnected, !isSending else { return }
            isSending = true
            webSocket?.send(.data(data)) { [weak self] error in
                DispatchQueue.main.async {
                    self?.isSending = false
                    if let error = error {
                        print("[WebSocket] Send error: \(error.localizedDescription)")
                        self?.isConnected = false
                    } else {
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
            self.isConnecting = false
            self.connectionError = nil
            self.framesSent = 0
            print("[WebSocket] Connected to \(self.serverURL)")
        }
    }

    nonisolated func urlSession(
        _ session: URLSession,
        task: URLSessionTask,
        didCompleteWithError error: Error?
    ) {
        DispatchQueue.main.async {
            self.isConnected = false
            self.isConnecting = false
            if let error = error {
                self.connectionError = error.localizedDescription
            }
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
            self.isConnecting = false
            print("[WebSocket] Disconnected (code: \(closeCode))")
        }
    }
}
