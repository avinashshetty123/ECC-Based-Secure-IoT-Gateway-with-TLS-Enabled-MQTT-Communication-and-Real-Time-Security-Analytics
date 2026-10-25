"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useLive } from "@/lib/live";
import { API } from "@/lib/api";

/** "Backend offline" help screen + toast messages. */
export default function Overlays() {
  const { online, toast } = useLive();
  return (
    <>
      <AnimatePresence>
        {online === false && (
          <motion.div className="offline" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <motion.div className="box" initial={{ y: 20, scale: 0.97 }} animate={{ y: 0, scale: 1 }}>
              <h2>The backend is not running</h2>
              <p>
                This page gets everything (broker, devices, eavesdropper, analytics) from the Python backend at{" "}
                <code>{API}</code>. Start it with <b>one</b> of these:
              </p>
              <p>
                1. Double-click <code>start.bat</code> in the project folder (starts backend + frontend), <b>or</b>
                <br />
                2. In a terminal opened in the project folder:
              </p>
              <pre>powershell -ExecutionPolicy Bypass -File backend\scripts\start_backend.ps1</pre>
              <p className="muted small">Keep that window open. This page reconnects automatically every few seconds.</p>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
      <AnimatePresence>
        {toast && (
          <motion.div className="toast" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 16 }}>
            {toast}
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
