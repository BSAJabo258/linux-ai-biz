package bau.watch;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.jcraft.jsch.HostKeyRepository;
import com.jcraft.jsch.JSchException;

import java.nio.charset.StandardCharsets;
import java.util.Base64;

import org.junit.jupiter.api.Test;

class TunnelTest {
    static final String PRINTED = "On your own computer, keep this running:\n"
            + "  ssh -L 8766:127.0.0.1:8766 -L 8765:127.0.0.1:8765 owner@YOUR_SERVER_IP\n"
            + "then open:\n  http://127.0.0.1:8766/?k=Ab3_-xYz0123456789abcdefGHIJ\n";

    @Test
    void readsJarvisKeyFromWhatTheLaptopPrints() {
        assertEquals("Ab3_-xYz0123456789abcdefGHIJ", Tunnel.keyFrom(PRINTED));
        assertNull(Tunnel.keyFrom("Permission denied"));
        assertNull(Tunnel.keyFrom(null));
        // another host or a short key is not Jarvis's address
        assertNull(Tunnel.keyFrom("http://evil.example:8766/?k=Ab3_-xYz0123456789abc"));
        assertNull(Tunnel.keyFrom("http://127.0.0.1:8766/?k=short"));
    }

    @Test
    void newKeyIsAnEcdsaLineTheLaptopAccepts() throws JSchException {
        String[] k = Tunnel.newKey("bau-watch-tablet");
        assertTrue(k[0].contains("PRIVATE KEY"));
        // the same shape src/bau/station.py's KEY_LINE accepts
        assertTrue(k[1].matches("ecdsa-sha2-nistp256 [A-Za-z0-9+/]{40,}={0,2} bau-watch-tablet"), k[1]);
        assertNotEquals(k[1], Tunnel.newKey("bau-watch-tablet")[1]);
    }

    @Test
    void fingerprintMatchesOpenSsh() {
        // ssh-keygen -lf prints SHA256: + unpadded base64 of the blob's SHA-256
        byte[] blob = "abc".getBytes(StandardCharsets.US_ASCII);
        assertEquals("SHA256:ungWv48Bz+pBQUDeXa4iI7ADYaOWF3qctBD/YfIAFa0", Tunnel.fingerprint(blob));
    }

    @Test
    void onlyThePinnedHostKeyIsAccepted() {
        byte[] laptop = Base64.getDecoder().decode("AAAAE2VjZHNhLXNoYTItbmlzdHAyNTY=");
        Tunnel.Pin pin = new Tunnel.Pin(Tunnel.fingerprint(laptop));
        assertEquals(HostKeyRepository.OK, pin.check("laptop", laptop));
        assertEquals(HostKeyRepository.CHANGED, pin.check("laptop", "other".getBytes()));
        Tunnel.Pin unpinned = new Tunnel.Pin(null);
        assertEquals(HostKeyRepository.NOT_INCLUDED, unpinned.check("laptop", laptop));
        assertEquals(Tunnel.fingerprint(laptop), unpinned.seen);
    }

    @Test
    void neverSignsInBeforeTheOwnerConfirmedTheLaptop() {
        assertThrows(JSchException.class,
                () -> Tunnel.open("127.0.0.1", 22, "owner", "x", "y", null));
        assertFalse(new Tunnel.Quiet().promptYesNo("accept this host?"));
    }
}
