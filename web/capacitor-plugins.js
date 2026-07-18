// Capacitor plugin loader — no bundler needed.
// In the Capacitor webview, window.Capacitor is injected by the native bridge
// before any page scripts run. Plugins register via Capacitor.registerPlugin().
// In a plain browser, stubs are provided so app.js loads without errors.
(function () {
  var C = window.Capacitor;

  if (!C) {
    // Plain browser — stub out plugin APIs. All native calls are gated behind
    // isNative which returns false when Capacitor isn't present.
    var noop = function () { return Promise.resolve(); };
    window.__pwcPlugins = {
      Capacitor: { isNativePlatform: function () { return false; } },
      StatusBar: { setStyle: noop, setBackgroundColor: noop, hide: noop, show: noop },
      Style: { Dark: 'DARK', Light: 'LIGHT', Default: 'DEFAULT' },
      SplashScreen: { hide: noop, show: noop },
      Keyboard: { setAccessoryBarVisible: noop, setStyle: noop, hide: noop, show: noop },
      App: { addListener: function () {}, minimizeApp: function () { return Promise.resolve(); } },
      Preferences: { get: function () { return Promise.resolve({ value: null }); }, set: noop, remove: noop },
      Browser: { open: noop, close: noop },
      Network: { getStatus: function () { return Promise.resolve({ connected: true }); }, addListener: function () {} },
    };
    return;
  }

  // Native Capacitor webview — plugins are auto-registered by the native
  // bridge in Capacitor v8+. They live on Capacitor.Plugins.
  var P = C.Plugins || {};

  window.__pwcPlugins = {
    Capacitor: C,
    StatusBar: P.StatusBar,
    Style: { Dark: 'DARK', Light: 'LIGHT', Default: 'DEFAULT' },
    SplashScreen: P.SplashScreen,
    Keyboard: P.Keyboard,
    App: P.App,
    Preferences: P.Preferences,
    Browser: P.Browser,
    Network: P.Network,
  };
})();
