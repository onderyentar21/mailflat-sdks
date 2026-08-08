// OutgoingAttachment — one file on its way out, base64 encoded for the wire.
//
// The agent should never have to base64 a file by hand: hiding that is most of what an SDK
// is for. A filesystem path is the common case here, unlike the JS SDK which deliberately
// takes bytes only because it also runs in a browser, where there is no filesystem.
//
// Connected to:
//   - used by:    SendOptions, Inbox.send(), Message.reply()
//   - depends on: java.nio.file (reading the file), java.util.Base64
//
// Key export: OutgoingAttachment.of(Path) · of(name, bytes) · of(name, type, bytes) · ofBase64(...)
package net.mailflat;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Base64;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;

/** A file being sent out. Build it with one of the static factories. */
public final class OutgoingAttachment {

    private static final String FALLBACK_TYPE = "application/octet-stream";

    /**
     * Extension → content type, consulted BEFORE {@link Files#probeContentType(Path)}.
     *
     * <p>Probing is platform-dependent: on Linux it reads the shared MIME database, on macOS
     * it often returns null for the very types that matter here. Guessing from the extension
     * first makes {@code invoice.pdf} arrive as {@code application/pdf} on every machine
     * instead of as a nameless blob on some of them.
     */
    private static final Map<String, String> TYPES_BY_EXTENSION = new HashMap<>();

    static {
        TYPES_BY_EXTENSION.put("pdf", "application/pdf");
        TYPES_BY_EXTENSION.put("png", "image/png");
        TYPES_BY_EXTENSION.put("jpg", "image/jpeg");
        TYPES_BY_EXTENSION.put("jpeg", "image/jpeg");
        TYPES_BY_EXTENSION.put("gif", "image/gif");
        TYPES_BY_EXTENSION.put("webp", "image/webp");
        TYPES_BY_EXTENSION.put("svg", "image/svg+xml");
        TYPES_BY_EXTENSION.put("txt", "text/plain");
        TYPES_BY_EXTENSION.put("log", "text/plain");
        TYPES_BY_EXTENSION.put("csv", "text/csv");
        TYPES_BY_EXTENSION.put("json", "application/json");
        TYPES_BY_EXTENSION.put("xml", "application/xml");
        TYPES_BY_EXTENSION.put("html", "text/html");
        TYPES_BY_EXTENSION.put("htm", "text/html");
        TYPES_BY_EXTENSION.put("zip", "application/zip");
        TYPES_BY_EXTENSION.put("gz", "application/gzip");
        TYPES_BY_EXTENSION.put("doc", "application/msword");
        TYPES_BY_EXTENSION.put("docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document");
        TYPES_BY_EXTENSION.put("xls", "application/vnd.ms-excel");
        TYPES_BY_EXTENSION.put("xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
        TYPES_BY_EXTENSION.put("ics", "text/calendar");
        TYPES_BY_EXTENSION.put("eml", "message/rfc822");
    }

    private final String filename;
    private final String contentType;
    private final String contentBase64;

    private OutgoingAttachment(String filename, String contentType, String contentBase64) {
        this.filename = filename;
        this.contentType = contentType;
        this.contentBase64 = contentBase64;
    }

    /**
     * Read a file from disk and attach it; the content type is guessed from the extension.
     *
     * @throws MailFlatException if the file cannot be read — better here than as a confusing
     *                           server-side rejection after a half-built payload went out
     */
    public static OutgoingAttachment of(Path path) {
        if (path == null) {
            throw new MailFlatException("Attachment path must not be null.");
        }
        byte[] data;
        try {
            data = Files.readAllBytes(path);
        } catch (IOException e) {
            throw new MailFlatException(
                    "Could not read attachment " + path + ": " + e.getMessage());
        }
        Path name = path.getFileName();
        return of(name == null ? "attachment" : name.toString(), guessContentType(path), data);
    }

    /** Attach bytes you already have; the content type is guessed from the filename. */
    public static OutgoingAttachment of(String filename, byte[] content) {
        return of(filename, guessContentType(filename), content);
    }

    /** Attach bytes with an explicit content type (null falls back to the guess). */
    public static OutgoingAttachment of(String filename, String contentType, byte[] content) {
        String name = filename == null ? "" : filename.trim();
        if (name.isEmpty()) {
            throw new MailFlatException("An attachment needs a filename.");
        }
        if (content == null) {
            throw new MailFlatException("Attachment '" + name + "' has no content.");
        }
        String type = (contentType == null || contentType.trim().isEmpty())
                ? guessContentType(name) : contentType.trim();
        return new OutgoingAttachment(name, type,
                Base64.getEncoder().encodeToString(content));
    }

    /** Attach content that is already base64 encoded (e.g. straight from another API). */
    public static OutgoingAttachment ofBase64(String filename, String contentType,
                                              String contentBase64) {
        String name = filename == null ? "" : filename.trim();
        if (name.isEmpty()) {
            throw new MailFlatException("An attachment needs a filename.");
        }
        if (contentBase64 == null) {
            throw new MailFlatException("Attachment '" + name + "' has no content.");
        }
        String type = (contentType == null || contentType.trim().isEmpty())
                ? guessContentType(name) : contentType.trim();
        return new OutgoingAttachment(name, type, contentBase64);
    }

    public String filename() {
        return filename;
    }

    public String contentType() {
        return contentType;
    }

    /** The file as base64 — this is what goes on the wire (JSON + base64, not multipart). */
    public String contentBase64() {
        return contentBase64;
    }

    private static String guessContentType(Path path) {
        Path name = path.getFileName();
        String fromExtension = byExtension(name == null ? "" : name.toString());
        if (fromExtension != null) {
            return fromExtension;
        }
        try {
            String probed = Files.probeContentType(path);
            if (probed != null && !probed.isEmpty()) {
                return probed;
            }
        } catch (IOException ignored) {
            // Probing is best-effort; an unreadable MIME database must not fail a send.
        }
        return FALLBACK_TYPE;
    }

    private static String guessContentType(String filename) {
        String fromExtension = byExtension(filename == null ? "" : filename);
        return fromExtension != null ? fromExtension : FALLBACK_TYPE;
    }

    private static String byExtension(String filename) {
        int dot = filename.lastIndexOf('.');
        if (dot < 0 || dot == filename.length() - 1) {
            return null;
        }
        return TYPES_BY_EXTENSION.get(filename.substring(dot + 1).toLowerCase(Locale.ROOT));
    }

    @Override
    public String toString() {
        return "OutgoingAttachment{" + filename + ", " + contentType + "}";
    }
}
