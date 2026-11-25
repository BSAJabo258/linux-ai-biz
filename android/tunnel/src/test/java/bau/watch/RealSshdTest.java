package bau.watch;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

import com.jcraft.jsch.ChannelExec;
import com.jcraft.jsch.JSch;
import com.jcraft.jsch.JSchException;
import com.jcraft.jsch.Session;

import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.ServerSocket;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

/**
 * Against a real OpenSSH server, with the exact authorized_keys line BAU writes for a station
 * (src/bau/station.py key_line, made by BAU itself) and the real {@code bau jarvis url}: the
 * tunnel reaches Jarvis's port, a shell and every other port are refused, and a laptop whose
 * key changed is refused. Runs only with BAU_SSHD_TEST=1 (needs sshd, root and BAU).
 */
class RealSshdTest {
    static Process sshd;
    static Process jarvis;
    static Process other;
    static Path dir;
    static int port;
    static String[] key;
    static String hostFp;
    static final String USER = System.getProperty("user.name");

    @BeforeAll
    static void start() throws Exception {
        assumeTrue("1".equals(System.getenv("BAU_SSHD_TEST")), "BAU_SSHD_TEST=1 not set");
        dir = Files.createTempDirectory("bau-sshd");
        run("ssh-keygen", "-q", "-t", "ecdsa", "-b", "256", "-N", "", "-f", dir.resolve("host").toString());
        key = Tunnel.newKey("bau-watch-test");
        Files.writeString(dir.resolve("tablet.pub"), key[1] + "\n");
        // BAU's own line for a station key: restrict, permitopen Jarvis only, forced command
        String line = run("python3", "-c", "import sys; from bau.station import key_line; "
                + "print(key_line(open(sys.argv[1]).read()))", dir.resolve("tablet.pub").toString()).trim();
        assertTrue(line.startsWith("restrict,port-forwarding,permitopen=\"127.0.0.1:8766\""), line);
        Files.writeString(dir.resolve("authorized_keys"), line + "\n");
        port = free();
        Files.writeString(dir.resolve("sshd_config"), String.join("\n",
                "Port " + port, "ListenAddress 127.0.0.1", "HostKey " + dir.resolve("host"),
                "AuthorizedKeysFile " + dir.resolve("authorized_keys"),
                "StrictModes no", "PidFile " + dir.resolve("pid"), "UsePAM no",
                "PermitRootLogin prohibit-password", "PasswordAuthentication no",
                "KbdInteractiveAuthentication no", "AllowTcpForwarding local",
                "AllowStreamLocalForwarding no", "X11Forwarding no", "PermitTunnel no",
                "GatewayPorts no", "") + "\n");
        Files.createDirectories(Path.of("/run/sshd"));
        sshd = new ProcessBuilder("/usr/sbin/sshd", "-D", "-e", "-f", dir.resolve("sshd_config").toString())
                .redirectErrorStream(true).redirectOutput(dir.resolve("sshd.log").toFile()).start();
        // Jarvis's port answers with a page; another local port the tunnel must never reach
        jarvis = http(8766, "jarvis-page");
        other = http(free(), "secret");
        Thread.sleep(1500);
        hostFp = run("ssh-keygen", "-lf", dir.resolve("host.pub").toString()).split(" ")[1];
    }

    @AfterAll
    static void stop() {
        for (Process p : new Process[] {sshd, jarvis, other}) {
            if (p != null) {
                p.destroy();
            }
        }
    }

    @Test
    void theOwnerSeesTheSameFingerprintTheLaptopPrints() throws Exception {
        assertEquals(hostFp, Tunnel.hostKey("127.0.0.1", port));
    }

    @Test
    void theTunnelOpensJarvisAndNothingElse() throws Exception {
        try (Tunnel t = Tunnel.open("127.0.0.1", port, USER, key[0], key[1], hostFp)) {
            assertTrue(t.jarvisKey().length() >= 16);
            assertEquals("jarvis-page", get(t.url("/")));
        }
    }

    @Test
    void aShellOrAnyOtherCommandOnlyGetsJarvisAddress() throws Exception {
        Session s = signIn();
        try {
            ChannelExec ch = (ChannelExec) s.openChannel("exec");
            ch.setCommand("id; cat /etc/shadow");
            InputStream in = ch.getInputStream();
            ch.connect(10000);
            String out = new String(in.readAllBytes(), StandardCharsets.UTF_8);
            assertTrue(out.contains("http://127.0.0.1:8766/?k="), out);
            assertTrue(!out.contains("uid=") && !out.contains("root:"), out);
        } finally {
            s.disconnect();
        }
    }

    @Test
    void everyOtherPortIsRefused() throws Exception {
        Session s = signIn();
        try {
            int otherPort = Integer.parseInt(Files.readString(dir.resolve("other.port")).trim());
            int local = s.setPortForwardingL("127.0.0.1", 0, "127.0.0.1", otherPort);
            assertThrows(IOException.class, () -> get("http://127.0.0.1:" + local + "/"));
        } finally {
            s.disconnect();
        }
    }

    @Test
    void aLaptopWithAnotherKeyIsRefused() {
        assertThrows(JSchException.class, () -> Tunnel.open("127.0.0.1", port, USER, key[0], key[1],
                "SHA256:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"));
    }

    @Test
    void anotherTabletKeyIsRefused() throws Exception {
        String[] stranger = Tunnel.newKey("stranger");
        assertNotEquals(stranger[1], key[1]);
        assertThrows(JSchException.class,
                () -> Tunnel.open("127.0.0.1", port, USER, stranger[0], stranger[1], hostFp));
    }

    static Session signIn() throws JSchException {
        JSch j = new JSch();
        j.addIdentity("t", key[0].getBytes(StandardCharsets.US_ASCII),
                key[1].getBytes(StandardCharsets.US_ASCII), null);
        j.setHostKeyRepository(new Tunnel.Pin(hostFp));
        Session s = j.getSession(USER, "127.0.0.1", port);
        s.setConfig("StrictHostKeyChecking", "yes");
        s.setConfig("server_host_key", Tunnel.HOST_KEYS);
        s.setConfig("kex", Tunnel.KEX);
        s.connect(10000);
        return s;
    }

    static String get(String url) throws IOException {
        HttpURLConnection c = (HttpURLConnection) URI.create(url).toURL().openConnection();
        c.setConnectTimeout(5000);
        c.setReadTimeout(5000);
        try (InputStream in = c.getInputStream()) {
            return new String(in.readAllBytes(), StandardCharsets.UTF_8).trim();
        }
    }

    static Process http(int p, String body) throws IOException {
        Path root = Files.createDirectories(dir.resolve("www-" + p));
        Files.writeString(root.resolve("index.html"), body);
        if (!body.startsWith("jarvis")) {
            Files.writeString(dir.resolve("other.port"), Integer.toString(p));
        }
        return new ProcessBuilder("python3", "-m", "http.server", Integer.toString(p), "--bind",
                "127.0.0.1", "--directory", root.toString()).redirectErrorStream(true)
                .redirectOutput(ProcessBuilder.Redirect.DISCARD).start();
    }

    static int free() throws IOException {
        try (ServerSocket s = new ServerSocket(0)) {
            return s.getLocalPort();
        }
    }

    static String run(String... cmd) throws Exception {
        Process p = new ProcessBuilder(List.of(cmd)).redirectErrorStream(true).start();
        String out = new String(p.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
        if (p.waitFor() != 0) {
            throw new IllegalStateException(String.join(" ", cmd) + ": " + out);
        }
        return out;
    }
}
