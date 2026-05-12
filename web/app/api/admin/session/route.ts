import { NextRequest, NextResponse } from "next/server";
import {
  ADMIN_SESSION_COOKIE_NAME,
  verifyAdminSessionCookie,
} from "../session-cookie";

export const runtime = "nodejs";

export async function GET(request: NextRequest) {
  const sessionCookie = request.cookies.get(ADMIN_SESSION_COOKIE_NAME)?.value;
  return NextResponse.json({
    authenticated: verifyAdminSessionCookie(sessionCookie),
  });
}
