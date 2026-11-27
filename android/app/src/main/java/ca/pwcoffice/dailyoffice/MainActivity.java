package ca.pwcoffice.dailyoffice;

import android.graphics.Color;
import android.os.Build;
import android.os.Bundle;
import android.os.Looper;
import android.view.View;
import android.view.WindowManager;
import android.webkit.WebView;
import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.core.view.WindowInsetsControllerCompat;
import com.getcapacitor.BridgeActivity;
import com.getcapacitor.WebViewListener;
import java.util.Locale;

public class MainActivity extends BridgeActivity {
    private int[] safeAreaDp = new int[] { 0, 0, 0, 0 };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        WindowCompat.setDecorFitsSystemWindows(getWindow(), false);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && Build.VERSION.SDK_INT < Build.VERSION_CODES.VANILLA_ICE_CREAM) {
            getWindow().setNavigationBarColor(Color.TRANSPARENT);
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P && Build.VERSION.SDK_INT < Build.VERSION_CODES.VANILLA_ICE_CREAM) {
            WindowManager.LayoutParams lp = getWindow().getAttributes();
            lp.layoutInDisplayCutoutMode = WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES;
            getWindow().setAttributes(lp);
        }

        View decorView = getWindow().getDecorView();
        WindowInsetsControllerCompat insetsController =
            WindowCompat.getInsetsController(getWindow(), decorView);
        // Header bar is always dark (#15382A light theme, #0F1A14 dark theme), so keep status bar icons white.
        // Initial WebView background is light parchment (#F4EEDF), so keep nav bar icons dark until JS syncs theme.
        insetsController.setAppearanceLightStatusBars(false);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            insetsController.setAppearanceLightNavigationBars(true);
        }

        ViewCompat.setOnApplyWindowInsetsListener(decorView, (v, insets) -> {
            Insets sysBars = insets.getInsets(
                WindowInsetsCompat.Type.systemBars() | WindowInsetsCompat.Type.displayCutout()
            );
            Insets ime = insets.getInsets(WindowInsetsCompat.Type.ime());
            boolean imeVisible = insets.isVisible(WindowInsetsCompat.Type.ime());

            // Keep top/left/right 0 so the WebView extends behind the status bar; only pad bottom for IME.
            v.setPadding(0, 0, 0, imeVisible ? ime.bottom : 0);

            int bottomInsetPx = imeVisible ? Math.max(0, sysBars.bottom - ime.bottom) : sysBars.bottom;
            float density = getResources().getDisplayMetrics().density;
            safeAreaDp = new int[] {
                (int) Math.ceil(sysBars.top / density),
                (int) Math.ceil(sysBars.right / density),
                (int) Math.ceil(bottomInsetPx / density),
                (int) Math.ceil(sysBars.left / density),
            };
            injectSafeAreaVars();

            return new WindowInsetsCompat.Builder(insets)
                .setInsets(
                    WindowInsetsCompat.Type.systemBars() | WindowInsetsCompat.Type.displayCutout(),
                    Insets.of(0, 0, 0, 0)
                )
                .build();
        });

        if (getBridge() != null) {
            // Re-apply after SystemBars.initSystemBars() queued Runnable so light status icons do not flash dark.
            getBridge().executeOnMainThread(() -> insetsController.setAppearanceLightStatusBars(false));
            getBridge().addWebViewListener(new WebViewListener() {
                @Override
                public void onPageCommitVisible(WebView view, String url) {
                    injectSafeAreaVars();
                }

                @Override
                public void onPageLoaded(WebView view) {
                    injectSafeAreaVars();
                }
            });
        }

        ViewCompat.requestApplyInsets(decorView);
    }

    private void injectSafeAreaVars() {
        if (isFinishing() || isDestroyed() || getBridge() == null) return;
        WebView webView = getBridge().getWebView();
        if (webView == null) return;
        final String js = String.format(
            Locale.US,
            "try{var s=document.documentElement.style;" +
            "s.setProperty('--safe-area-inset-top','%dpx');" +
            "s.setProperty('--safe-area-inset-right','%dpx');" +
            "s.setProperty('--safe-area-inset-bottom','%dpx');" +
            "s.setProperty('--safe-area-inset-left','%dpx');" +
            "}catch(e){}",
            safeAreaDp[0], safeAreaDp[1], safeAreaDp[2], safeAreaDp[3]
        );
        if (Looper.myLooper() == Looper.getMainLooper()) {
            webView.evaluateJavascript(js, null);
        } else {
            getBridge().executeOnMainThread(() -> {
                if (!isFinishing() && !isDestroyed() && getBridge() != null && getBridge().getWebView() != null) {
                    getBridge().getWebView().evaluateJavascript(js, null);
                }
            });
        }
    }
}
