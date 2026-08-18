/**
 * Window-bridge globals for the Capacitor shell (#147).
 *
 * capacitor-plugins.js installs `__pwcPlugins` (real plugin proxies in the
 * native webview, no-op stubs in a plain browser); app.js reads offline
 * state and the last-route hook from `__pwcOffline` / `__pwcLastRoute`.
 * Declared once here so checkJs stops treating them as unknown window props.
 */

/** The plugin surface app.js actually calls. */
interface PwcPlugins {
  Capacitor: { isNativePlatform?: () => boolean };
  StatusBar: {
    setStyle(opts: unknown): Promise<void>;
    setBackgroundColor(opts: unknown): Promise<void>;
    hide(): Promise<void>;
    show(): Promise<void>;
  };
  Style: { Dark: string; Light: string; Default: string };
  SplashScreen: { hide(): Promise<void>; show(): Promise<void> };
  Keyboard: {
    setAccessoryBarVisible(opts: { isVisible: boolean }): Promise<void>;
    setStyle(opts: unknown): Promise<void>;
    hide(): Promise<void>;
    show(): Promise<void>;
  };
  App: {
    addListener(event: 'backButton', cb: (info: { canGoBack: boolean }) => void): unknown;
    minimizeApp(): Promise<void>;
  };
  Preferences: {
    get(opts: { key: string }): Promise<{ value: string | null }>;
    set(opts: { key: string; value: string }): Promise<void>;
    remove(opts: { key: string }): Promise<void>;
  };
  Browser: { open(opts: { url: string }): Promise<void>; close(): Promise<void> };
  Network: {
    getStatus(): Promise<{ connected: boolean }>;
    addListener(event: 'networkStatusChange', cb: (s: { connected: boolean }) => void): unknown;
  };
}

interface Window {
  Capacitor?: { isNativePlatform?: () => boolean; Plugins?: Partial<PwcPlugins> };
  __pwcPlugins: PwcPlugins;
  __pwcOffline: boolean;
  __pwcLastRoute?: string;
}
