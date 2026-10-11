// Asculto gateway: auth, entitlements and monthly quotas.
//
// API keys are stored hashed in KV as `apikey:<sha256>` -> entitlement JSON.
// Usage counters are KV keys `usage:<userId>:<YYYY-MM>`.

export type Tier = "free" | "pro" | "research" | "enterprise";

export interface Entitlement {
  userId: string;
  tier: Tier;
  reportsPerMonth: number;
  llm: boolean;
  batch: boolean;
}

export interface Env {
  QUOTAS: KVNamespace;
  USERS: KVNamespace;
  ENVIRONMENT: string;
  INFERENCE_URL: string;
  R2_ACCOUNT_ID: string;
  STRIPE_SECRET_KEY: string;
  STRIPE_WEBHOOK_SECRET: string;
  R2_ACCESS_KEY_ID: string;
  R2_SECRET_ACCESS_KEY: string;
}

export const TIER_QUOTA: Record<Tier, number> = {
  free: 5,
  pro: 25,
  research: 100,
  enterprise: 1000,
};

export function entitlementFor(userId: string, tier: Tier): Entitlement {
  return {
    userId,
    tier,
    reportsPerMonth: TIER_QUOTA[tier],
    llm: tier !== "free",
    batch: tier === "research" || tier === "enterprise",
  };
}

async function sha256Hex(input: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(input));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function authenticate(request: Request, env: Env): Promise<Entitlement | null> {
  const header = request.headers.get("authorization") || "";
  const key = header.startsWith("Bearer ") ? header.slice(7).trim() : "";
  if (!key) return null;
  const record = await env.USERS.get(`apikey:${await sha256Hex(key)}`);
  if (!record) return null;
  return JSON.parse(record) as Entitlement;
}

export function period(date = new Date()): string {
  return date.toISOString().slice(0, 7);
}

export async function usage(env: Env, userId: string): Promise<number> {
  return Number((await env.QUOTAS.get(`usage:${userId}:${period()}`)) || "0");
}

export async function incrementUsage(env: Env, userId: string, by = 1): Promise<number> {
  const next = (await usage(env, userId)) + by;
  await env.QUOTAS.put(`usage:${userId}:${period()}`, String(next), { expirationTtl: 60 * 60 * 24 * 40 });
  return next;
}

export async function withinQuota(env: Env, ent: Entitlement): Promise<boolean> {
  return (await usage(env, ent.userId)) < ent.reportsPerMonth;
}
