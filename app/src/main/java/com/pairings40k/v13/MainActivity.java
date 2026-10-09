package com.pairings40k.v13;

import android.app.Activity;
import android.Manifest;
import android.content.pm.PackageManager;
import android.app.AlertDialog;
import android.app.DownloadManager;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Build;
import android.content.ContentValues;
import android.provider.MediaStore;
import android.util.Base64;
import android.webkit.JavascriptInterface;
import org.json.JSONObject;
import java.io.OutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import android.os.Bundle;
import android.os.Environment;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.view.inputmethod.InputMethodManager;
import android.content.Context;
import android.webkit.CookieManager;
import android.webkit.DownloadListener;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;
import android.webkit.URLUtil;

import java.util.ArrayList;

public class MainActivity extends Activity {
    private static final String PREFS = "pairings_settings";
    private static final String KEY_URL = "streamlit_url";
    private static final int FILE_PICKER_REQUEST = 4107;

    private LinearLayout root;
    private WebView webView;
    private ProgressBar progressBar;
    private TextView titleView;
    private ValueCallback<Uri[]> uploadMessage;
    private String appUrl = "";
    private String trustedHost = "";

    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Window window = getWindow();
        window.setStatusBarColor(Color.rgb(17, 24, 39));
        window.setNavigationBarColor(Color.rgb(17, 24, 39));
        appUrl = getPreferencesStore().getString(KEY_URL, "");
        trustedHost = Uri.parse(appUrl).getHost() == null ? "" : Uri.parse(appUrl).getHost();
        buildLayout();
        configureWebView();
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q
                && checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.WRITE_EXTERNAL_STORAGE}, 4108);
        }

        if (savedInstanceState != null && webView.restoreState(savedInstanceState) != null) {
            // Restore the WebView session when Android recreates the activity.
        } else if (!appUrl.isEmpty()) {
            webView.loadUrl(appUrl);
        } else {
            showUrlDialog(true);
        }
    }

    private SharedPreferences getPreferencesStore() {
        return getSharedPreferences(PREFS, MODE_PRIVATE);
    }

    private void buildLayout() {
        root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.rgb(248, 250, 252));

        LinearLayout toolbar = new LinearLayout(this);
        toolbar.setOrientation(LinearLayout.HORIZONTAL);
        toolbar.setGravity(Gravity.CENTER_VERTICAL);
        toolbar.setPadding(dp(12), dp(4), dp(8), dp(4));
        toolbar.setBackgroundColor(Color.rgb(17, 24, 39));

        titleView = new TextView(this);
        titleView.setText("40K Team Pairings");
        titleView.setTextColor(Color.WHITE);
        titleView.setTextSize(17);
        titleView.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        titleView.setSingleLine(true);
        toolbar.addView(titleView, new LinearLayout.LayoutParams(0, dp(48), 1f));

        Button backButton = makeToolbarButton("‹", "Volver");
        backButton.setOnClickListener(v -> {
            if (webView.canGoBack()) webView.goBack();
        });
        toolbar.addView(backButton, new LinearLayout.LayoutParams(dp(44), dp(44)));

        Button reloadButton = makeToolbarButton("↻", "Recargar");
        reloadButton.setOnClickListener(v -> {
            if (!appUrl.isEmpty()) webView.reload();
            else showUrlDialog(true);
        });
        toolbar.addView(reloadButton, new LinearLayout.LayoutParams(dp(44), dp(44)));

        Button settingsButton = makeToolbarButton("⚙", "Configurar URL");
        settingsButton.setOnClickListener(v -> showUrlDialog(false));
        toolbar.addView(settingsButton, new LinearLayout.LayoutParams(dp(44), dp(44)));

        root.addView(toolbar, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, dp(56)));

        progressBar = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progressBar.setMax(100);
        progressBar.setProgressTintList(android.content.res.ColorStateList.valueOf(Color.rgb(20, 184, 166)));
        progressBar.setIndeterminateTintList(android.content.res.ColorStateList.valueOf(Color.rgb(20, 184, 166)));
        root.addView(progressBar, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, dp(3)));

        webView = new WebView(this);
        webView.setBackgroundColor(Color.rgb(248, 250, 252));
        root.addView(webView, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));
        setContentView(root);
    }

    private Button makeToolbarButton(String label, String description) {
        Button button = new Button(this);
        button.setText(label);
        button.setTextColor(Color.WHITE);
        button.setTextSize(24);
        button.setAllCaps(false);
        button.setPadding(0, 0, 0, 0);
        button.setBackgroundColor(Color.TRANSPARENT);
        button.setContentDescription(description);
        return button;
    }

    private void configureWebView() {
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setLoadWithOverviewMode(true);
        settings.setUseWideViewPort(true);
        settings.setSupportZoom(true);
        settings.setBuiltInZoomControls(true);
        settings.setDisplayZoomControls(false);
        settings.setJavaScriptCanOpenWindowsAutomatically(false);
        settings.setSupportMultipleWindows(false);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(true);
        settings.setDefaultTextEncodingName("UTF-8");
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);

        CookieManager cookies = CookieManager.getInstance();
        cookies.setAcceptCookie(true);
        cookies.setAcceptThirdPartyCookies(webView, true);

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                String scheme = request.getUrl().getScheme();
                if ("http".equalsIgnoreCase(scheme) || "https".equalsIgnoreCase(scheme)) {
                    String targetHost = request.getUrl().getHost();
                    if (targetHost != null && targetHost.equalsIgnoreCase(trustedHost)) return false;
                    try {
                        startActivity(new Intent(Intent.ACTION_VIEW, request.getUrl()));
                    } catch (ActivityNotFoundException ex) {
                        Toast.makeText(MainActivity.this, "No hay una aplicación compatible con este enlace.", Toast.LENGTH_SHORT).show();
                    }
                    return true;
                }
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, request.getUrl()));
                } catch (ActivityNotFoundException ex) {
                    Toast.makeText(MainActivity.this, "No hay una aplicación compatible con este enlace.", Toast.LENGTH_SHORT).show();
                }
                return true;
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                CookieManager.getInstance().flush();
            }
        });

        webView.addJavascriptInterface(new BlobDownloadBridge(), "AndroidDownloadBridge");

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onProgressChanged(WebView view, int newProgress) {
                progressBar.setProgress(newProgress);
                progressBar.setVisibility(newProgress >= 100 ? View.GONE : View.VISIBLE);
            }

            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback,
                                             FileChooserParams fileChooserParams) {
                if (uploadMessage != null) uploadMessage.onReceiveValue(null);
                uploadMessage = callback;
                Intent intent = new Intent(Intent.ACTION_GET_CONTENT);
                intent.addCategory(Intent.CATEGORY_OPENABLE);
                intent.setType("*/*");
                if (fileChooserParams.getMode() == FileChooserParams.MODE_OPEN_MULTIPLE) {
                    intent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
                }
                try {
                    startActivityForResult(Intent.createChooser(intent, "Seleccionar archivo"), FILE_PICKER_REQUEST);
                } catch (ActivityNotFoundException e) {
                    uploadMessage = null;
                    Toast.makeText(MainActivity.this, "No se encuentra un selector de archivos.", Toast.LENGTH_SHORT).show();
                    return false;
                }
                return true;
            }
        });

        webView.setDownloadListener(new DownloadListener() {
            @Override
            public void onDownloadStart(String url, String userAgent, String contentDisposition,
                                        String mimeType, long contentLength) {
                startDownload(url, userAgent, contentDisposition, mimeType);
            }
        });
    }

    private void startDownload(String url, String userAgent, String contentDisposition, String mimeType) {
        if (url != null && url.startsWith("blob:")) {
            String filename = URLUtil.guessFileName(url, contentDisposition, mimeType);
            if (filename == null || filename.trim().isEmpty() || "downloadfile".equalsIgnoreCase(filename)) filename = "equipo-warhammer.json";
            String js = "(function(){var u=" + JSONObject.quote(url) + ";var n=" + JSONObject.quote(filename)
                    + ";var m=" + JSONObject.quote(mimeType == null ? "application/octet-stream" : mimeType)
                    + ";fetch(u).then(function(r){return r.blob();}).then(function(b){var f=new FileReader();f.onloadend=function(){var d=String(f.result).split(',')[1]||'';AndroidDownloadBridge.saveBlob(n,m,d);};f.readAsDataURL(b);}).catch(function(e){console.error('Download failed',e);});})();";
            webView.evaluateJavascript(js, null);
            Toast.makeText(this, "Preparando descarga…", Toast.LENGTH_SHORT).show();
            return;
        }
        if (url == null || !(url.startsWith("https://") || url.startsWith("http://"))) {
            Toast.makeText(this, "No se ha podido reconocer el enlace de descarga.", Toast.LENGTH_LONG).show();
            return;
        }
        try {
            String filename = URLUtil.guessFileName(url, contentDisposition, mimeType);
            DownloadManager.Request request = new DownloadManager.Request(Uri.parse(url));
            request.setTitle(filename);
            request.setDescription("Descarga de 40K Team Pairings");
            request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
            request.setAllowedOverMetered(true);
            request.setAllowedOverRoaming(false);
            request.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, filename);
            String cookie = CookieManager.getInstance().getCookie(url);
            if (cookie != null) request.addRequestHeader("Cookie", cookie);
            if (userAgent != null) request.addRequestHeader("User-Agent", userAgent);
            DownloadManager manager = (DownloadManager) getSystemService(DOWNLOAD_SERVICE);
            if (manager != null) {
                manager.enqueue(request);
                Toast.makeText(this, "Descarga iniciada: " + filename, Toast.LENGTH_SHORT).show();
            } else {
                Toast.makeText(this, "No se pudo iniciar la descarga.", Toast.LENGTH_SHORT).show();
            }
        } catch (Exception e) {
            Toast.makeText(this, "Error al iniciar la descarga: " + e.getMessage(), Toast.LENGTH_LONG).show();
        }
    }

    private void showUrlDialog(boolean firstRun) {
        final EditText input = new EditText(this);
        input.setSingleLine(true);
        input.setText(appUrl);
        input.setHint("https://tu-aplicacion.streamlit.app");
        input.setInputType(android.text.InputType.TYPE_CLASS_TEXT | android.text.InputType.TYPE_TEXT_VARIATION_URI);
        input.setSelectAllOnFocus(true);
        int pad = dp(20);
        LinearLayout holder = new LinearLayout(this);
        holder.setPadding(pad, dp(4), pad, 0);
        holder.addView(input, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(52)));

        AlertDialog dialog = new AlertDialog.Builder(this)
                .setTitle(firstRun ? "Conecta tu V13" : "Dirección de la aplicación")
                .setMessage("Pega la URL pública de tu aplicación Streamlit. Se guardará en esta tablet.")
                .setView(holder)
                .setPositiveButton("Guardar y abrir", null)
                .setNegativeButton(firstRun ? "Cancelar" : "Cerrar", (d, which) -> {
                    if (firstRun && appUrl.isEmpty()) {
                        Toast.makeText(this, "Configura la URL para utilizar la aplicación.", Toast.LENGTH_LONG).show();
                    }
                })
                .create();
        dialog.setOnShowListener(d -> dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
            String value = input.getText().toString().trim();
            if (value.isEmpty()) {
                input.setError("Introduce la URL de Streamlit");
                return;
            }
            if (!value.matches("(?i)^https?://.*")) value = "https://" + value;
            Uri parsed = Uri.parse(value);
            String scheme = parsed.getScheme();
            if (parsed.getHost() == null || !"https".equalsIgnoreCase(scheme)) {
                input.setError("Usa una dirección HTTPS válida, por ejemplo https://mi-app.streamlit.app");
                return;
            }
            appUrl = value;
            trustedHost = parsed.getHost();
            getPreferencesStore().edit().putString(KEY_URL, appUrl).apply();
            ((InputMethodManager) getSystemService(Context.INPUT_METHOD_SERVICE)).hideSoftInputFromWindow(input.getWindowToken(), 0);
            dialog.dismiss();
            webView.loadUrl(appUrl);
        }));
        dialog.show();
        dialog.getWindow().setSoftInputMode(android.view.WindowManager.LayoutParams.SOFT_INPUT_STATE_ALWAYS_HIDDEN);
    }


    private class BlobDownloadBridge {
        @JavascriptInterface
        public void saveBlob(String filename, String mimeType, String base64Data) {
            if (base64Data == null || base64Data.length() > 70_000_000) {
                runOnUiThread(() -> Toast.makeText(MainActivity.this, "El archivo es demasiado grande o está vacío.", Toast.LENGTH_LONG).show());
                return;
            }
            OutputStream output = null;
            try {
                byte[] bytes = Base64.decode(base64Data, Base64.DEFAULT);
                String cleanName = filename == null ? "equipo-warhammer.json" : new File(filename).getName();
                if (cleanName.isEmpty() || ".".equals(cleanName) || "..".equals(cleanName)) cleanName = "equipo-warhammer.json";
                String contentType = (mimeType == null || mimeType.trim().isEmpty()) ? "application/octet-stream" : mimeType;
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    ContentValues values = new ContentValues();
                    values.put(MediaStore.MediaColumns.DISPLAY_NAME, cleanName);
                    values.put(MediaStore.MediaColumns.MIME_TYPE, contentType);
                    values.put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS);
                    Uri destination = getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values);
                    if (destination == null) throw new IllegalStateException("No se pudo crear el archivo en Descargas");
                    output = getContentResolver().openOutputStream(destination);
                } else {
                    File directory = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS);
                    if (!directory.exists() && !directory.mkdirs()) throw new IllegalStateException("No se pudo acceder a Descargas");
                    output = new FileOutputStream(new File(directory, cleanName));
                }
                if (output == null) throw new IllegalStateException("No se pudo abrir el archivo de destino");
                output.write(bytes);
                output.flush();
                output.close();
                output = null;
                final String savedFilename = cleanName;
                runOnUiThread(() -> Toast.makeText(MainActivity.this, "Guardado en Descargas: " + savedFilename, Toast.LENGTH_LONG).show());
            } catch (Exception e) {
                final String message = e.getMessage() == null ? "error de escritura" : e.getMessage();
                runOnUiThread(() -> Toast.makeText(MainActivity.this, "Error al guardar: " + message, Toast.LENGTH_LONG).show());
            } finally {
                if (output != null) try { output.close(); } catch (Exception ignored) { }
            }
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == FILE_PICKER_REQUEST) {
            if (uploadMessage == null) return;
            Uri[] results = null;
            if (resultCode == RESULT_OK && data != null) {
                if (data.getClipData() != null) {
                    int count = data.getClipData().getItemCount();
                    results = new Uri[count];
                    for (int i = 0; i < count; i++) results[i] = data.getClipData().getItemAt(i).getUri();
                } else if (data.getData() != null) {
                    results = new Uri[]{data.getData()};
                }
            }
            uploadMessage.onReceiveValue(results);
            uploadMessage = null;
        }
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        if (webView != null) webView.saveState(outState);
        super.onSaveInstanceState(outState);
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
