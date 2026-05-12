import { NextRequest, NextResponse } from "next/server";
import {
  ADMIN_SESSION_COOKIE_NAME,
  getConfiguredAdminKey,
  verifyAdminSessionCookie,
} from "../../admin/session-cookie";

export const runtime = "nodejs";

const ALLOWED_BACKEND_ROUTES: Array<{ method: string; pattern: RegExp }> = [
  { method: "GET", pattern: /^\/api\/agents$/ },
  { method: "POST", pattern: /^\/api\/agents\/[^/]+\/config$/ },
  { method: "GET", pattern: /^\/api\/config$/ },
  { method: "GET", pattern: /^\/api\/models$/ },
  { method: "POST", pattern: /^\/api\/analyze$/ },
  { method: "POST", pattern: /^\/api\/discover$/ },
  { method: "POST", pattern: /^\/api\/reports\/pdf$/ },
];

function internalApiUrl(): string {
  return (
    process.env.INTERNAL_API_URL?.trim() ||
    process.env.NEXT_PUBLIC_API_URL?.trim() ||
    "http://localhost:8000"
  ).replace(/\/+$/, "");
}

function isAllowedBackendRoute(method: string, path: string): boolean {
  return ALLOWED_BACKEND_ROUTES.some(
    (route) => route.method === method && route.pattern.test(path),
  );
}

function upstreamHeaders(request: NextRequest, adminKey: string): Headers {
  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("cookie");
  headers.delete("connection");
  headers.delete("content-length");
  headers.set("X-Research-Agent-Key", adminKey);
  return headers;
}

async function proxyToBackend(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const sessionCookie = request.cookies.get(ADMIN_SESSION_COOKIE_NAME)?.value;
  if (!verifyAdminSessionCookie(sessionCookie)) {
    return NextResponse.json({ detail: "Unauthorized." }, { status: 401 });
  }

  const adminKey = getConfiguredAdminKey();
  if (!adminKey) {
    return NextResponse.json(
      { detail: "Admin API is not configured." },
      { status: 503 },
    );
  }

  const params = await context.params;
  const backendPath = `/${params.path.join("/")}`;
  if (!isAllowedBackendRoute(request.method, backendPath)) {
    return NextResponse.json(
      { detail: "Backend route is not allowed." },
      { status: 404 },
    );
  }

  const upstreamUrl = new URL(`${internalApiUrl()}${backendPath}`);
  upstreamUrl.search = request.nextUrl.search;
  const requestBody =
    request.method === "GET" || request.method === "HEAD"
      ? undefined
      : await request.arrayBuffer();

  const upstreamResponse = await fetch(upstreamUrl, {
    method: request.method,
    headers: upstreamHeaders(request, adminKey),
    body: requestBody,
    cache: "no-store",
  });

  const responseHeaders = new Headers();
  for (const header of ["content-type", "content-disposition"]) {
    const value = upstreamResponse.headers.get(header);
    if (value) {
      responseHeaders.set(header, value);
    }
  }

  return new NextResponse(await upstreamResponse.arrayBuffer(), {
    status: upstreamResponse.status,
    headers: responseHeaders,
  });
}

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  return proxyToBackend(request, context);
}

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  return proxyToBackend(request, context);
}
