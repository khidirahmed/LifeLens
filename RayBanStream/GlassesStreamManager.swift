import Foundation
import MWDATCore
import MWDATCamera
import UIKit
import Observation

/// Manages the glasses connection, camera permissions, and stream session.
/// Feeds each video frame to the WebSocketRelay for forwarding to your computer.
@MainActor
@Observable
final class GlassesStreamManager {

    // MARK: - State

    var registrationState: String = "Not registered"
    var sdkConfigureError: String?
    var deviceName: String = "No device"
    var isStreaming = false
    var cameraPermission: String = "Unknown"
    var latestPreview: UIImage?
    var streamState: String = "Stopped"
    var framesReceived: Int = 0

    // MARK: - Private

    private var wearables: WearablesInterface { Wearables.shared }
    private var streamSession: StreamSession?
    private var stateToken: (any AnyListenerToken)?
    private var frameToken: (any AnyListenerToken)?

    let relay = WebSocketRelay()

    // MARK: - Registration

    func register() {
        Task { [wearables] in
            do {
                try await wearables.startRegistration()
                self.registrationState = "Registering..."
            } catch {
                let e = error as NSError
                self.registrationState = "Error: \(e.localizedDescription) [domain:\(e.domain) code:\(e.code)]"
            }
        }
    }

    func unregister() {
        Task { [wearables] in
            do {
                try await wearables.startUnregistration()
                self.registrationState = "Unregistered"
            } catch {
                let e = error as NSError
                self.registrationState = "Error: \(e.localizedDescription) [domain:\(e.domain) code:\(e.code)]"
            }
        }
    }

    /// Call from your App's onOpenURL to handle the Meta AI callback.
    nonisolated func handleURL(_ url: URL) {
        Task {
            do {
                _ = try await Wearables.shared.handleUrl(url)
            } catch {
                print("Handle URL error: \(error)")
            }
        }
    }

    // MARK: - Observation

    /// Start observing registration state and device list.
    func startObserving() {
        Task { [wearables] in
            for await state in wearables.registrationStateStream() {
                self.registrationState = "\(state)"
            }
        }

        Task { [wearables] in
            for await devices in wearables.devicesStream() {
                if let first = devices.first {
                    self.deviceName = "\(first)"
                } else {
                    self.deviceName = "No device"
                }
            }
        }
    }

    // MARK: - Camera permission

    func checkCameraPermission() {
        Task { [wearables] in
            do {
                let status = try await wearables.checkPermissionStatus(.camera)
                self.cameraPermission = "\(status)"
            } catch {
                let e = error as NSError
                self.cameraPermission = "Error: \(e.localizedDescription) [domain:\(e.domain) code:\(e.code)]"
            }
        }
    }

    func requestCameraPermission() {
        Task { [wearables] in
            do {
                let status = try await wearables.requestPermission(.camera)
                self.cameraPermission = "\(status)"
            } catch {
                let e = error as NSError
                self.cameraPermission = "Error: \(e.localizedDescription) [domain:\(e.domain) code:\(e.code)]"
            }
        }
    }

    // MARK: - Streaming
    func startStream() {
        let deviceSelector = AutoDeviceSelector(wearables: wearables)

        let config = StreamSessionConfig(
            videoCodec: VideoCodec.raw,
            resolution: StreamingResolution.low,
            frameRate: 24
        )

        let session = StreamSession(
            streamSessionConfig: config,
            deviceSelector: deviceSelector
        )
        self.streamSession = session

        stateToken = session.statePublisher.listen { [weak self] (state: StreamSessionState) in
            DispatchQueue.main.async {
                self?.streamState = "\(state)"
                self?.isStreaming = (state == .streaming)

                if state == .streaming {
                    self?.relay.sendStatus("streaming_started")
                }
            }
        }

        frameToken = session.videoFramePublisher.listen { [weak self] (frame: VideoFrame) in
            guard let image = frame.makeUIImage() else { return }
            DispatchQueue.main.async {
                guard let self = self else { return }
                self.framesReceived += 1

                if self.framesReceived % 5 == 0 {
                    self.latestPreview = image
                }

                self.relay.sendFrame(image)
            }
        }

        Task {
            await session.start()
        }
    }

    func stopStream() {
        let session = streamSession
        streamSession = nil
        isStreaming = false
        streamState = "Stopped"
        relay.sendStatus("streaming_stopped")
        Task {
            await session?.stop()
        }
    }

    func capturePhoto() {
        _ = streamSession?.capturePhoto(format: .jpeg)
    }
}
