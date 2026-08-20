export type RateBucket = { startMs: number; flagged: number; total: number };

export function pushScore(scores: number[], value: number, cap = 200): number[] {
  const next = [...scores, value];
  return next.length > cap ? next.slice(next.length - cap) : next;
}

export function pushRate(
  buckets: RateBucket[],
  atMs: number,
  flagged: boolean,
  bucketMs = 10_000,
  windowMs = 600_000,
): RateBucket[] {
  const startMs = Math.floor(atMs / bucketMs) * bucketMs;
  const found = buckets.find((bucket) => bucket.startMs === startMs);
  const next = found
    ? buckets.map((bucket) =>
        bucket.startMs === startMs
          ? { ...bucket, total: bucket.total + 1, flagged: bucket.flagged + (flagged ? 1 : 0) }
          : bucket,
      )
    : [...buckets, { startMs, total: 1, flagged: flagged ? 1 : 0 }];
  const cutoff = atMs - windowMs;
  return next.filter((bucket) => bucket.startMs >= cutoff);
}

export function drawHistogram(canvas: HTMLCanvasElement, scores: number[]): void {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const width = canvas.width;
  const height = canvas.height;
  ctx.clearRect(0, 0, width, height);
  if (scores.length === 0) return;
  const bins = new Array(10).fill(0);
  for (const score of scores) {
    const index = Math.min(9, Math.max(0, Math.floor(score * 10)));
    bins[index] += 1;
  }
  const max = Math.max(...bins, 1);
  const gap = 2;
  const barW = (width - gap * 9) / 10;
  ctx.fillStyle = "#3ec6ff";
  bins.forEach((count, i) => {
    const h = (count / max) * height;
    ctx.fillRect(i * (barW + gap), height - h, barW, h);
  });
}

export function drawRate(canvas: HTMLCanvasElement, buckets: RateBucket[]): void {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const width = canvas.width;
  const height = canvas.height;
  ctx.clearRect(0, 0, width, height);
  if (buckets.length === 0) return;
  const rates = buckets.map((bucket) => bucket.flagged / Math.max(bucket.total, 1));
  const max = Math.max(...rates, 1e-6);
  ctx.strokeStyle = "#ff6b5e";
  ctx.beginPath();
  rates.forEach((rate, i) => {
    const x = (i / Math.max(rates.length - 1, 1)) * width;
    const y = height - (rate / max) * height;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
}
