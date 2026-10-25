# Frontend: Next.js web app

The user interface for the Secure IoT Gateway. All data comes from the Python backend API at
`http://127.0.0.1:8600` (override with `NEXT_PUBLIC_API_URL`).

```powershell
npm install      # first time only
npm run dev      # http://localhost:3000  (start the backend first: ..\backend\scripts\start_backend.ps1)
```

If the backend isn't running, the app shows a help screen with the start command and reconnects automatically.

## Pages
- `app/page.tsx`: **Live demo**. Animated message path, stage tracker, narrator, handshake steps, triggers, logs.
- `app/analytics/page.tsx`: **Analytics** from SQLite (polled every 3 s).
- `app/benchmarks/page.tsx`: **Benchmarks** A/B/C from `backend/reports/benchmarks/`.
- `app/learn/page.tsx`: **Learn**. Animated explainers (ECDHE, TLS 1.3 handshake, record anatomy).

## How the live demo works
- `lib/live.tsx`: one shared Server-Sent Events connection (`/events`) plus session state for every page.
- `lib/visualizer.ts`: a pure reducer that turns each real backend event (wire record, connection result, gateway
  decision, verdict…) into visual state: packets, stages, steps, narration.
- `lib/useVisualizer.ts`: paces bursts of events (a TLS handshake arrives within milliseconds) so each step is
  visible, and speeds up automatically if it falls behind.
- `components/charts.tsx`: small dependency-free SVG charts.

Styling is plain CSS (`app/globals.css`); animations use `framer-motion`.
