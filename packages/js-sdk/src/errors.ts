// MailFlat SDK error types — maps HTTP status codes to meaningful JS exceptions.
//
// Connected to:
//   - used by:    client.ts, inbox.ts, index.ts
//   - depends on: none (pure)
//
// Key export: MailFlatError + alt tipleri (Authentication/Permission/NotFound/RateLimit/API/OTPTimeout/EncryptedInbox)

export class MailFlatError extends Error {
  statusCode?: number;
  constructor(message: string, statusCode?: number) {
    super(message);
    this.name = "MailFlatError";
    this.statusCode = statusCode;
    // Restores the prototype chain for Error subclasses under TS
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export class AuthenticationError extends MailFlatError {
  constructor(message: string, statusCode?: number) {
    super(message, statusCode);
    this.name = "AuthenticationError";
  }
}

export class PermissionError extends MailFlatError {
  constructor(message: string, statusCode?: number) {
    super(message, statusCode);
    this.name = "PermissionError";
  }
}

export class NotFoundError extends MailFlatError {
  constructor(message: string, statusCode?: number) {
    super(message, statusCode);
    this.name = "NotFoundError";
  }
}

export class RateLimitError extends MailFlatError {
  /** The server's `Retry-After` in seconds, when it sent one. */
  retryAfter?: number;
  constructor(message: string, statusCode?: number, retryAfter?: number) {
    super(message, statusCode);
    this.name = "RateLimitError";
    this.retryAfter = retryAfter;
  }
}

export class APIError extends MailFlatError {
  constructor(message: string, statusCode?: number) {
    super(message, statusCode);
    this.name = "APIError";
  }
}

export class OTPTimeoutError extends MailFlatError {
  constructor(message: string) {
    super(message);
    this.name = "OTPTimeoutError";
  }
}

export class EncryptedInboxError extends MailFlatError {
  constructor(message: string) {
    super(message);
    this.name = "EncryptedInboxError";
  }
}

// Throws the matching MailFlatError subclass for an HTTP status code.
export function raiseForStatus(
  statusCode: number,
  detail: string,
  retryAfter?: number,
): never {
  switch (statusCode) {
    case 401:
      throw new AuthenticationError(detail || "Invalid or missing API key", statusCode);
    case 403:
      throw new PermissionError(detail || "This API key does not own that inbox", statusCode);
    case 404:
      throw new NotFoundError(detail || "Not found", statusCode);
    case 429:
      throw new RateLimitError(detail || "Rate limit exceeded", statusCode, retryAfter);
    default:
      throw new APIError(detail || `Request failed with status ${statusCode}`, statusCode);
  }
}
