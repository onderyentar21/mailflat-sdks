# MailFlat Java SDK

Official Java client for [MailFlat](https://mailflat.net): disposable, automation-friendly email
inboxes with **one-line OTP retrieval**. Built for **Selenium / JUnit** test suites. HTTP via the
built-in `java.net.http` (no HTTP dependency); JSON via Jackson.

> Java 11+ · published via [JitPack](https://jitpack.io).

## Install (Maven, via JitPack)

```xml
<repositories>
  <repository><id>jitpack.io</id><url>https://jitpack.io</url></repository>
</repositories>

<dependency>
  <groupId>com.github.onderyentar21</groupId>
  <artifactId>mailflat-sdks</artifactId>
  <version>v0.4.0</version>
</dependency>
```

Gradle:

```groovy
repositories { maven { url 'https://jitpack.io' } }
dependencies { implementation 'com.github.onderyentar21:mailflat-sdks:v0.4.0' }
```

## Quickstart

```java
import net.mailflat.MailFlat;
import net.mailflat.Inbox;

MailFlat mf = new MailFlat("mf_live_…");          // or set MAILFLAT_API_KEY

Inbox inbox = mf.create("signup");                // open a disposable inbox
System.out.println(inbox.address());              // → signup-8f3@x7k2m.mailflat.net

// ... your app/browser submits the form using inbox.address() ...

String otp = inbox.waitForOtp(30);                // polls up to 30s, returns the code
System.out.println(otp);                          // → "123456"

inbox.delete();                                   // or let it auto-purge
```

## With Selenium

The killer use case — sign up in a real browser, grab the verification code, continue:

```java
WebDriver driver = new ChromeDriver();
MailFlat mf = new MailFlat(System.getenv("MAILFLAT_KEY"));

Inbox inbox = mf.create("selenium-run");

driver.get("https://staging.example.com/signup");
driver.findElement(By.id("email")).sendKeys(inbox.address());
driver.findElement(By.id("submit")).click();

String otp = inbox.waitForOtp(30);                // waits for the OTP email
driver.findElement(By.id("code")).sendKeys(otp);
driver.findElement(By.id("verify")).click();

inbox.delete();
driver.quit();
```

> MailFlat is just an SDK call alongside WebDriver — no special Selenium plugin needed. Works the
> same with JUnit, TestNG, Cucumber, or plain `main()`.

## API

### `MailFlat`
- `new MailFlat(apiKey)` · `new MailFlat(apiKey, baseUrl)` · `MailFlat.builder()…build()`
  (`apiKey`, `baseUrl`, `timeout`, `maxRetries`, `httpClient`). `apiKey` falls back to
  `MAILFLAT_API_KEY`. Use `baseUrl` for self-hosted / BYOD (default `https://mailflat.net`).
- `create()` / `create(label)` / `create(CreateInboxOptions)` → `Inbox`
- `list()` → `List<Inbox>` — inboxes opened with this key
- `inbox(address)` → `Inbox` — attach without a network call

### `Inbox`
`address()`, `name()`, `apiKey()`, `retentionHours()`, `delete()`.

**Read** — every read defaults to `Direction.IN`, so a wait right after `send()` never returns
your own outgoing mail:
`messages([Direction])` → `List<Message>`, `latest([Direction])` → `Optional<Message>`,
`waitForMessage(seconds[, Direction])`, `waitForOtp(seconds)` → `String`.

**Write** — `send(to, subject, body[, html[, inReplyTo]])` and `send(to, SendOptions)`,
`markRead(messageId)`, `burn()` (delete every message, keep the address),
`deleteMessage(messageId)`, `downloadAttachment(messageId, attachmentId)` → `byte[]`.

**Added in 0.4.0** — `message(id)` → `Message` (one message by id, without pulling the whole
list), `send(to, SendOptions)` with attachments and cc/bcc, and `waitUntilSent(...)`.

### Attachments, cc and bcc

```java
SendResult r = inbox.send("finance@acme.com", SendOptions.builder()
        .subject("Invoice 2026-08")
        .body("Attached, as discussed.")
        .cc("accounts@acme.com")
        .bcc("archive@acme.com")            // in no header, not even in its own copy
        .attach(Path.of("/tmp/invoice.pdf")) // read + base64 encoded for you
        .attach("notes.txt", bytes)          // or bytes you already hold
        .build());
```

Attachment size and count depend on your plan (free is deliberately small); going over is
rejected with the limit spelled out rather than silently dropping the file.

### "Did it actually go out?"

`send()` returns when the mail is **accepted for delivery** (HTTP 202), not when it is
delivered — delivery runs on a queue. `SendResult` carries `messageId()` and `queued()`; ask
for the outcome:

```java
Message sent = inbox.waitUntilSent(r);        // or waitUntilSent(messageId, seconds)
```

- delivered → returns the `Message` (`sendStatus()` is `sent`, or `unsigned` when it went out
  without a DKIM signature)
- permanently failed → `SendFailedException`, carrying the server's reason
- still queued when your timeout elapses → `SendTimeoutException`. **That is not a failure**:
  the queue keeps retrying, so treating it as "it never went out" and sending again delivers
  the mail twice.

Prefer the `message.delivered` / `message.failed` webhook when you can receive one;
`waitUntilSent` is the pull half of the same contract, for places that cannot (local CI).

### `Message`
`otp()`, `subject()`, `sender()`, `text()`, `html()`, `toAddress()`, `direction()`,
`isRead()`, `receivedAt()`, `raw()`.

**Added in 0.3.0:** `links()` → `List<String>` (clickable URLs written in *this* message;
links quoted from an earlier one are excluded), `attachments()` → `List<Attachment>`,
`headers()` → `Map<String,String>` (null on an encrypted inbox), `spam()`,
`header(name)` (case-insensitive), `messageId()`, `replyToAddress()`,
`reply(body[, html, subject])`, `markRead()`, `delete()`.

**Added in 0.4.0:** `sendStatus()` / `sendError()` (delivery state of a mail you sent) and
`reply(SendOptions)` — a reply carries everything a send does, attachments included, while
keeping its own recipient and threading headers.

> ⚠️ `sender()` is the SMTP **envelope** sender. For transactional mail that is usually a
> bounce address, so `send(to = msg.sender(), …)` quietly delivers your reply to a machine.
> Use `reply(…)`, which targets `replyToAddress()` and adds the `In-Reply-To` / `References`
> headers Gmail and Outlook thread on.

### `Attachment`
`filename()`, `contentType()`, `sizeBytes()`, `isTruncated()`, `download()` → `byte[]`.
Bytes are never included in a listing, so `download()` makes its own request. A `truncated`
attachment exceeded the storage cap and its bytes were never stored.

## Retries

Reads (`GET`/`DELETE`) are retried on `429/502/503/504` and honour the server's `Retry-After`.
**`send()` and `create()` are never retried.** A retried send delivers the same mail twice and
the caller never finds out; a retried create opens a second inbox and burns quota.
`markRead()` and `burn()` are retried, because repeating them lands on the same end state.

## Errors

All extend `MailFlatException`: `AuthenticationException` (401), `PermissionException` (403),
`NotFoundException` (404), `RateLimitException` (429), `ApiException` (other),
`OtpTimeoutException` (no OTP before the timeout), `EncryptedInboxException` (the inbox is
end-to-end encrypted, so the server cannot read it — use a non-encrypted inbox for automation),
`SendFailedException` / `SendTimeoutException` (both `SendException`, carrying `messageId()`
and `sendStatus()` — see `waitUntilSent` above for why they are two types and not one).

## License

MIT
