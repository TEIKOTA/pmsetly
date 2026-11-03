import SwiftUI

@main
struct PmsetlyApp: App {
    @NSApplicationDelegateAdaptor private var delegate: AppDelegate
    @State private var on = Pmset.sleepDisabled()
    @State private var failed = false

    var body: some Scene {
        MenuBarExtra {
            Text("Sleep prevention: \(on.map { $0 ? "ON" : "OFF" } ?? "unknown")")
            Button(on == true ? "Turn OFF" : "Turn ON") {
                failed = !Pmset.setSleepDisabled(on != true)
                on = Pmset.sleepDisabled()
            }
            if failed {
                Text("Failed. Run: sudo ./install.sh")
            }
            Divider()
            Button("Quit") { NSApp.terminate(nil) }
        } label: {
            Image(systemName: on == true ? "cup.and.saucer.fill" : "moon.zzz")
                // Re-read every 5 s so the icon follows changes made by other tools.
                .onReceive(Timer.publish(every: 5, on: .main, in: .common).autoconnect()) { _ in
                    on = Pmset.sleepDisabled()
                }
        }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    /// Do not leave sleep disabled after quitting.
    func applicationWillTerminate(_ notification: Notification) {
        if Pmset.sleepDisabled() == true {
            _ = Pmset.setSleepDisabled(false)
        }
    }
}
