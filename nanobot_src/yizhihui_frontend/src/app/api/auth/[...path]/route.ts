import { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const OPENCLAW_API_URL =
  process.env.OPENCLAW_API_URL || "http://localhost:8080";

async function proxyAuthRequest(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  const subPath = path.join("/");
  const upstream = new URL(`/api/auth/${subPath}`, OPENCLAW_API_URL);

  req.nextUrl.searchParams.forEach((value, key) => {
    upstream.searchParams.set(key, value);
  });

  const headers = new Headers();
  const authorization = req.headers.get("authorization");
  if (authorization) headers.set("Authorization", authorization);
  const contentType = req.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);
  const accept = req.headers.get("accept");
  if (accept) headers.set("Accept", accept);

  const init: RequestInit = {
    method: req.method,
    headers,
    // @ts-expect-error -- Node fetch supports streaming request bodies.
    duplex: "half",
  };

  if (req.method !== "GET" && req.method !== "HEAD" && req.body) {
    init.body = req.body;
  }

  let upstreamRes: Response;
  try {
    upstreamRes = await fetch(upstream.toString(), init);
  } catch (err) {
    const detail = err instanceof Error ? err.message : "fetch failed";
    return Response.json(
      {
        detail: `OpenClaw gateway unavailable. Check OPENCLAW_API_URL and container network. (${detail})`,
      },
      { status: 503 },
    );
  }

  const responseHeaders = new Headers();
  const upstreamContentType = upstreamRes.headers.get("content-type");
  if (upstreamContentType) responseHeaders.set("Content-Type", upstreamContentType);

  return new Response(upstreamRes.body, {
    status: upstreamRes.status,
    headers: responseHeaders,
  });
}

export const GET = proxyAuthRequest;
export const POST = proxyAuthRequest;
export const PUT = proxyAuthRequest;
export const DELETE = proxyAuthRequest;
export const PATCH = proxyAuthRequest;
