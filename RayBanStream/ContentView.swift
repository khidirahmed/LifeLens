import SwiftUI

/// Backwards-compatible wrapper: older code referenced `ContentView`,
/// but the app now routes through `RootView`.
struct ContentView: View {
    let sdkConfigureError: String?

    var body: some View {
        RootView(sdkConfigureError: sdkConfigureError)
    }
}

#Preview {
    ContentView(sdkConfigureError: nil)
}

