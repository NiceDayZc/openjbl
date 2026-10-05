# OpenJBL GUI front end

Vite + React + Tailwind + shadcn/ui (Radix, Nova preset, neutral). `npm run build`
writes the page into `../src/openjbl/web/`, which `openjbl-gui` serves.

- `src/lib/api.ts` -- the JSON API client; every call carries the per-launch token.
- `src/lib/eq.ts` -- RBJ biquads for the response curve, and slider snapping.
- `src/App.tsx` -- layout and state; `src/components/` -- the panels.
