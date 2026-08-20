export type Decision = "ALLOW" | "REVIEW" | "BLOCK";

export type ScoredTransaction = {
  id: string;
  occurred_at: string;
  amount: number;
  model_score: number;
  decision: Decision;
  model_name: "isolation_forest" | "autoencoder";
};

export type FeatureContribution = { feature: string; contribution: number };

export type BurstResponse = {
  accepted: boolean;
  size: number;
  window_ms: number;
  cooldown_seconds: number;
};

export function streamUrl(): string {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${location.host}/api/stream`;
}

export async function fetchRecent(limit = 50): Promise<ScoredTransaction[]> {
  const res = await fetch(`/api/transactions?limit=${limit}`);
  if (!res.ok) throw new Error("list failed");
  return res.json();
}

export async function fetchExplanation(
  id: string,
): Promise<{ status: number; items: FeatureContribution[] }> {
  const res = await fetch(`/api/transactions/${id}/explanation`);
  if (res.status === 200) {
    const body = await res.json();
    return { status: 200, items: body.explanation };
  }
  return { status: res.status, items: [] };
}

export async function triggerBurst(): Promise<{ status: number; body: BurstResponse }> {
  const res = await fetch("/api/demo/burst", { method: "POST" });
  const body = (await res.json()) as BurstResponse;
  return { status: res.status, body };
}

export type Stats = {
  processed: number;
  throughput_tx_per_s: number;
  latency_p50_ms: number | null;
  latency_p95_ms: number | null;
  flagged: number;
};

export async function fetchStats(): Promise<{ status: number; body: Stats | null }> {
  const res = await fetch("/api/stats");
  if (res.status !== 200) return { status: res.status, body: null };
  return { status: 200, body: (await res.json()) as Stats };
}
