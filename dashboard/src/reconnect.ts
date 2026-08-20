export function nextReconnectDelay(attempt: number): number {
  return Math.min(8000, 1000 * 2 ** attempt);
}
