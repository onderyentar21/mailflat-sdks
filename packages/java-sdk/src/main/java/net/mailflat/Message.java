// Message — a single email, the typed form of the /api/v1 email serialization.
//
// Connected to:
//   - used by:    Inbox (messages/latest/waitForMessage), kullanıcı kodu
//   - depends on: Jackson JsonNode
//
// Key export: Message — getter'lar (otp(), subject(), text(), sender(), ...) + raw()
package net.mailflat;

import com.fasterxml.jackson.databind.JsonNode;

/** One email. Build it from a server JSON node with {@link #fromJson(JsonNode)}. */
public final class Message {
    private final Integer id;
    private final String sender;
    private final String subject;
    private final String text;        // body_text
    private final String html;        // body_html
    private final String otp;         // otp_code (server-extracted)
    private final String tag;
    private final String toAddress;
    private final boolean encrypted;
    private final String direction;   // "in" | "out"
    private final boolean read;
    private final String sendStatus;
    private final String sendError;
    private final String receivedAt;
    private final JsonNode raw;

    private Message(JsonNode d) {
        this.id = d.hasNonNull("id") ? d.get("id").asInt() : null;
        this.sender = text(d, "sender");
        this.subject = text(d, "subject");
        this.text = text(d, "body_text");
        this.html = text(d, "body_html");
        this.otp = text(d, "otp_code");
        this.tag = text(d, "tag");
        this.toAddress = text(d, "to_address");
        this.encrypted = d.path("is_encrypted").asBoolean(false);
        this.direction = text(d, "direction");
        this.read = d.path("is_read").asBoolean(false);
        this.sendStatus = text(d, "send_status");
        this.sendError = text(d, "send_error");
        this.receivedAt = text(d, "received_at");
        this.raw = d;
    }

    static Message fromJson(JsonNode d) {
        return new Message(d);
    }

    private static String text(JsonNode d, String field) {
        JsonNode n = d.get(field);
        return (n == null || n.isNull()) ? null : n.asText();
    }

    public Integer id()         { return id; }
    public String sender()      { return sender; }
    public String subject()     { return subject; }
    public String text()        { return text; }
    public String html()        { return html; }
    /** The one-time code, if the server extracted one (else null). */
    public String otp()         { return otp; }
    public String tag()         { return tag; }
    public String toAddress()   { return toAddress; }
    public boolean isEncrypted(){ return encrypted; }
    public String direction()   { return direction; }
    public boolean isRead()     { return read; }
    public String sendStatus()  { return sendStatus; }
    public String sendError()   { return sendError; }
    public String receivedAt()  { return receivedAt; }
    /** The full backend JSON for this email (escape hatch for fields not surfaced above). */
    public JsonNode raw()       { return raw; }

    @Override
    public String toString() {
        return "Message{subject=" + subject + ", sender=" + sender + ", otp=" + otp + "}";
    }
}
