import { NextRequest, NextResponse } from "next/server";
import { adminSessionCookieOptions } from "../session-cookie";

export const runtime = "nodejs";

export async function POST(request: NextRequest) {
  const response = NextResponse.json({ authenticated: false });
  response.cookies.set(
    adminSessionCookieOptions("", request.nextUrl.protocol === "https:", 0),
  );
  return response;
}
