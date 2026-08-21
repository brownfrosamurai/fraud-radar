/** Display-only account chrome from the mockup. Not persisted. */

export const ACCOUNT_METHODS = [
  "Visa ····4012",
  "MC ····5500",
  "New account",
  "Biometric",
  "Amex ····9911",
] as const;

export const ACCOUNT_IPS = [
  "192.168.1.42",
  "203.0.113.7",
  "198.51.100.3",
  "172.16.0.11",
  "10.0.0.99",
  "203.0.113.201",
] as const;

export type AccountChrome = { ip: string; method: string; line: string };

export function accountChrome(id: string): AccountChrome {
  let hash = 0;
  for (let i = 0; i < id.length; i += 1) {
    hash = (hash * 31 + id.charCodeAt(i)) >>> 0;
  }
  const ip = ACCOUNT_IPS[hash % ACCOUNT_IPS.length];
  const method = ACCOUNT_METHODS[Math.floor(hash / ACCOUNT_IPS.length) % ACCOUNT_METHODS.length];
  return { ip, method, line: `${ip} · ${method}` };
}
