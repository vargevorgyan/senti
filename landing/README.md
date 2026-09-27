# Senti landing page

Static marketing page. Vite + TypeScript, animations with GSAP (ScrollTrigger) and Lenis smooth scroll.

```bash
npm install
npm run dev       # http://localhost:5173
npm run build     # static site in dist/, host anywhere
```

Content is in `index.html`, styles in `src/style.css`, motion in `src/main.ts` (the hero checkpoint list is `ACTIONS`).
Incident facts come from `.okf/research/agent-incidents.md`; keep them in sync. Respects `prefers-reduced-motion`.
