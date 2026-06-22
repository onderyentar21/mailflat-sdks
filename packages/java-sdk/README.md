# MailFlat Java SDK

Official Java client for [MailFlat](https://mailflat.net): disposable, automation-friendly email
inboxes with **one-line OTP retrieval**. Built for **Selenium / JUnit** test suites. HTTP via the
built-in `java.net.http` (no HTTP dependency); JSON via Jackson.

> Java 11+ · coordinates `net.mailflat:mailflat-sdk`.

## Install (Maven)

```xml
<dependency>
  <groupId>net.mailflat</groupId>
  <artifactId>mailflat-sdk</artifactId>
  <version>0.1.0</version>
</dependency>
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
`address()`, `name()`, `apiKey()`, `retentionHours()`, `messages()` → `List<Message>`,
`latest()` → `Optional<Message>`, `waitForOtp(seconds)` → `String`, `waitForMessage(seconds)`,
`send(to, subject, body[, html])`, `delete()`.

### `Message`
`otp()`, `subject()`, `sender()`, `text()`, `html()`, `toAddress()`, `direction()`,
`receivedAt()`, `raw()`.

## Errors

All extend `MailFlatException`: `AuthenticationException` (401), `PermissionException` (403),
`NotFoundException` (404), `RateLimitException` (429), `ApiException` (other),
`OtpTimeoutException` (no OTP before the timeout), `EncryptedInboxException` (the inbox is
end-to-end encrypted, so the server cannot read it — use a non-encrypted inbox for automation).

## License

MIT
