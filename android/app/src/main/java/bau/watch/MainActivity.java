package bau.watch;

import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

/**
 * BAU Watch (docs/TABLET.md, the owner's ask 2026-11-24): watch the operations world, the AI
 * workstation and the live task board on a tablet, and answer Jarvis's cards there (Accept /
 * Not now, the Inbox: his own page, behind his key). It reaches Jarvis only through the SSH
 * tunnel BAU allows for a station ({@link Tunnel}); it shows Jarvis's own pages and opens
 * nothing else.
 */
public class MainActivity extends Activity {
    static final String[][] VIEWS = {
        {"World", "/#world"}, {"Workstation", "/workstation"}, {"Tasks", "/watch"},
        {"Jarvis", "/"}};
    static final int BG = Color.rgb(8, 11, 18);
    static final int INK = Color.rgb(220, 231, 247);
    static final int DIM = Color.rgb(135, 151, 174);
    static final int CYAN = Color.rgb(63, 214, 255);

    private SharedPreferences prefs;
    private final Handler ui = new Handler(Looper.getMainLooper());
    private volatile Tunnel tunnel;
    private volatile boolean watching;
    private WebView web;
    private TextView status;

    @Override
    protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        prefs = getSharedPreferences("bau-watch", Context.MODE_PRIVATE);
        if (paired()) {
            showWatch();
        } else {
            showSetup();
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (watching && (tunnel == null || !tunnel.isConnected())) {
            connect();
        }
    }

    @Override
    protected void onDestroy() {
        watching = false;
        Tunnel t = tunnel;
        tunnel = null;
        if (t != null) {
            new Thread(t::close).start();
        }
        super.onDestroy();
    }

    private boolean paired() {
        return prefs.getString("pin", null) != null && prefs.getString("host", null) != null
                && prefs.getString("user", null) != null && prefs.getString("priv", null) != null;
    }

    // ------------------------------------------------------------------ pairing

    private void showSetup() {
        watching = false;
        LinearLayout col = column();
        col.addView(text("BAU Watch", 24, CYAN));
        col.addView(text("Watch Jarvis's world, the workstation and the task board. This tablet "
                + "reaches the laptop through an encrypted tunnel that can open Jarvis's screens "
                + "and nothing else. Home Wi-Fi only.", 15, DIM));

        col.addView(text("1. Allow this tablet on the laptop", 18, INK));
        String pub = key();
        String line = "sudo bau hq allow \"" + pub + "\"";
        TextView cmd = text(line, 13, INK);
        cmd.setTextIsSelectable(true);
        cmd.setBackgroundColor(Color.rgb(14, 20, 32));
        cmd.setPadding(18, 18, 18, 18);
        col.addView(cmd);
        col.addView(button("Copy the line", v -> {
            ClipboardManager cb = (ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
            cb.setPrimaryClip(ClipData.newPlainText("bau hq allow", line));
            toast("Copied. Send it to yourself and type it in the laptop's terminal.");
        }));

        col.addView(text("2. The laptop", 18, INK));
        EditText host = field("Laptop address, e.g. 192.168.1.20", prefs.getString("host", ""));
        EditText user = field("Your login name on the laptop", prefs.getString("user", ""));
        col.addView(host);
        col.addView(user);
        TextView said = text("", 15, INK);
        LinearLayout confirm = new LinearLayout(this);
        confirm.setOrientation(LinearLayout.HORIZONTAL);
        confirm.setVisibility(View.GONE);
        col.addView(button("Check the laptop", v -> {
            String h = host.getText().toString().trim();
            String u = user.getText().toString().trim();
            if (h.isEmpty() || u.isEmpty()) {
                said.setText("Type the laptop's address and your login name first.");
                return;
            }
            said.setText("Asking the laptop for its key…");
            confirm.setVisibility(View.GONE);
            new Thread(() -> {
                try {
                    String fp = Tunnel.hostKey(h, 22);
                    ui.post(() -> {
                        said.setText("The laptop's key is\n\n" + fp + "\n\nOn the laptop, type:\n"
                                + "sudo ssh-keygen -lf /etc/ssh/ssh_host_ecdsa_key.pub\n"
                                + "and compare. Only press \"It matches\" if every character "
                                + "is the same.");
                        confirm.removeAllViews();
                        confirm.addView(button("It matches", b -> {
                            prefs.edit().putString("host", h).putString("user", u)
                                    .putString("pin", fp).apply();
                            showWatch();
                        }));
                        confirm.addView(button("It does not match", b -> {
                            said.setText("Not trusted. Check the address: this is not your "
                                    + "laptop, or someone is in between.");
                            confirm.setVisibility(View.GONE);
                        }));
                        confirm.setVisibility(View.VISIBLE);
                    });
                } catch (Exception e) {
                    ui.post(() -> said.setText("The laptop did not answer: " + e.getMessage()
                            + "\nIs it on, on the same Wi-Fi, with sudo bau hq on done?"));
                }
            }).start();
        }));
        col.addView(said);
        col.addView(confirm);
        setContentView(scroll(col));
    }

    /** This tablet's key, made once and kept in the app's private storage. */
    private String key() {
        String pub = prefs.getString("pub", null);
        if (pub == null) {
            try {
                String[] k = Tunnel.newKey("bau-watch-" + android.os.Build.MODEL
                        .replaceAll("[^A-Za-z0-9.-]", "").toLowerCase());
                prefs.edit().putString("priv", k[0]).putString("pub", k[1]).apply();
                pub = k[1];
            } catch (Exception e) {
                return "(could not make a key: " + e.getMessage() + ")";
            }
        }
        return pub;
    }

    // ------------------------------------------------------------------ watching

    private void showWatch() {
        watching = true;
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(BG);
        web = new WebView(this);
        WebSettings ws = web.getSettings();
        ws.setJavaScriptEnabled(true);           // Jarvis's pages draw with JavaScript
        ws.setDomStorageEnabled(true);
        ws.setAllowFileAccess(false);
        ws.setAllowContentAccess(false);
        web.setBackgroundColor(BG);
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r) {
                return !local(r.getUrl());      // only the tunnel's own end, never the web
            }
        });
        root.addView(web, new FrameLayout.LayoutParams(-1, -1));

        LinearLayout bar = new LinearLayout(this);
        bar.setOrientation(LinearLayout.HORIZONTAL);
        bar.setGravity(Gravity.CENTER_VERTICAL);
        bar.setBackgroundColor(Color.argb(200, 8, 11, 18));
        bar.setPadding(12, 6, 12, 6);
        for (String[] v : VIEWS) {
            bar.addView(button(v[0], b -> {
                prefs.edit().putString("view", v[1]).apply();
                load();
            }));
        }
        status = text("connecting…", 13, DIM);
        status.setPadding(18, 0, 18, 0);
        bar.addView(status, new LinearLayout.LayoutParams(0, -2, 1));
        bar.addView(button("Pair again", b -> {
            prefs.edit().remove("pin").apply();
            showSetup();
        }));
        FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM);
        root.addView(bar, lp);
        setContentView(root);
        connect();
        ui.postDelayed(this::watchdog, 15000);
    }

    private boolean local(Uri u) {
        Tunnel t = tunnel;
        return t != null && "127.0.0.1".equals(u.getHost()) && u.getPort() == t.localPort();
    }

    private void load() {
        Tunnel t = tunnel;
        if (t == null || web == null) {
            return;
        }
        String page = prefs.getString("view", "/#world");
        String hash = page.contains("#") ? page.substring(page.indexOf('#')) : "";
        String path = page.contains("#") ? page.substring(0, page.indexOf('#')) : page;
        web.loadUrl(t.url(path) + hash);
    }

    private void connect() {
        if (status != null) {
            status.setText("connecting to " + prefs.getString("host", "") + "…");
        }
        new Thread(() -> {
            Tunnel old = tunnel;
            tunnel = null;
            if (old != null) {
                old.close();
            }
            try {
                Tunnel t = Tunnel.open(prefs.getString("host", ""), 22,
                        prefs.getString("user", ""), prefs.getString("priv", ""),
                        prefs.getString("pub", ""), prefs.getString("pin", null));
                if (!watching) {
                    t.close();
                    return;
                }
                tunnel = t;
                ui.post(() -> {
                    status.setText("live · " + prefs.getString("host", ""));
                    load();
                });
            } catch (Exception e) {
                ui.post(() -> {
                    if (status != null) {
                        status.setText("not connected: " + e.getMessage() + " · retrying");
                    }
                });
            }
        }).start();
    }

    /** Every 15 s: a dropped tunnel (Wi-Fi gone, laptop restarted) comes back by itself. */
    private void watchdog() {
        if (!watching) {
            return;
        }
        Tunnel t = tunnel;
        if (t == null || !t.isConnected()) {
            connect();
        }
        ui.postDelayed(this::watchdog, 15000);
    }

    // ------------------------------------------------------------------ small parts

    private LinearLayout column() {
        LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        col.setBackgroundColor(BG);
        col.setPadding(48, 48, 48, 48);
        return col;
    }

    private ScrollView scroll(View v) {
        ScrollView s = new ScrollView(this);
        s.setBackgroundColor(BG);
        s.addView(v);
        return s;
    }

    private TextView text(String s, int sp, int color) {
        TextView t = new TextView(this);
        t.setText(s);
        t.setTextSize(sp);
        t.setTextColor(color);
        t.setPadding(0, 12, 0, 12);
        return t;
    }

    private EditText field(String hint, String value) {
        EditText e = new EditText(this);
        e.setHint(hint);
        e.setText(value);
        e.setSingleLine(true);
        e.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
        e.setTextColor(INK);
        e.setHintTextColor(DIM);
        return e;
    }

    private Button button(String label, View.OnClickListener on) {
        Button b = new Button(this);
        b.setText(label);
        b.setAllCaps(false);
        b.setOnClickListener(on);
        b.setLayoutParams(new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT,
                ViewGroup.LayoutParams.WRAP_CONTENT));
        return b;
    }

    private void toast(String s) {
        android.widget.Toast.makeText(this, s, android.widget.Toast.LENGTH_LONG).show();
    }
}
