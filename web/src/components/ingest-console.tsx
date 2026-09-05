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
};

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
    const closed = snap.cycles.find((c) => c.status === "closed" || c.status === "partial");
    const endpoint = closed?.missing[0] ?? "E-9407";
    const cycle = closed ?? snap.cycles[0];
    setBusy(true);
    try {
      await api.late(cycle.cycle_date, cycle.cycle_no, endpoint);
      await load();
    } finally {
      setBusy(false);
    }
  };

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
          <Button size="sm" variant="outline" onClick={() => void dropLate()} disabled={busy || !snap}>
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
          <div className="grid gap-3 sm:grid-cols-3">
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
                <CardDescription>Today</CardDescription>
                <CardTitle className="font-mono text-2xl">{snap.today}</CardTitle>
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
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="text-sm">
                      {cycle.missing.length ? (
                        <p>Missing: {cycle.missing.join(", ")}</p>
                      ) : (
                        <p className="text-teal-300">All required endpoints landed.</p>
                      )}
                    </CardContent>
                  </Card>
                ))}
              </div>
            </TabsContent>
            <TabsContent value="catalog" className="pt-4">
              <Card>
                <CardHeader>
                  <CardTitle>Sources</CardTitle>
                  <CardDescription>Five ingest contracts. Cadence and owner live on the catalog row.</CardDescription>
                </CardHeader>
                <CardContent>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Source</TableHead>
                        <TableHead>Kind</TableHead>
                        <TableHead>Cadence</TableHead>
                        <TableHead>Owner</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {snap.sources.map((source) => (
                        <TableRow key={source.id}>
                          <TableCell>
                            <div>{source.name}</div>
                            <div className="text-xs text-muted-foreground">{source.contract}</div>
                          </TableCell>
                          <TableCell>
                            <Badge variant="outline">{source.kind}</Badge>
                          </TableCell>
                          <TableCell>{source.cadence}</TableCell>
                          <TableCell>{source.owner}</TableCell>
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
                </CardHeader>
                <CardContent>
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
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>Dead letters</CardTitle>
                  <CardDescription>Contract failures. Replay is a no-op until the pack is repaired.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3 text-sm">
                  {snap.dead_letters.length === 0 ? (
                    <p className="text-muted-foreground">No dead letters.</p>
                  ) : (
                    snap.dead_letters.map((row) => (
                      <div key={row.id} className="rounded-lg border border-border px-3 py-2">
                        <p className="font-medium text-rose-300">{row.reason}</p>
                        <p className="font-mono text-xs text-muted-foreground">{row.path}</p>
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
