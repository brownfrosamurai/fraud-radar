import { useEffect, useState } from "react";
import {
  fetchExplanation,
  fetchLatest,
  postScore,
  triggerBurst,
  type Decision,
  type FeatureContribution,
  type ScoredTransaction,
} from "./api";

const BADGE: Record<Decision, string> = {
  ALLOW: "var(--allow)",
  REVIEW: "var(--review)",
  BLOCK: "var(--block)",
};

export function ScoreCard() {
  const [tx, setTx] = useState<ScoredTransaction | null>(null);
  const [explanation, setExplanation] = useState<FeatureContribution[]>([]);
  const [cooldown, setCooldown] = useState(0);
  const [injecting, setInjecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const scored = await postScore(20);
        const latest = (await fetchLatest()) ?? scored;
        const expl = await fetchExplanation(latest.id);
        if (!cancelled) {
          setTx(latest);
          setExplanation(expl);
          setError(null);
        }
      } catch {
        if (!cancelled) setError("API unavailable");
      }
    }
    void load();
    const poll = window.setInterval(async () => {
      try {
        const latest = await fetchLatest();
        if (!cancelled && latest) {
          setTx(latest);
          setExplanation(await fetchExplanation(latest.id));
          setError(null);
        }
      } catch {
        if (!cancelled) setError("API unavailable");
      }
    }, 1000);
    return () => {
      cancelled = true;
      window.clearInterval(poll);
    };
  }, []);

  useEffect(() => {
    if (cooldown <= 0) return;
    const t = window.setInterval(() => setCooldown((c) => Math.max(0, c - 1)), 1000);
    return () => window.clearInterval(t);
  }, [cooldown]);

  async function onBurst() {
    setInjecting(true);
    try {
      const { status, body } = await triggerBurst();
      if (status === 200 && body.accepted) {
        setCooldown(body.cooldown_seconds);
        setError(null);
        return;
      }
      if (status === 429) {
        setCooldown(body.cooldown_seconds);
        setError(null);
        return;
      }
      setError("Burst failed");
    } catch {
      setError("Burst failed");
    } finally {
      setInjecting(false);
    }
  }

  const disabled = injecting || cooldown > 0;
  const label = injecting
    ? "Injecting…"
    : cooldown > 0
      ? `Cooldown ${cooldown}s`
      : "Inject Synthetic Burst";

  return (
    <section className="mx-auto mt-16 w-[480px] border border-neutral-700 p-6">
      <p className="text-xs uppercase tracking-wide text-neutral-400">Fraud Radar · Slice 0</p>
      {tx ? (
        <>
          <p className="mt-4 font-mono text-2xl">${tx.amount.toFixed(2)}</p>
          <p className="font-mono text-sm text-neutral-400">score {tx.model_score.toFixed(2)}</p>
          <p className="mt-2 font-semibold" style={{ color: BADGE[tx.decision] }}>
            {tx.decision}
          </p>
          <ul className="mt-4 space-y-1 font-mono text-sm">
            {explanation.map((item) => (
              <li key={item.feature}>
                <span>{item.feature}</span> {item.contribution.toFixed(2)}
              </li>
            ))}
          </ul>
        </>
      ) : error ? (
        <p className="mt-4 text-neutral-400">{error}</p>
      ) : (
        <p className="mt-4 text-neutral-400">Waiting for transactions…</p>
      )}
      {tx && error ? <p className="mt-2 text-sm text-neutral-400">{error}</p> : null}
      <button
        type="button"
        className="mt-6 bg-cyan-400 px-3 py-2 text-sm font-semibold text-black disabled:opacity-50"
        disabled={disabled}
        onClick={onBurst}
      >
        {label}
      </button>
    </section>
  );
}
