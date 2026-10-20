/** Matches the contract's SESSION_ID_PATTERN: ^[A-Za-z0-9_-]{1,64}$ */
export const SESSION_ID_RE = /^[A-Za-z0-9_-]{1,64}$/;

/** e.g. "20261019T150211Z_two-sum_k3f9q2" */
export function newSessionId(slug: string, now: Date = new Date(), rand: () => number = Math.random): string {
  const stamp = now.toISOString().replace(/[-:]/g, "").replace(/\.\d+Z$/, "Z");
  const safeSlug = slug.replace(/[^A-Za-z0-9-]/g, "-").slice(0, 32) || "problem";
  const suffix = Array.from({ length: 6 }, () => "abcdefghijklmnopqrstuvwxyz0123456789"[Math.floor(rand() * 36)]).join("");
  const id = `${stamp}_${safeSlug}_${suffix}`;
  if (!SESSION_ID_RE.test(id)) throw new Error(`generated invalid session id: ${id}`);
  return id;
}

export function eventId(seq: number): string {
  return `ev_${seq}`;
}
