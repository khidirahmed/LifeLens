import SwiftUI
import MWDATCore

@main
struct RayBanStreamApp: App {
    init() {
        do {
            try Wearables.configure()
        } catch {
            print("Failed to configure Wearables SDK: \(error)")
        }
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}
