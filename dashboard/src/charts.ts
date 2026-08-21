export type RateBucket = { startMs: number; flagged: number; total: number };

const ALLOW_HEX = "rgba(62,198,255,0.55)";
const REVIEW_HEX = "rgba(240,169,59,0.75)";
const BLOCK_HEX = "rgba(255,107,94,0.75)";
const GRID = "rgba(255,255,255,0.06)";
const MARKER = "rgba(255,255,255,0.18)";
const RATE_LINE = "#ff6b5e";
const THRESHOLDS = [0.4, 0.6, 0.9];
const HIST_BINS = 24;

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

export function scoreBandColor(score: number): string {
  if (score > 0.6) return BLOCK_HEX;
  if (score > 0.4) return REVIEW_HEX;
  return ALLOW_HEX;
}

function setupCanvas(canvas: HTMLCanvasElement): {
  ctx: CanvasRenderingContext2D;
  w: number;
  h: number;
} | null {
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  const dpr = typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1;
  const rect = canvas.getBoundingClientRect();
  const w = rect.width || canvas.clientWidth || canvas.width || 640;
  const h = rect.height || canvas.clientHeight || canvas.height || 160;
  const nextW = Math.max(1, Math.round(w * dpr));
  const nextH = Math.max(1, Math.round(h * dpr));
  if (canvas.width !== nextW || canvas.height !== nextH) {
    canvas.width = nextW;
    canvas.height = nextH;
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, w, h };
}

export function drawHistogram(canvas: HTMLCanvasElement, scores: number[]): void {
  const dims = setupCanvas(canvas);
  if (!dims) return;
  const { ctx, w, h } = dims;
  ctx.clearRect(0, 0, w, h);
  if (scores.length === 0) return;

  const counts = new Array(HIST_BINS).fill(0);
  for (const score of scores) {
    const index = Math.min(HIST_BINS - 1, Math.max(0, Math.floor(score * HIST_BINS)));
    counts[index] += 1;
  }
  const max = Math.max(...counts, 1);
  const padL = 4;
  const padB = 4;
  const padT = 4;
  const barW = (w - padL * 2) / HIST_BINS;

  ctx.strokeStyle = GRID;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(0, h - padB);
  ctx.lineTo(w, h - padB);
  ctx.stroke();

  counts.forEach((count, i) => {
    const barH = (count / max) * (h - padT - padB);
    const x = padL + i * barW;
    const y = h - padB - barH;
    ctx.fillStyle = scoreBandColor(i / HIST_BINS);
    ctx.fillRect(x + 1, y, Math.max(1, barW - 2), barH);
  });

  THRESHOLDS.forEach((threshold) => {
    const x = padL + threshold * (w - padL * 2);
    ctx.strokeStyle = MARKER;
    ctx.setLineDash([2, 3]);
    ctx.beginPath();
    ctx.moveTo(x, padT);
    ctx.lineTo(x, h - padB);
    ctx.stroke();
    ctx.setLineDash([]);
  });
}

export function drawRate(canvas: HTMLCanvasElement, buckets: RateBucket[]): void {
  const dims = setupCanvas(canvas);
  if (!dims) return;
  const { ctx, w, h } = dims;
  ctx.clearRect(0, 0, w, h);
  if (buckets.length < 2) return;

  const padB = 4;
  const padT = 6;
  const rates = buckets.map((bucket) => bucket.flagged / Math.max(bucket.total, 1));
  const maxRate = Math.max(0.15, ...rates);
  const stepX = w / (rates.length - 1);

  ctx.strokeStyle = GRID;
  ctx.beginPath();
  ctx.moveTo(0, h - padB);
  ctx.lineTo(w, h - padB);
  ctx.stroke();

  const grad = ctx.createLinearGradient(0, padT, 0, h - padB);
  grad.addColorStop(0, "rgba(255,107,94,0.35)");
  grad.addColorStop(1, "rgba(255,107,94,0.02)");

  ctx.beginPath();
  rates.forEach((rate, i) => {
    const x = i * stepX;
    const y = h - padB - (rate / maxRate) * (h - padT - padB);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.lineTo(w, h - padB);
  ctx.lineTo(0, h - padB);
  ctx.closePath();
  ctx.fillStyle = grad;
  ctx.fill();

  ctx.beginPath();
  rates.forEach((rate, i) => {
    const x = i * stepX;
    const y = h - padB - (rate / maxRate) * (h - padT - padB);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = RATE_LINE;
  ctx.lineWidth = 1.5;
  ctx.stroke();

  const lastX = (rates.length - 1) * stepX;
  const lastY = h - padB - (rates[rates.length - 1] / maxRate) * (h - padT - padB);
  ctx.fillStyle = RATE_LINE;
  ctx.beginPath();
  ctx.arc(lastX, lastY, 2.5, 0, Math.PI * 2);
  ctx.fill();
}
