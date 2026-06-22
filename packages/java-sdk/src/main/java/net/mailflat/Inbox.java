// Inbox — high-level operations on a single MailFlat inbox.
//
// Returned by MailFlat.create()/list()/inbox(address). Reads mail, waits for OTPs, sends, deletes.
//
// Connected to:
//   - used by:    MailFlat (oluşturur), kullanıcı kodu
//   - depends on: MailFlat (HTTP), Message, exceptions, Jackson
//
// Key export: Inbox — address(), messages(), latest(), waitForOtp(), send(), delete()
package net.mailflat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

/** A single disposable inbox. Obtain it from {@link MailFlat}, don't construct directly. */
public final class Inbox {
    private static final long DEFAULT_POLL_MILLIS = 1000L;

    private final MailFlat client;
    private final String address;
    private final JsonNode raw;

    Inbox(MailFlat client, String address, JsonNode meta) {
        this.client = client;
        this.address = address;
        this.raw = meta;
    }

    public String address() {
        return address;
    }

    /** Per-inbox API key (mf_sk_...) when the server returned one, else null. */
    public String apiKey() {
        return raw != null && raw.hasNonNull("api_key") ? raw.get("api_key").asText() : null;
    }

    public String name() {
        return raw != null && raw.hasNonNull("name") ? raw.get("name").asText() : null;
    }

    public Integer retentionHours() {
        return raw != null && raw.hasNonNull("retention_hours") ? raw.get("retention_hours").asInt() : null;
    }

    public boolean isEncrypted() {
        return raw != null && raw.path("encrypted").asBoolean(false);
    }

    /** The full backend JSON returned for this inbox (or null if attached via inbox(address)). */
    public JsonNode raw() {
        return raw;
    }

    // -------------------------------------------------------------------- read
    /** All messages in this inbox, newest first. */
    public List<Message> messages() {
        JsonNode res = client.get("/api/v1/inboxes/" + address + "/messages");
        List<Message> out = new ArrayList<>();
        JsonNode emails = res.get("emails");
        if (emails != null && emails.isArray()) {
            for (JsonNode e : emails) {
                out.add(Message.fromJson(e));
            }
        }
        return out;
    }

    /** The most recent message, or empty if the inbox has none. */
    public Optional<Message> latest() {
        JsonNode res = client.get("/api/v1/inboxes/" + address + "/latest");
        JsonNode email = res.get("email");
        return (email != null && !email.isNull()) ? Optional.of(Message.fromJson(email)) : Optional.empty();
    }

    /** Polls (default 30s) until any message arrives. */
    public Message waitForMessage() {
        return waitForMessage(30);
    }

    /**
     * Polls until any message arrives, then returns it.
     *
     * @throws OtpTimeoutException   if nothing arrives before {@code timeoutSeconds}
     * @throws EncryptedInboxException if the inbox is end-to-end encrypted
     */
    public Message waitForMessage(int timeoutSeconds) {
        long deadline = System.nanoTime() + timeoutSeconds * 1_000_000_000L;
        while (true) {
            JsonNode res = client.get("/api/v1/inboxes/" + address + "/latest");
            requireNotEncrypted(res, "use a non-encrypted inbox for agent automation.");
            JsonNode email = res.get("email");
            if (email != null && !email.isNull()) {
                return Message.fromJson(email);
            }
            if (System.nanoTime() >= deadline) {
                throw new OtpTimeoutException(
                        "No message arrived for " + address + " within " + timeoutSeconds + "s");
            }
            sleep();
        }
    }

    /** Polls (default 30s) until an OTP code arrives, then returns it. */
    public String waitForOtp() {
        return waitForOtp(30);
    }

    /**
     * Polls until a one-time code (OTP) arrives, then returns it.
     *
     * @throws OtpTimeoutException     if no OTP arrives before {@code timeoutSeconds}
     * @throws EncryptedInboxException if the inbox is end-to-end encrypted
     */
    public String waitForOtp(int timeoutSeconds) {
        long deadline = System.nanoTime() + timeoutSeconds * 1_000_000_000L;
        while (true) {
            JsonNode res = client.get("/api/v1/inboxes/" + address + "/latest");
            requireNotEncrypted(res, "OTP cannot be read via the API.");
            JsonNode email = res.get("email");
            if (email != null && email.hasNonNull("otp_code")) {
                return email.get("otp_code").asText();
            }
            if (System.nanoTime() >= deadline) {
                throw new OtpTimeoutException(
                        "No OTP arrived for " + address + " within " + timeoutSeconds + "s");
            }
            sleep();
        }
    }

    // ------------------------------------------------------------------- write
    /** Send a DKIM-signed email from this inbox (plain text). */
    public JsonNode send(String to, String subject, String body) {
        return send(to, subject, body, null);
    }

    /** Send a DKIM-signed email from this inbox; {@code html} is optional (null = plain only). */
    public JsonNode send(String to, String subject, String body, String html) {
        ObjectNode payload = client.json().createObjectNode();
        payload.put("to", to);
        payload.put("subject", subject != null ? subject : "");
        payload.put("body", body != null ? body : "");
        if (html != null) {
            payload.put("html", html);
        }
        return client.post("/api/v1/inboxes/" + address + "/send", payload);
    }

    /** Delete this inbox and all its messages. Irreversible. */
    public JsonNode delete() {
        return client.delete("/api/v1/inboxes/" + address);
    }

    // ------------------------------------------------------------------- utils
    private void requireNotEncrypted(JsonNode res, String hint) {
        if (res.path("encrypted").asBoolean(false)) {
            String note = res.hasNonNull("note") ? res.get("note").asText()
                    : "This inbox is end-to-end encrypted; " + hint;
            throw new EncryptedInboxException(note);
        }
    }

    private void sleep() {
        try {
            Thread.sleep(DEFAULT_POLL_MILLIS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new MailFlatException("Interrupted while polling " + address);
        }
    }

    @Override
    public String toString() {
        return "Inbox{" + address + "}";
    }
}
