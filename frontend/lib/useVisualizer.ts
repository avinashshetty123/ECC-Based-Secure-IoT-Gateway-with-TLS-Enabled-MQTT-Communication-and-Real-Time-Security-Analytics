"use client";

import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { useLiveEvents } from "./live";
import { initialState, paceFor, reduce, type Action, type VizState } from "./visualizer";
import type { LiveEvent, Mode } from "./api";

export type Speed = "step" | "slow" | "normal";
/** Multiplier on the base pacing and on packet travel time. */
export const SPEED_FACTOR: Record<Speed, number> = { step: 2.2, slow: 2.6, normal: 1 };

const ANIMATED = new Set(["hello", "session","wire_conn", "wire", "connect", "app_publish", "broker_log", "gateway_rx",
  "gateway_reject", "scenario", "verdict"]);

export interface Visualizer {
  viz: VizState;
  dispatch: (a: Action) => void;
  /** step mode: true while paused, waiting for next() */
  waiting: boolean;
  /** events received but not shown yet */
  queued: number;
  next: () => void;
}

/**
 * Feeds live events into the visual reducer at a pace a person can follow.
 * - normal: ~0.3 s between steps (a TLS handshake really takes a few ms)
 * - slow:   ~2.6x slower, for explaining
 * - step:   pauses after every meaningful event until next() is called (presenter mode)
 * In normal/slow mode a big backlog is fast-forwarded so the screen never lags far behind reality.
 */
export function useVisualizer(mode: Mode, speed: Speed): Visualizer {
  const [viz, dispatch] = useReducer(reduce, mode, initialState);
  const [waiting, setWaiting] = useState(false);
  const [queued, setQueued] = useState(0);
  const queue = useRef<LiveEvent[]>([]);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const paused = useRef(false);
  const speedRef = useRef(speed);

  const pump = useCallback(() => {
    timer.current = null;
    const e = queue.current.shift();
    setQueued(queue.current.length);
    if (!e) return;
    dispatch({ type: "event", e });
    const pace = paceFor(e);
    if (speedRef.current === "step" && pace > 0) {
      paused.current = true;
      setWaiting(true);
      return;
    }
    const backlog = queue.current.length;
    const catchUp = speedRef.current === "slow" ? (backlog > 60 ? 0.05 : backlog > 25 ? 0.4 : 1)
      : backlog > 30 ? 0.05 : backlog > 12 ? 0.3 : 1;
    timer.current = setTimeout(pump, pace * SPEED_FACTOR[speedRef.current] * catchUp);
  }, []);

  const next = useCallback(() => {
    if (!paused.current) return;
    paused.current = false;
    setWaiting(false);
    pump();
  }, [pump]);

  // Leaving step mode resumes automatically
  useEffect(() => {
    speedRef.current = speed;
    if (speed !== "step" && paused.current) next();
  }, [speed, next]);

  useLiveEvents((e) => {
    if (!ANIMATED.has(e.kind)) return;
    if (e.kind === "broker_log" && !/PUBLISH/.test(e.line || "")) return; // only publish/deny lines drive visuals
    queue.current.push(e);
    setQueued(queue.current.length);
    if (timer.current === null && !paused.current) pump();
  });

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  return { viz, dispatch, waiting, queued, next };
}
