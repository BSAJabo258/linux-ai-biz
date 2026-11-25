package bau.watch;

import com.jcraft.jsch.ChannelExec;
import com.jcraft.jsch.HostKey;
import com.jcraft.jsch.HostKeyRepository;
import com.jcraft.jsch.JSch;
import com.jcraft.jsch.JSchException;
import com.jcraft.jsch.KeyPair;
import com.jcraft.jsch.Session;
import com.jcraft.jsch.UserInfo;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * The tablet's one way in to Jarvis (docs/TABLET.md): an SSH tunnel to the laptop that BAU
 * already allows for a station (src/bau/station.py, {@code bau hq allow}). The laptop lets this
 * key do two things only: forward to Jarvis's port 127.0.0.1:8766, and run {@code bau jarvis
 * url}, which prints Jarvis's address with his key. No shell, no other port.
 *
 * <p>The laptop's host key is shown to the owner and pinned before the first sign-in
 * ({@link #hostKey}); a different key later is refused. ECDSA P-256 keys and key exchange are
 * preferred: Android's own crypto has them on every version this app supports.
 */
public final class Tunnel implements AutoCloseable {
    public static final int JARVIS_PORT = 8766;
    static final Pattern URL_KEY = Pattern.compile("http://127\\.0\\.0\\.1:\\d+/\\?k=([A-Za-z0-9_-]{16,})");
    static final String HOST_KEYS = "ecdsa-sha2-nistp256,rsa-sha2-512,rsa-sha2-256";
    static final String KEX = "ecdh-sha2-nistp256,ecdh-sha2-nistp384,diffie-hellman-group14-sha256";

    private final Session session;
    private final int localPort;
    private final String jarvisKey;

    private Tunnel(Session session, int localPort, String jarvisKey) {
        this.session = session;
        this.localPort = localPort;
        this.jarvisKey = jarvisKey;
    }

    /** A new key for this tablet: [0] the private key (PEM), [1] its public line for the laptop. */
    public static String[] newKey(String comment) throws JSchException {
        KeyPair kp = KeyPair.genKeyPair(new JSch(), KeyPair.ECDSA, 256);
        ByteArrayOutputStream priv = new ByteArrayOutputStream();
        ByteArrayOutputStream pub = new ByteArrayOutputStream();
        kp.writePrivateKey(priv);
        kp.writePublicKey(pub, comment);
        kp.dispose();
        return new String[] {priv.toString(StandardCharsets.US_ASCII).trim(),
                pub.toString(StandardCharsets.US_ASCII).trim()};
    }

    /** OpenSSH's fingerprint of a host key blob, as {@code ssh-keygen -lf} prints it. */
    public static String fingerprint(byte[] blob) {
        try {
            byte[] d = MessageDigest.getInstance("SHA-256").digest(blob);
            return "SHA256:" + Base64.getEncoder().withoutPadding().encodeToString(d);
        } catch (java.security.NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }

    /** Jarvis's key from what {@code bau jarvis url} printed, or null. */
    public static String keyFrom(String printed) {
        Matcher m = URL_KEY.matcher(printed == null ? "" : printed);
        return m.find() ? m.group(1) : null;
    }

    /**
     * The laptop's host key fingerprint, read without signing in, for the owner to compare
     * with what the laptop prints. Nothing is trusted yet.
     */
    public static String hostKey(String host, int port) throws JSchException {
        Pin pin = new Pin(null);
        Session s = session(new JSch(), host, port, "bau-watch", pin);
        try {
            s.connect(15000);
        } catch (JSchException e) {
            if (pin.seen == null) {
                throw e;            // never got as far as the host key: the laptop is not there
            }
        } finally {
            s.disconnect();
        }
        return pin.seen;
    }

    /**
     * Signs in with this tablet's key, checks the laptop's key against the pinned
     * fingerprint, reads Jarvis's key and opens the local end of the tunnel.
     */
    public static Tunnel open(String host, int port, String user, String privateKeyPem,
                              String publicKeyLine, String pinnedFingerprint) throws JSchException {
        if (pinnedFingerprint == null || !pinnedFingerprint.startsWith("SHA256:")) {
            throw new JSchException("the laptop's key is not confirmed yet");
        }
        JSch jsch = new JSch();
        jsch.addIdentity("bau-watch", privateKeyPem.getBytes(StandardCharsets.US_ASCII),
                publicKeyLine.getBytes(StandardCharsets.US_ASCII), null);
        Pin pin = new Pin(pinnedFingerprint);
        Session s = session(jsch, host, port, user, pin);
        s.setConfig("PreferredAuthentications", "publickey");
        s.setServerAliveInterval(15000);
        s.connect(15000);
        try {
            String key = keyFrom(run(s));
            if (key == null) {
                throw new JSchException("the laptop did not print Jarvis's address: is "
                        + "Jarvis running there (sudo bau hq on)?");
            }
            int local = s.setPortForwardingL("127.0.0.1", 0, "127.0.0.1", JARVIS_PORT);
            return new Tunnel(s, local, key);
        } catch (JSchException e) {
            s.disconnect();
            throw e;
        }
    }

    private static Session session(JSch jsch, String host, int port, String user, Pin pin)
            throws JSchException {
        jsch.setHostKeyRepository(pin);
        Session s = jsch.getSession(user, host, port);
        s.setConfig("StrictHostKeyChecking", "yes");
        s.setConfig("server_host_key", HOST_KEYS);
        s.setConfig("kex", KEX);
        s.setUserInfo(new Quiet());
        return s;
    }

    /** The forced command runs whatever is asked; its output holds Jarvis's address. */
    private static String run(Session s) throws JSchException {
        ChannelExec ch = (ChannelExec) s.openChannel("exec");
        ch.setCommand("bau jarvis url");
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        try {
            InputStream in = ch.getInputStream();
            ch.connect(15000);
            byte[] buf = new byte[4096];
            long until = System.currentTimeMillis() + 15000;
            int n;
            while ((n = in.read(buf)) >= 0 && out.size() < 65536) {
                out.write(buf, 0, n);
                if (System.currentTimeMillis() > until) {
                    break;
                }
            }
        } catch (java.io.IOException e) {
            throw new JSchException("reading Jarvis's address failed: " + e.getMessage());
        } finally {
            ch.disconnect();
        }
        return out.toString(StandardCharsets.UTF_8);
    }

    public int localPort() {
        return localPort;
    }

    public String jarvisKey() {
        return jarvisKey;
    }

    /** The address to open on this tablet: the tunnel's local end, with Jarvis's key. */
    public String url(String page) {
        return "http://127.0.0.1:" + localPort + page + (page.contains("?") ? "&" : "?")
                + "k=" + jarvisKey;
    }

    public boolean isConnected() {
        return session.isConnected();
    }

    @Override
    public void close() {
        session.disconnect();
    }

    /** Accepts only the pinned host key; remembers what it saw for {@link #hostKey}. */
    static final class Pin implements HostKeyRepository {
        final String pinned;
        String seen;

        Pin(String pinned) {
            this.pinned = pinned;
        }

        @Override
        public int check(String host, byte[] key) {
            seen = fingerprint(key);
            return pinned != null && pinned.equals(seen) ? OK : (pinned == null ? NOT_INCLUDED : CHANGED);
        }

        @Override public void add(HostKey hostkey, UserInfo ui) { }
        @Override public void remove(String host, String type) { }
        @Override public void remove(String host, String type, byte[] key) { }
        @Override public String getKnownHostsRepositoryID() { return "bau-watch-pin"; }
        @Override public HostKey[] getHostKey() { return new HostKey[0]; }
        @Override public HostKey[] getHostKey(String host, String type) { return new HostKey[0]; }
    }

    /** No questions: nothing is ever accepted by answering yes. */
    static final class Quiet implements UserInfo {
        @Override public String getPassphrase() { return null; }
        @Override public String getPassword() { return null; }
        @Override public boolean promptPassword(String message) { return false; }
        @Override public boolean promptPassphrase(String message) { return false; }
        @Override public boolean promptYesNo(String message) { return false; }
        @Override public void showMessage(String message) { }
    }
}
