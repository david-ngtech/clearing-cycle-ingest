"use client";

import { useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, type Snapshot } from "@/lib/api";

const statusTone: Record<string, string> = {
  open: "text-muted-foreground",
  partial: "text-amber-300",
  closed: "text-teal-300",
  late: "text-rose-300",
  accepted: "text-teal-300",
  rejected: "text-rose-300",
  landed: "text-teal-300",
  missing: "text-amber-300",
  duplicate: "text-muted-foreground",
};

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export function IngestConsole() {
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setSnap(await api.metrics());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Engine unreachable");
    }
  }, []);

  useEffect(() => {
    void load();
    const id = window.setInterval(() => void load(), 4000);
    return () => window.clearInterval(id);
  }, [load]);

  const run = async () => {
    setBusy(true);
    try {
      await api.run();
      await load();
    } finally {
      setBusy(false);
    }
  };

  const dropLate = async () => {
    if (!snap) return;
    const closed = snap.cycles.find((c) => c.status === "closed") ?? snap.cycles.find((c) => c.status === "late");
    if (!closed) return;
    setBusy(true);
    try {
      await api.late(closed.cycle_date, closed.cycle_no, "E-9407");
      await load();
    } finally {
      setBusy(false);
    }
  };

  const replay = async (deadId: number) => {
    setBusy(true);
    try {
      await api.replay(deadId);
      await load();
    } finally {
      setBusy(false);
    }
  };

  const rejectRate =
    snap && snap.inbox_files > 0 ? ((snap.reject_count / snap.inbox_files) * 100).toFixed(0) : "0";

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-5 px-4 py-6 sm:px-6">
      <header className="flex flex-col gap-3 border-b border-border/80 pb-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-medium tracking-[0.16em] text-teal-300 uppercase">
            Clearing Cycle Ingest
          </p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">Cycle intake board</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
            Member files, FX and BIN APIs, an internal endpoint registry, and yesterday’s parquet.
            A cycle closes only when every required endpoint has landed.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" onClick={() => void run()} disabled={busy || !snap}>
            Run inbox
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => void dropLate()}
            disabled={busy || !snap || !snap.cycles.some((c) => c.status === "closed" || c.status === "late")}
          >
            Drop late file
          </Button>
        </div>
      </header>

      {error ? (
        <div className="rounded-xl border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm">
          Engine is down on :18771. {error}
        </div>
      ) : null}

      {!snap ? (
        <p className="text-sm text-muted-foreground">Loading catalog…</p>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Card size="sm">
              <CardHeader>
                <CardDescription>Clearing rows</CardDescription>
                <CardTitle className="font-mono text-2xl">{snap.row_count}</CardTitle>
              </CardHeader>
            </Card>
            <Card size="sm">
              <CardHeader>
                <CardDescription>Dead letters</CardDescription>
                <CardTitle className="font-mono text-2xl">{snap.dead_letters.length}</CardTitle>
              </CardHeader>
            </Card>
            <Card size="sm">
              <CardHeader>
                <CardDescription>Reject rate</CardDescription>
                <CardTitle className="font-mono text-2xl">{rejectRate}%</CardTitle>
              </CardHeader>
            </Card>
            <Card size="sm">
              <CardHeader>
                <CardDescription>Bytes landed</CardDescription>
                <CardTitle className="font-mono text-2xl">{formatBytes(snap.bytes_landed)}</CardTitle>
              </CardHeader>
            </Card>
          </div>

          <Tabs defaultValue="cycles">
            <TabsList variant="line">
              <TabsTrigger value="cycles">Cycles</TabsTrigger>
              <TabsTrigger value="catalog">Catalog</TabsTrigger>
              <TabsTrigger value="inbox">Inbox</TabsTrigger>
            </TabsList>
            <TabsContent value="cycles" className="pt-4">
              <div className="grid gap-3 md:grid-cols-2">
                {snap.cycles.map((cycle) => (
                  <Card key={`${cycle.cycle_date}-${cycle.cycle_no}`}>
                    <CardHeader>
                      <div className="flex items-center justify-between">
                        <CardTitle>Cycle {cycle.cycle_no}</CardTitle>
                        <span className={`text-xs font-medium uppercase ${statusTone[cycle.status]}`}>
                          {cycle.status}
                        </span>
                      </div>
                      <CardDescription>
                        Required {cycle.required.length} · landed {cycle.landed.length}
                        {cycle.missing.length ? ` · missing ${cycle.missing.join(", ")}` : ""}
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="flex flex-wrap gap-1.5">
                      {(cycle.endpoints ?? []).map((ep) => (
                        <span
                          key={ep.id}
                          className={`rounded-full border border-border px-2 py-0.5 font-mono text-[11px] ${statusTone[ep.status] ?? ""}`}
                        >
                          {ep.id}
                          {ep.required ? "" : " opt"} · {ep.status}
                        </span>
                      ))}
                    </CardContent>
                  </Card>
                ))}
              </div>
            </TabsContent>
            <TabsContent value="catalog" className="pt-4 space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle>Sources</CardTitle>
                  <CardDescription>
                    Five ingest contracts. Watermark is the last as-of each source has actually landed.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Source</TableHead>
                        <TableHead>Kind</TableHead>
                        <TableHead>Watermark</TableHead>
                        <TableHead>Owner</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {snap.sources.map((source) => (
                        <TableRow key={source.id}>
                          <TableCell>
                            <div>{source.name}</div>
                            <div className="text-xs text-muted-foreground">{source.contract}</div>
                            <div className="text-xs text-muted-foreground">{source.cadence}</div>
                          </TableCell>
                          <TableCell>
                            <Badge variant="outline">{source.kind}</Badge>
                          </TableCell>
                          <TableCell className="font-mono text-xs">{source.watermark ?? "—"}</TableCell>
                          <TableCell>{source.owner}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>Endpoints</CardTitle>
                  <CardDescription>Required destinations must land before a cycle can close.</CardDescription>
                </CardHeader>
                <CardContent>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Endpoint</TableHead>
                        <TableHead>Member</TableHead>
                        <TableHead>City</TableHead>
                        <TableHead>Required</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {snap.endpoints.map((ep) => (
                        <TableRow key={ep.id}>
                          <TableCell className="font-mono text-xs">{ep.id}</TableCell>
                          <TableCell>{ep.member_id}</TableCell>
                          <TableCell>{ep.city}</TableCell>
                          <TableCell>{ep.required ? "yes" : "optional"}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            </TabsContent>
            <TabsContent value="inbox" className="pt-4 space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle>Landed and rejected files</CardTitle>
                  <CardDescription>
                    {snap.inbox.length
                      ? `${snap.inbox_files} fingerprints · ${snap.reject_count} rejected`
                      : "Inbox is empty. Seed writes today’s packs on engine boot."}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {snap.inbox.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No files have been fingerprinted yet.</p>
                  ) : (
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Status</TableHead>
                          <TableHead>File</TableHead>
                          <TableHead>Reason</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {snap.inbox.map((row) => (
                          <TableRow key={row.id}>
                            <TableCell className={statusTone[row.status] ?? ""}>{row.status}</TableCell>
                            <TableCell className="max-w-[280px] truncate font-mono text-xs">
                              {row.file_id ?? row.path}
                            </TableCell>
                            <TableCell className="text-xs">{row.reason ?? "—"}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  )}
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>Dead letters</CardTitle>
                  <CardDescription>
                    Contract failures. Replay writes a repaired pack for that endpoint and lands it.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3 text-sm">
                  {snap.dead_letters.length === 0 ? (
                    <p className="text-muted-foreground">No dead letters.</p>
                  ) : (
                    snap.dead_letters.map((row) => (
                      <div
                        key={row.id}
                        className="flex flex-col gap-2 rounded-lg border border-border px-3 py-2 sm:flex-row sm:items-center sm:justify-between"
                      >
                        <div>
                          <p className="font-medium text-rose-300">{row.reason}</p>
                          <p className="font-mono text-xs text-muted-foreground">
                            {row.endpoint_id ?? "?"} · cycle {row.cycle_no ?? "?"} · {row.path}
                          </p>
                          {row.replayed_at ? (
                            <p className="text-xs text-teal-300">Replayed {row.replayed_at}</p>
                          ) : null}
                        </div>
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={busy || !row.endpoint_id}
                          onClick={() => void replay(row.id)}
                        >
                          Replay
                        </Button>
                      </div>
                    ))
                  )}
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </>
      )}
    </div>
  );
}
