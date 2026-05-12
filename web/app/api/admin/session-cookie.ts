import { createHmac, randomBytes, timingSafeEqual } from "crypto";

export const ADMIN_SESSION_COOKIE_NAME = "research_agent_admin_session";
export const ADMIN_SESSION_MAX_AGE_SECONDS = 8 * 60 * 60;

interface SessionPayload {
  iat: number;
  nonce: string;
}

function getAdminSessionSecret(): string {
  return process.env.ADMIN_SESSION_SECRET?.trim() || "";
}

export function getConfiguredAdminKey(): string {
  return process.env.ADMIN_API_KEY?.trim() || "";
}

function safeEqual(left: string, right: string): boolean {
  const leftBuffer = Buffer.from(left);
  const rightBuffer = Buffer.from(right);
  return (
    leftBuffer.length === rightBuffer.length &&
    timingSafeEqual(leftBuffer, rightBuffer)
  );
}

export function isAdminKeyConfigured(): boolean {
  return Boolean(getConfiguredAdminKey());
}

export function isSessionSecretConfigured(): boolean {
  return Boolean(getAdminSessionSecret());
}

export function adminKeyMatches(candidate: string): boolean {
  const expected = getConfiguredAdminKey();
  return Boolean(expected) && safeEqual(candidate, expected);
}

function signSession(data: string): string {
  return createHmac("sha256", getAdminSessionSecret())
    .update(data)
    .digest("base64url");
}

export function createAdminSessionCookieValue(): string {
  const payload: SessionPayload = {
    iat: Math.floor(Date.now() / 1000),
    nonce: randomBytes(16).toString("base64url"),
  };
  const encodedPayload = Buffer.from(JSON.stringify(payload)).toString("base64url");
  return `${encodedPayload}.${signSession(encodedPayload)}`;
}

export function verifyAdminSessionCookie(value: string | undefined): boolean {
  if (!value || !isSessionSecretConfigured()) {
    return false;
  }

  const [encodedPayload, signature, ...extraParts] = value.split(".");
  if (!encodedPayload || !signature || extraParts.length > 0) {
    return false;
  }

  const expectedSignature = signSession(encodedPayload);
  if (!safeEqual(signature, expectedSignature)) {
    return false;
  }

  try {
    const payload = JSON.parse(
      Buffer.from(encodedPayload, "base64url").toString("utf8"),
    ) as SessionPayload;
    const ageSeconds = Math.floor(Date.now() / 1000) - payload.iat;
    return (
      Number.isFinite(payload.iat) &&
      ageSeconds >= 0 &&
      ageSeconds <= ADMIN_SESSION_MAX_AGE_SECONDS
    );
  } catch {
    return false;
  }
}

export function adminSessionCookieOptions(
  value: string,
  secure: boolean,
  maxAge: number = ADMIN_SESSION_MAX_AGE_SECONDS,
) {
  return {
    name: ADMIN_SESSION_COOKIE_NAME,
    value,
    httpOnly: true,
    sameSite: "lax" as const,
    secure,
    path: "/",
    maxAge,
  };
}
