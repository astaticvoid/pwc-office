// Capacitor plugin entry point — bundled by esbuild into capacitor-plugins.js
// In the Capacitor webview, Capacitor core is available as a global.
// Plugins register themselves on the Capacitor global when loaded.
import { Capacitor } from '@capacitor/core';
import { StatusBar, Style } from '@capacitor/status-bar';
import { SplashScreen } from '@capacitor/splash-screen';
import { Keyboard } from '@capacitor/keyboard';
import { App } from '@capacitor/app';
import { Preferences } from '@capacitor/preferences';
import { Browser } from '@capacitor/browser';
import { Network } from '@capacitor/network';

window.__pwcPlugins = {
  Capacitor, StatusBar, Style, SplashScreen,
  Keyboard, App, Preferences, Browser, Network,
};
