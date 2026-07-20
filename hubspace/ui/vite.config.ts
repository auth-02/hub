import { defineConfig } from "vite";

// Phase 01 — UI extraction.
//
// The index page's script (hub.js) reads lexical `const` globals (FTS_DATA,
// _currentRoot, …) that hub.html defines in an inline classic <script>. ES
// modules cannot see those bindings, so we emit **IIFE** (a classic script) —
// hub.html's `<script src="/static/hub.js">` tag then works unchanged.
//
// outDir is ../static (which ships in the wheel); emptyOutDir:false so the
// build never wipes hub.html. public/ (favicon.svg + the Python-inlined
// page/backlinks/chrome CSS) is copied verbatim into static/ by Vite.
export default defineConfig({
  build: {
    outDir: "../static",
    emptyOutDir: false,
    cssCodeSplit: false,
    rollupOptions: {
      input: "src/index.ts",
      output: {
        format: "iife",
        entryFileNames: "hub.js",
        assetFileNames: (info) =>
          info.name && info.name.endsWith(".css") ? "hub.css" : "[name][extname]",
      },
    },
  },
});
