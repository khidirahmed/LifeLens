import SwiftUI
import MWDATCore

@main
struct LifeLensApp: App {
    @State private var sdkError: String?

    init() {
        do {
            try Wearables.configure()
        } catch {
            let msg = "\(error.localizedDescription) (code: \((error as NSError).code))"
            print("Failed to configure Wearables SDK: \(msg)")
            _sdkError = State(initialValue: msg)
        }

        // Configure global appearance
        configureAppearance()
    }

    var body: some Scene {
        WindowGroup {
            ContentView(sdkConfigureError: sdkError)
                .preferredColorScheme(.dark)
        }
    }

    private func configureAppearance() {
        // Set navigation bar appearance
        let navBarAppearance = UINavigationBarAppearance()
        navBarAppearance.configureWithTransparentBackground()
        navBarAppearance.backgroundColor = .clear
        navBarAppearance.titleTextAttributes = [.foregroundColor: UIColor.white]
        navBarAppearance.largeTitleTextAttributes = [.foregroundColor: UIColor.white]

        UINavigationBar.appearance().standardAppearance = navBarAppearance
        UINavigationBar.appearance().scrollEdgeAppearance = navBarAppearance
        UINavigationBar.appearance().compactAppearance = navBarAppearance

        // Set tab bar appearance if used
        let tabBarAppearance = UITabBarAppearance()
        tabBarAppearance.configureWithTransparentBackground()
        UITabBar.appearance().standardAppearance = tabBarAppearance
        UITabBar.appearance().scrollEdgeAppearance = tabBarAppearance
    }
}
