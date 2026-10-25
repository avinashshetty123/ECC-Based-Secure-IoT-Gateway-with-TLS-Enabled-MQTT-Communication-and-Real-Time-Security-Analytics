"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import type { Mode } from "@/lib/api";
import { useLive } from "@/lib/live";
import { SPEED_FACTOR, useVisualizer, type Speed } from "@/lib/useVisualizer";
import Toolbar from "@/components/live/Toolbar";
import Stepper from "@/components/live/Stepper";
import Scene from "@/components/live/Scene";
import Explain from "@/components/live/Explain";
import Actions from "@/components/live/Actions";
import DetailTabs from "@/components/live/DetailTabs";

const reveal = (i: number) => ({
  initial: { opacity: 0, y: 14 }, animate: { opacity: 1, y: 0 }, transition: { delay: 0.06 * i, duration: 0.35 },
});

/**
 * Live demo, top to bottom:
 *   1 toolbar → 2 stepper → 3 scene + explanation → 4 actions → 5 details (tabs)
 */
export default function LiveDemoPage() {
  const { session } = useLive();
  const [mode, setMode] = useState<Mode>("mtls");
  const [speed, setSpeed] = useState<Speed>("slow");
  const { viz, dispatch, waiting, queued, next } = useVisualizer(mode, speed);

  // Follow the backend when it reports a running mode (e.g. after a page reload)
  useEffect(() => {
    if (session.mode && session.mode !== mode) {
      setMode(session.mode);
      dispatch({ type: "setMode", mode: session.mode });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.mode]);

  const changeMode = (m: Mode) => {
    setMode(m);
    dispatch({ type: "setMode", mode: m });
  };

  return (
    <main className="page live">
      <motion.div className="live-head" {...reveal(0)}>
        <h1>Follow one sensor reading from the field to the database</h1>
        <p>Everything you see is real traffic from a running broker, except the sensor values and the hardware drawing.</p>
      </motion.div>

      <motion.div {...reveal(1)}>
        <Toolbar mode={mode} onMode={changeMode} speed={speed} onSpeed={setSpeed} waiting={waiting} queued={queued} onNext={next} />
      </motion.div>

      <motion.div {...reveal(2)}>
        <Stepper pipe={viz.pipe} />
      </motion.div>

      <motion.div className="hero" {...reveal(3)}>
        <Scene viz={viz} mode={mode} session={session} dispatch={dispatch} slow={SPEED_FACTOR[speed]} />
        <Explain viz={viz} mode={mode} running={session.running} />
      </motion.div>

      <motion.div {...reveal(4)}>
        <Actions mode={mode} runningScenario={viz.runningScenario} />
      </motion.div>

      <motion.div {...reveal(5)}>
        <DetailTabs viz={viz} />
      </motion.div>

      <p className="footer-note">
        Demo certificates come from a local CA and are not publicly trusted. The eavesdropper is a local relay that forwards
        bytes unchanged; it cannot decrypt TLS.
      </p>
    </main>
  );
}
