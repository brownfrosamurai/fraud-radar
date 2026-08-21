import { expect, test, vi } from "vitest";
import { drawHistogram, drawRate, scoreBandColor } from "./charts";

function fakeContext() {
  const gradient = { addColorStop: vi.fn() };
  return {
    clearRect: vi.fn(),
    fillRect: vi.fn(),
    beginPath: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    stroke: vi.fn(),
    fill: vi.fn(),
    closePath: vi.fn(),
    arc: vi.fn(),
    setLineDash: vi.fn(),
    setTransform: vi.fn(),
    createLinearGradient: vi.fn(() => gradient),
    fillStyle: "",
    strokeStyle: "",
    lineWidth: 1,
  };
}

function fakeCanvas(ctx: ReturnType<typeof fakeContext>) {
  return {
    getContext: () => ctx,
    getBoundingClientRect: () => ({ width: 640, height: 160, top: 0, left: 0, bottom: 160, right: 640 }),
    width: 640,
    height: 160,
  } as unknown as HTMLCanvasElement;
}

test("scoreBandColor follows decide() thresholds", () => {
  expect(scoreBandColor(0.2)).toContain("62,198,255");
  expect(scoreBandColor(0.5)).toContain("240,169,59");
  expect(scoreBandColor(0.8)).toContain("255,107,94");
});

function recordingCanvas(ctx: ReturnType<typeof fakeContext>) {
  let width = 0;
  let height = 0;
  const widthWrites: number[] = [];
  const canvas = {
    getContext: () => ctx,
    getBoundingClientRect: () => ({
      width: 640,
      height: 160,
      top: 0,
      left: 0,
      bottom: 160,
      right: 640,
    }),
    get width() {
      return width;
    },
    set width(value: number) {
      width = value;
      widthWrites.push(value);
    },
    get height() {
      return height;
    },
    set height(value: number) {
      height = value;
    },
  };
  return { canvas: canvas as unknown as HTMLCanvasElement, widthWrites };
}

test("drawHistogram does not reset the bitmap when size is unchanged", () => {
  const ctx = fakeContext();
  const { canvas, widthWrites } = recordingCanvas(ctx);
  drawHistogram(canvas, [0.1, 0.5, 0.85]);
  drawHistogram(canvas, [0.1, 0.5, 0.85, 0.2]);
  expect(widthWrites).toHaveLength(1);
});

test("drawHistogram paints threshold-colored bins", () => {
  const ctx = fakeContext();
  drawHistogram(fakeCanvas(ctx), [0.1, 0.5, 0.85]);
  expect(ctx.fillRect.mock.calls.length).toBeGreaterThan(0);
  expect(ctx.setLineDash).toHaveBeenCalledWith([2, 3]);
});

test("drawRate fills under the line once there are two buckets", () => {
  const ctx = fakeContext();
  drawRate(fakeCanvas(ctx), [
    { startMs: 0, flagged: 1, total: 4 },
    { startMs: 10_000, flagged: 2, total: 5 },
  ]);
  expect(ctx.createLinearGradient).toHaveBeenCalled();
  expect(ctx.fill).toHaveBeenCalled();
  expect(ctx.arc).toHaveBeenCalled();
});
