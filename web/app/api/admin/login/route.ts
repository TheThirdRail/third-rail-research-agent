import { NextRequest, NextResponse } from "next/server";
import {
  adminKeyMatches,
  adminSessionCookieOptions,
  createAdminSessionCookieValue,
  isAdminKeyConfigured,
  isSessionSecretConfigured,
} from "../session-cookie";

export const runtime = "nodejs";

export async function POST(request: NextRequest) {
  if (!isAdminKeyConfigured() || !isSessionSecretConfigured()) {
    return NextResponse.json(
      { detail: "Admin session is not configured." },
      { status: 503 },
    );
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid login payload." }, { status: 400 });
  }

  const adminKey =
    typeof body === "object" &&
    body !== null &&
    "adminKey" in body &&
    typeof body.adminKey === "string"
      ? body.adminKey
      : "";

  if (!adminKeyMatches(adminKey)) {
    return NextResponse.json({ detail: "Unauthorized." }, { status: 401 });
  }

  const response = NextResponse.json({ authenticated: true });
  response.cookies.set(
    adminSessionCookieOptions(
      createAdminSessionCookieValue(),
      request.nextUrl.protocol === "https:",
    ),
  );
  return response;
}
