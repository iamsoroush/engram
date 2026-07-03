import { request as playwrightRequest } from "@playwright/test";

// Fail fast with an actionable message if the real stack isn't up, instead of every spec timing out.
export default async function globalSetup(): Promise<void> {
  const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:5183";
  const ctx = await playwrightRequest.newContext({ baseURL });
  try {
    const res = await ctx.get("/api/v1/health", { timeout: 10_000 });
    if (!res.ok()) throw new Error(`health returned ${res.status()}`);
  } catch (err) {
    throw new Error(
      `e2e-stack: backend not reachable at ${baseURL}/api/v1/health (${String(err)}).\n` +
        "Bring the stack up first:\n" +
        "  docker compose -f docker-compose.yml -f docker-compose.e2e.yml up -d --build --wait\n" +
        "then run with PLAYWRIGHT_BASE_URL pointing at the frontend.",
    );
  } finally {
    await ctx.dispose();
  }
}
