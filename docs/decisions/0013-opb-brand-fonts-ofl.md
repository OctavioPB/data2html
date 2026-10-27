# ADR 0013 — OPB brand in the viewer; self-hosted fonts under the SIL Open Font License

**Status:** accepted · 2026-10-27

## Context
The readers' surfaces (the live viewer `/r/…`, the report index and the sign-in pages) adopt the brand
system of Octavio Pérez Bravo ("OPB"): Fraunces for display and titles, Plus Jakarta Sans for body text,
navy/gold tokens, and the "From Pipeline to Decision" monogram and logo. ADR 0006 allows only MIT, Apache or
BSD licenses. Both typefaces are licensed under the **SIL Open Font License 1.1 (OFL)**.

## Decision
1. **OFL is accepted for fonts only** (not for code). OFL allows use, embedding and redistribution, including
   in commercial products; it forbids selling the fonts by themselves and reusing the reserved font names
   for modified versions. We ship the original, unmodified files.
2. **The fonts are self-hosted**: `render/static/fonts/` holds the variable `woff2` files (latin subset:
   Fraunces with its `opsz` and `wght` axes, roman and italic; Plus Jakarta Sans with its `wght` axis), taken
   from the Fontsource packages `@fontsource-variable/fraunces` and `@fontsource-variable/plus-jakarta-sans`
   5.3.0, next to their license texts (`OFL-*.txt`). No request leaves for Google Fonts, so the viewer's CSP
   only gains `font-src 'self'`.
3. **Scope**: the viewer and the sign-in pages. The studio (the author's tool) keeps its own neutral style.
4. **Charts** use a categorical palette derived from the brand and validated with the dataviz checks
   (lightness band, chroma floor, colour-blind separation, contrast against white). In fixed order: `#2D69AE`
   (corporate blue), `#B8871F` (gold), `#7C4DBD` (purple), `#E05080` (pink), `#3E9BD6` (light blue). The
   brand's semantic colours (green, red, orange) are reserved for states and never used as series colours.
   A colour dimension with more than 5 values falls back to the table view instead of repeating colours.

## Consequences
- Adding another typeface, or another OFL asset, needs no new ADR as long as it is a font shipped unmodified
  with its license text.
- The viewer is light only: the brand defines no dark theme, so `prefers-color-scheme` no longer switches it.
- The latin subset covers Spanish and English; other scripts would fall back to Georgia / the system sans.
