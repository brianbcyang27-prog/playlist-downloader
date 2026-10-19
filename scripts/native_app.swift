// Playlist Downloader — native macOS shell.
//
// Owns a real window (WKWebView) and the Python backend that serves the UI.
// The Python runtime and app code live inside this bundle, so the app is
// self-contained: no browser, no terminal, no external Python needed.
//
//   Contents/Resources/python/bin/python3.14   bundled interpreter
//   Contents/Resources/python/lib/python3.14   stdlib + site-packages
//   Contents/Resources/app                    the backend package
//   Contents/Resources/web                    the UI

import Cocoa
import Darwin
import WebKit

let appName = "Playlist Downloader"

/// Debug tracing to stderr, enabled with PLAYLIST_DOWNLOADER_DEBUG=1.
func dbg(_ message: String) {
    guard ProcessInfo.processInfo.environment["PLAYLIST_DOWNLOADER_DEBUG"] != nil else { return }
    FileHandle.standardError.write("[pd] \(message)\n".data(using: .utf8)!)
}

/// Always-on lifecycle log, because a double-clicked app has no console.
/// Written to ~/Library/Application Support/PlaylistDownloader/native.log.
func lifecycle(_ message: String) {
    let stamp = ISO8601DateFormatter().string(from: Date())
    let line = "[\(stamp)] \(message)\n"
    guard let base = try? FileManager.default.url(for: .applicationSupportDirectory,
                                                  in: .userDomainMask,
                                                  appropriateFor: nil, create: true) else { return }
    let dir = base.appendingPathComponent("PlaylistDownloader", isDirectory: true)
    try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    let log = dir.appendingPathComponent("native.log")
    if let handle = try? FileHandle(forWritingTo: log) {
        handle.seekToEndOfFile()
        handle.write(line.data(using: .utf8)!)
        try? handle.close()
    } else {
        try? line.write(to: log, atomically: true, encoding: .utf8)
    }
    dbg(message)
}

final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate, WKNavigationDelegate {

    var window: NSWindow!
    var webView: WKWebView!
    var serverProcess: Process?
    var logHandle: FileHandle?
    var baseURL: URL?
    var isQuitting = false
    var didShowError = false

    // MARK: lifecycle

    func applicationDidFinishLaunching(_ notification: Notification) {
        lifecycle("=== app launched, bundle=\(Bundle.main.bundlePath) ===")
        buildMenu()
        makeWindow()
        lifecycle("window created")

        let resources = Bundle.main.resourceURL ?? Bundle.main.bundleURL
        openLog()

        guard let python = pythonExecutable(in: resources) else {
            lifecycle("FATAL: no python at \(resources.path)/python/bin/python3.14")
            showError("The bundled Python runtime is missing.\n\nReinstall \(appName).")
            return
        }
        lifecycle("python: \(python.path)")

        let port = pickFreePort(preferred: 8765)
        lifecycle("port: \(port)")
        baseURL = URL(string: "http://127.0.0.1:\(port)/")!

        startServer(python: python, resources: resources, port: port)
        lifecycle("server process launched")
        waitForServer(then: { [weak self] ok in
            guard let self else { return }
            if ok, let url = self.baseURL {
                self.webView.load(URLRequest(url: url))
            } else if !self.didShowError {
                self.showError(self.startupFailureMessage())
            }
        })
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    func applicationWillTerminate(_ notification: Notification) {
        stopServer()
    }

    func windowWillClose(_ notification: Notification) {
        NSApp.terminate(nil)
    }

    // MARK: window

    private func makeWindow() {
        let frame = NSRect(x: 0, y: 0, width: 1180, height: 820)
        window = NSWindow(
            contentRect: frame,
            styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        window.title = appName
        window.titlebarAppearsTransparent = true
        window.minSize = NSSize(width: 900, height: 600)
        window.delegate = self
        window.center()
        window.setFrameAutosaveName("MainWindow")

        let config = WKWebViewConfiguration()
        config.websiteDataStore = .default()
        webView = WKWebView(frame: frame, configuration: config)
        webView.navigationDelegate = self
        webView.autoresizingMask = [.width, .height]
        if #available(macOS 12.0, *) {
            // Dark backdrop so there is no white flash before the UI paints.
            webView.underPageBackgroundColor = NSColor(red: 0.063, green: 0.063, blue: 0.078, alpha: 1)
        }
        window.contentView = webView
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)

        loadPlaceholder("Starting the local server…")
    }

    private func loadPlaceholder(_ message: String) {
        let html = """
        <!doctype html><meta charset="utf-8">
        <style>
          html,body{height:100%;margin:0;background:#101014;color:#c9c9d1;
            font:14px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
          .wrap{height:100%;display:flex;flex-direction:column;align-items:center;
            justify-content:center;gap:18px}
          .spin{width:26px;height:26px;border:3px solid #2b2b36;border-top-color:#7c5cff;
            border-radius:50%;animation:s 1s linear infinite}
          @keyframes s{to{transform:rotate(360deg)}}
        </style>
        <div class="wrap"><div class="spin"></div><div>\(message)</div></div>
        """
        webView.loadHTMLString(html, baseURL: nil)
    }

    // MARK: python backend

    private func pythonExecutable(in resources: URL) -> URL? {
        let bundled = resources.appendingPathComponent("python/bin/python3.14")
        if FileManager.default.isExecutableFile(atPath: bundled.path) { return bundled }
        // Development fallback: use a project venv when running from source.
        if let project = ProcessInfo.processInfo.environment["PLAYLIST_DOWNLOADER_PROJECT"] {
            let dev = URL(fileURLWithPath: project).appendingPathComponent(".venv/bin/python")
            if FileManager.default.isExecutableFile(atPath: dev.path) { return dev }
        }
        if let which = which("python3") { return URL(fileURLWithPath: which) }
        return nil
    }

    private func startServer(python: URL, resources: URL, port: Int) {
        let proc = Process()
        proc.executableURL = python
        proc.currentDirectoryURL = resources
        proc.arguments = ["-u", "-m", "app.server", "--port", "\(port)", "--no-browser"]

        var env = ProcessInfo.processInfo.environment
        let home = FileManager.default.homeDirectoryForCurrentUser
        env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:\(home.path)/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
        env["PYTHONHOME"] = resources.appendingPathComponent("python").path
        env["PYTHONPATH"] = resources.path
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        proc.environment = env

        let pipe = Pipe()
        proc.standardOutput = pipe
        proc.standardError = pipe
        proc.standardInput = FileHandle.nullDevice
        pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            if !data.isEmpty { self?.logHandle?.write(data) }
        }
        proc.terminationHandler = { [weak self] _ in
            DispatchQueue.main.async {
                guard let self, !self.isQuitting else { return }
                self.isQuitting = true
                NSApp.terminate(nil)
            }
        }
        do {
            try proc.run()
            serverProcess = proc
        } catch {
            showError("Could not start the backend.\n\n\(error.localizedDescription)")
        }
    }

    private func stopServer() {
        guard !isQuitting || serverProcess?.isRunning == true else { return }
        isQuitting = true
        // Ask the server to close cleanly (flushes the database) and then make sure.
        if let url = baseURL?.appendingPathComponent("api/shutdown") {
            var req = URLRequest(url: url)
            req.httpMethod = "POST"
            req.timeoutInterval = 1.5
            let sem = DispatchSemaphore(value: 0)
            URLSession.shared.dataTask(with: req) { _, _, _ in sem.signal() }.resume()
            _ = sem.wait(timeout: .now() + 2.0)
        }
        if let proc = serverProcess, proc.isRunning {
            proc.terminate()
        }
        serverProcess = nil
    }

    private func waitForServer(then done: @escaping (Bool) -> Void) {
        guard let ping = baseURL?.appendingPathComponent("api/ping") else { return done(false) }
        DispatchQueue.global(qos: .userInitiated).async {
            let deadline = Date().addingTimeInterval(25)
            var attempts = 0
            var lastError = "timed out"
            while Date() < deadline {
                attempts += 1
                do {
                    let data = try Data(contentsOf: ping)
                    if let text = String(data: data, encoding: .utf8), text.contains("\"ok\"") {
                        lifecycle("server ready after \(attempts) ping attempt(s)")
                        DispatchQueue.main.async { done(true) }
                        return
                    }
                } catch {
                    lastError = error.localizedDescription
                }
                Thread.sleep(forTimeInterval: 0.25)
            }
            lifecycle("server NOT ready after \(attempts) attempts: \(lastError)")
            DispatchQueue.main.async { done(false) }
        }
    }

    private func startupFailureMessage() -> String {
        var tail = ""
        if let url = try? FileManager.default.url(for: .applicationSupportDirectory, in: .userDomainMask,
                                                  appropriateFor: nil, create: false) {
            let log = url.appendingPathComponent("PlaylistDownloader/app.log")
            if let text = try? String(contentsOf: log, encoding: .utf8) {
                tail = text.split(separator: "\n").suffix(12).joined(separator: "\n")
            }
        }
        return "The local server did not start.\n\n\(tail)"
    }

    private func showError(_ message: String) {
        didShowError = true
        let escaped = message
            .replacingOccurrences(of: "&", with: "&amp;")
            .replacingOccurrences(of: "<", with: "&lt;")
            .replacingOccurrences(of: ">", with: "&gt;")
        let html = """
        <!doctype html><meta charset="utf-8">
        <style>html,body{height:100%;margin:0;background:#101014;color:#e7e7ee;
          font:14px -apple-system,BlinkMacSystemFont,sans-serif}
          .wrap{height:100%;display:flex;flex-direction:column;align-items:center;
          justify-content:center;gap:14px;padding:40px;text-align:center}
          pre{background:#17171e;padding:14px;border-radius:8px;color:#9aa;font-size:12px;
          max-width:760px;overflow:auto;text-align:left}
          h2{color:#ff6b6b;margin:0}</style>
        <div class="wrap"><h2>\(appName) could not start</h2>
        <pre>\(escaped)</pre></div>
        """
        webView.loadHTMLString(html, baseURL: nil)
    }

    // MARK: helpers

    private func openLog() {
        guard let base = try? FileManager.default.url(for: .applicationSupportDirectory,
                                                      in: .userDomainMask, appropriateFor: nil, create: true)
        else { return }
        let dir = base.appendingPathComponent("PlaylistDownloader", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let log = dir.appendingPathComponent("app.log")
        if !FileManager.default.fileExists(atPath: log.path) {
            FileManager.default.createFile(atPath: log.path, contents: nil)
        }
        logHandle = try? FileHandle(forWritingTo: log)
        logHandle?.seekToEndOfFile()
    }

    private func pickFreePort(preferred: Int) -> Int {
        for candidate in [preferred, 0] {
            let fd = socket(AF_INET, SOCK_STREAM, 0)
            if fd < 0 { continue }
            var addr = sockaddr_in()
            addr.sin_family = sa_family_t(AF_INET)
            addr.sin_port = in_port_t(UInt16(candidate).bigEndian)
            addr.sin_addr.s_addr = inet_addr("127.0.0.1")
            let bound = withUnsafePointer(to: &addr) {
                $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                    Darwin.bind(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
                }
            }
            if bound != 0 { close(fd); continue }
            var out = sockaddr_in()
            var len = socklen_t(MemoryLayout<sockaddr_in>.size)
            let got = withUnsafeMutablePointer(to: &out) {
                $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { getsockname(fd, $0, &len) }
            }
            close(fd)
            if got == 0 { return Int(UInt16(bigEndian: out.sin_port)) }
        }
        return 8765
    }

    private func which(_ tool: String) -> String? {
        let paths = (ProcessInfo.processInfo.environment["PATH"] ?? "").split(separator: ":")
        for dir in paths {
            let full = "\(dir)/\(tool)"
            if FileManager.default.isExecutableFile(atPath: full) { return full }
        }
        return nil
    }

    private func buildMenu() {
        let main = NSMenu()

        let appItem = NSMenuItem()
        main.addItem(appItem)
        let appMenu = NSMenu()
        appItem.submenu = appMenu
        appMenu.addItem(withTitle: "About \(appName)",
                        action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Hide \(appName)",
                        action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        let hideOthers = appMenu.addItem(withTitle: "Hide Others",
                        action: #selector(NSApplication.hideOtherApplications(_:)), keyEquivalent: "h")
        hideOthers.keyEquivalentModifierMask = [.command, .option]
        appMenu.addItem(withTitle: "Show All",
                        action: #selector(NSApplication.unhideAllApplications(_:)), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Quit \(appName)",
                        action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")

        let editItem = NSMenuItem()
        main.addItem(editItem)
        let edit = NSMenu(title: "Edit")
        editItem.submenu = edit
        edit.addItem(withTitle: "Undo", action: Selector(("undo:")), keyEquivalent: "z")
        let redo = edit.addItem(withTitle: "Redo", action: Selector(("redo:")), keyEquivalent: "z")
        redo.keyEquivalentModifierMask = [.command, .shift]
        edit.addItem(.separator())
        edit.addItem(withTitle: "Cut", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        edit.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        edit.addItem(withTitle: "Paste", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        edit.addItem(withTitle: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")

        let viewItem = NSMenuItem()
        main.addItem(viewItem)
        let view = NSMenu(title: "View")
        viewItem.submenu = view
        view.addItem(withTitle: "Reload", action: #selector(reloadPage), keyEquivalent: "r")
        view.addItem(withTitle: "Actual Size", action: #selector(zoomReset), keyEquivalent: "0")
        view.addItem(withTitle: "Zoom In", action: #selector(zoomIn), keyEquivalent: "+")
        view.addItem(withTitle: "Zoom Out", action: #selector(zoomOut), keyEquivalent: "-")

        let windowItem = NSMenuItem()
        main.addItem(windowItem)
        let winMenu = NSMenu(title: "Window")
        windowItem.submenu = winMenu
        winMenu.addItem(withTitle: "Minimize", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        winMenu.addItem(withTitle: "Zoom", action: #selector(NSWindow.performZoom(_:)), keyEquivalent: "")
        NSApp.windowsMenu = winMenu

        NSApp.mainMenu = main
    }

    @objc private func reloadPage() { webView.reload() }

    @objc private func zoomReset() { webView.pageZoom = 1.0 }
    @objc private func zoomIn() { webView.pageZoom = min(webView.pageZoom + 0.1, 3.0) }
    @objc private func zoomOut() { webView.pageZoom = max(webView.pageZoom - 0.1, 0.5) }

    // MARK: WKNavigationDelegate

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        lifecycle("page loaded: \(webView.url?.absoluteString ?? "?")")
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        // The page briefly fails while the server is still coming up; the retry
        // in waitForServer handles it, so ignore cancellations here.
        if (error as NSError).code == NSURLErrorCancelled { return }
        lifecycle("navigation failed: \(error.localizedDescription)")
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!,
                 withError error: Error) {
        if (error as NSError).code == NSURLErrorCancelled { return }
        lifecycle("provisional load failed: \(error.localizedDescription)")
        if !didShowError {
            showError("The interface could not be loaded.\n\n\(error.localizedDescription)")
        }
    }
}

dbg("bootstrap")
let app = NSApplication.shared
dbg("NSApplication.shared ok")
let delegate = AppDelegate()
app.delegate = delegate
dbg("delegate set")
app.setActivationPolicy(.regular)
dbg("activation policy ok")
app.run()
