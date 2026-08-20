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

export async function postScore(amount: number): Promise<ScoredTransaction> {
  const features: Record<string, number> = { Time: 0 };
  for (let i = 1; i <= 28; i += 1) features[`V${i}`] = 0;
  const res = await fetch("/api/score", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      transaction_id: crypto.randomUUID(),
      occurred_at: new Date().toISOString(),
      amount,
      features,
    }),
  });
  if (!res.ok) throw new Error("score failed");
  return res.json();
}

export async function fetchLatest(): Promise<ScoredTransaction | null> {
  const res = await fetch("/api/transactions?limit=1");
  if (!res.ok) throw new Error("list failed");
  const rows: ScoredTransaction[] = await res.json();
  return rows[0] ?? null;
}

export async function fetchExplanation(
  id: string,
): Promise<FeatureContribution[]> {
  const res = await fetch(`/api/transactions/${id}/explanation`);
  if (!res.ok) throw new Error("explain failed");
  const body = await res.json();
  return body.explanation;
}

export async function triggerBurst(): Promise<{ status: number; body: BurstResponse }> {
  const res = await fetch("/api/demo/burst", { method: "POST" });
  const body = (await res.json()) as BurstResponse;
  return { status: res.status, body };
}
