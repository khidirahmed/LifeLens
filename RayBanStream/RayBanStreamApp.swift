import SwiftUI
import MWDATCore

@main
struct RayBanStreamApp: App {
    init() {
        do {
            try Wearables.configure()
            print("✅ SDK configured OK")
        } catch {
            print("❌ SDK FAILED: \(error)")
            print("❌ Error details: \(error.localizedDescription)")
        }
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}
