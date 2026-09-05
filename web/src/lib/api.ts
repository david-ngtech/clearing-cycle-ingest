const BASE = "/engine";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

export type CycleSnap = {
  cycle_date: string;
  cycle_no: number;
  status: string;
  required: string[];
  landed: string[];
  missing: string[];
};

export type Source = {
  id: string;
  kind: string;
  name: string;
  cadence: string;
  contract: string;
  owner: string;
};

export type Snapshot = {
  as_of: string;
  today: string;
  sources: Source[];
  members: { id: string; name: string; country: string; ica: string }[];
  endpoints: { id: string; member_id: string; code: string; required: number; city: string }[];
  cycles: CycleSnap[];
  dead_letters: { id: number; path: string; reason: string; evidence: string; created_at: string }[];
  inbox: { id: number; path: string; status: string; file_id: string | null; reason: string | null }[];
  row_count: number;
};

export const api = {
  metrics: () => request<Snapshot>("/metrics"),
  run: () => request<{ cycles: CycleSnap[] }>("/run", { method: "POST" }),
  late: (cycle_date: string, cycle_no: number, endpoint_id: string) =>
    request("/late", {
      method: "POST",
      body: JSON.stringify({ cycle_date, cycle_no, endpoint_id }),
    }),
};
