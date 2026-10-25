"use client";

/**
 * One shared connection to the backend for the whole app:
 *  - loads /api/state, then opens the /events SSE stream
 *  - keeps the session (mode, running, streaming, fleet) up to date
 *  - lets components subscribe to raw live events
 *  - reconnects automatically if the backend restarts
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { API, EMPTY_SESSION, getJSON, post, type LiveEvent, type Scenario, type Session } from "./api";

type Listener = (e: LiveEvent) => void;

interface LiveValue {
  session: Session;
  scenarios: Scenario[];
  /** null while the first connection attempt is in progress */
  online: boolean | null;
  subscribe: (fn: Listener) => () => void;
  send: (path: string, body?: object) => Promise<void>;
  toast: string | null;
  notify: (msg: string) => void;
}

const LiveContext = createContext<LiveValue | null>(null);

function sessionFromEvent(e: LiveEvent): Partial<Session> {
  const out: Partial<Session> = {};
  for (const k of ["mode", "running", "streaming", "fleet", "broker_port", "tap_port", "state", "message"] as const) {
    if (k in e) (out as Record<string, unknown>)[k] = e[k];
  }
  return out;
}

export function LiveProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session>(EMPTY_SESSION);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [online, setOnline] = useState<boolean | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const listeners = useRef(new Set<Listener>());
  const toastTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const notify = useCallback((msg: string) => {
    setToast(msg);
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 5000);
  }, []);

  useEffect(() => {
    let es: EventSource | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let cancelled = false;

    const load = async () => {
      try {
        const s = await getJSON<{ session: Session; scenarios: Scenario[] }>("/api/state");
        if (cancelled) return;
        setScenarios(s.scenarios);
        setSession({ ...EMPTY_SESSION, ...s.session, state: s.session.running ? "running" : "stopped" });
        setOnline(true);
        open();
      } catch {
        if (cancelled) return;
        setOnline(false);
        timer = setTimeout(load, 2500);
      }
    };

    const open = () => {
      es = new EventSource(`${API}/events`);
      es.onmessage = (m) => {
        let e: LiveEvent;
        try {
          e = JSON.parse(m.data);
        } catch {
          return;
        }
        if (e.kind === "hello") {
          setSession((s) => ({ ...s, ...e.session, state: e.session.running ? "running" : "stopped" }));
        } else if (e.kind === "session") {
          setSession((s) => ({ ...s, ...sessionFromEvent(e) }));
          if (e.state === "error" && e.message) notify(String(e.message));
        } else if (e.kind === "error" && e.message) {
          notify(String(e.message));
        }
        listeners.current.forEach((fn) => fn(e));
      };
      es.onerror = () => {
        es?.close();
        if (cancelled) return;
        setOnline(false);
        timer = setTimeout(load, 2500);
      };
    };

    load();
    return () => {
      cancelled = true;
      clearTimeout(timer);
      es?.close();
    };
  }, [notify]);

  const subscribe = useCallback((fn: Listener) => {
    listeners.current.add(fn);
    return () => {
      listeners.current.delete(fn);
    };
  }, []);

  const send = useCallback(
    async (path: string, body?: object) => {
      const r = await post(path, body);
      if (r.offline) setOnline(false);
      else if (!r.ok && r.error) notify(r.error);
    },
    [notify],
  );

  const value = useMemo(
    () => ({ session, scenarios, online, subscribe, send, toast, notify }),
    [session, scenarios, online, subscribe, send, toast, notify],
  );
  return <LiveContext.Provider value={value}>{children}</LiveContext.Provider>;
}

export function useLive(): LiveValue {
  const v = useContext(LiveContext);
  if (!v) throw new Error("useLive must be used inside <LiveProvider>");
  return v;
}

/** Subscribe to raw live events for the lifetime of the component. */
export function useLiveEvents(fn: Listener) {
  const { subscribe } = useLive();
  const ref = useRef(fn);
  useEffect(() => {
    ref.current = fn;
  });
  useEffect(() => subscribe((e) => ref.current(e)), [subscribe]);
}

/** Poll a GET endpoint every `ms` milliseconds. */
export function usePoll<T>(path: string | null, ms: number): { data: T | null; error: string | null } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!path) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = async () => {
      try {
        const d = await getJSON<T>(path);
        if (alive) {
          setData(d);
          setError(null);
        }
      } catch (err) {
        if (alive) setError(String(err));
      }
      if (alive && ms > 0) timer = setTimeout(tick, ms);
    };
    tick();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [path, ms]);
  return { data, error };
}
