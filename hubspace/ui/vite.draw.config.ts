import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { viteStaticCopy } from "vite-plugin-static-copy";

// Phase 02 — Excalidraw entry (draw.tsx).
//
// Separate config from the hub index build: the index (hub.js) is IIFE because it
// reads lexical globals from hub.html, but Excalidraw needs React.lazy code-
// splitting, which requires ES-module output. draw.js is loaded as
// <script type="module"> on the dedicated /draw and /doc/<slug> canvas pages
// (fresh pages we fully control), so ESM is fine there.
//
// Fonts are vendored: the whole excalidraw-assets/ dir is copied verbatim into
// static/. draw.tsx sets window.EXCALIDRAW_ASSET_PATH="/static/" so Excalidraw
// fetches fonts from /static/excalidraw-assets/ — fully offline, no CDN.
export default defineConfig({
  plugins: [
    react(),
    viteStaticCopy({
      targets: [
        {
          src: "node_modules/@excalidraw/excalidraw/dist/excalidraw-assets",
          dest: ".", // -> ../static/excalidraw-assets
        },
      ],
    }),
  ],
  define: {
    "process.env.IS_PREACT": JSON.stringify("false"),
  },
  // Assets/chunks are served from /static/, so lazy-import + modulepreload URLs
  // must be prefixed accordingly (draw.js loads chunk-main.js as /static/chunk-main.js).
  base: "/static/",
  build: {
    outDir: "../static",
    emptyOutDir: false,
    rollupOptions: {
      input: "src/draw.tsx",
      output: {
        format: "es",
        entryFileNames: "draw.js",
        chunkFileNames: "chunk-[name].js",
        assetFileNames: (info) =>
          info.name && info.name.endsWith(".css") ? "draw.css" : "[name][extname]",
      },
    },
  },
});
