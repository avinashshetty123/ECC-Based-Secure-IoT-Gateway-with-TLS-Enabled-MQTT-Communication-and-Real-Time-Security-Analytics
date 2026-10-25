"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import { useLive } from "@/lib/live";
import { MODE_INFO } from "@/lib/api";

const LINKS = [
  { href: "/", label: "Live demo" },
  { href: "/analytics", label: "Analytics" },
  { href: "/benchmarks", label: "Benchmarks" },
  { href: "/learn", label: "Learn" },
];

export default function Nav() {
  const path = usePathname();
  const { session, online } = useLive();
  const st = online === false ? "offline" : session.state ?? (session.running ? "running" : "stopped");
  const label =
    st === "offline" ? "backend offline"
      : st === "running" && session.mode ? `running · ${MODE_INFO[session.mode].label}${session.fleet ? ` · fleet ${session.fleet.devices}` : ""}`
        : st;

  return (
    <nav className="nav">
      <div className="brand">
        <div className="brand-logo">🔐</div>
        <div>
          <b>Secure IoT Gateway</b>
          <span>ECC · TLS 1.3 · MQTT · analytics</span>
        </div>
      </div>
      <div className="nav-links">
        {LINKS.map((l) => {
          const active = l.href === "/" ? path === "/" : path.startsWith(l.href);
          return (
            <Link key={l.href} href={l.href} className={active ? "active" : ""}>
              {l.label}
              {active && (
                <motion.span
                  layoutId="nav-underline"
                  style={{ position: "absolute", left: 10, right: 10, bottom: 2, height: 2, borderRadius: 2, background: "#60a5fa" }}
                />
              )}
            </Link>
          );
        })}
      </div>
      <div className="spacer" />
      <span className={`pill ${st}`}>
        <span className="dot" />
        {label}
      </span>
    </nav>
  );
}
