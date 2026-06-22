// No OTP / message arrived before the timeout. (MailFlatException alt tipi.)
package net.mailflat;

public class OtpTimeoutException extends MailFlatException {
    public OtpTimeoutException(String message) {
        super(message);
    }
}
