// Excalidraw canvas entry (Phase 02). Loaded as an ES module on /draw and on
// /doc/<slug> for .excalidraw files. The heavy Excalidraw bundle is code-split
// via React.lazy so the page paints a skeleton first, then hydrates the canvas.
//
// Contract with render/draw.py (which serves the host page):
//   window.EXCALIDRAW_ASSET_PATH — vendored font root ("/static/")
//   window.DRAW_STATE = { rel: string | null, data: <scene JSON> | null }
//     rel  — vault-relative path of the file (null => new, unsaved diagram)
//     data — parsed .excalidraw scene ({elements, appState, files}) or null
// Saving POSTs { rel, scene } to /draw/save; the server returns { ok, rel } and
// we adopt the server-assigned rel for a brand-new diagram.
import "./draw.css";
import { StrictMode, Suspense, lazy, useCallback, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";

// Must be set before the Excalidraw chunk evaluates so its fonts resolve to the
// vendored /static/excalidraw-assets/ dir (fully offline, no CDN).
(window as any).EXCALIDRAW_ASSET_PATH = "/static/";

type DrawState = { rel: string | null; data: any | null };
const STATE: DrawState = (window as any).DRAW_STATE || { rel: null, data: null };

// Optional target directory for a NEW diagram (e.g. a task's tasks/<slug>/draws),
// passed as /draw?dir=... by the manifest page's "New draw" button.
const DIR: string | null = new URLSearchParams(window.location.search).get("dir");

// Lazy so the ~1 MB Excalidraw bundle is a separate chunk, deferred until paint.
const Excalidraw = lazy(() =>
  import("@excalidraw/excalidraw").then((m) => ({ default: m.Excalidraw })),
);

function App() {
  const apiRef = useRef<any>(null);
  const relRef = useRef<string | null>(STATE.rel);
  const [status, setStatus] = useState<string>("");

  const save = useCallback(async () => {
    const api = apiRef.current;
    if (!api) return;
    setStatus("saving…");
    const mod = await import("@excalidraw/excalidraw");
    const scene = mod.serializeAsJSON(
      api.getSceneElements(),
      api.getAppState(),
      api.getFiles(),
      "local",
    );
    try {
      const res = await fetch("/draw/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          rel: relRef.current,
          dir: relRef.current ? null : DIR, // only for a brand-new diagram
          scene: JSON.parse(scene),
        }),
      });
      if (!res.ok) throw new Error(String(res.status));
      const out = await res.json();
      if (out.rel) {
        relRef.current = out.rel;
        // Reflect the saved file's path in the URL without reloading the canvas.
        // Files are served at /<vault-relative-path> (resolved against scan root).
        const url = "/" + String(out.rel).split("/").map(encodeURIComponent).join("/");
        history.replaceState(null, "", url);
      }
      setStatus("saved ✓");
    } catch (e) {
      setStatus("save failed");
    }
    setTimeout(() => setStatus(""), 2000);
  }, []);

  // ⌘S / Ctrl+S saves into the vault. Intercept on window in the CAPTURE phase so
  // it fires before Excalidraw's own document-level handler — otherwise Excalidraw
  // also runs its "Save to disk" action and the browser's native file picker pops up.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        void save();
      }
    };
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [save]);

  return (
    <div style={{ position: "fixed", inset: 0 }}>
      <Excalidraw
        excalidrawAPI={(api: any) => (apiRef.current = api)}
        initialData={STATE.data || undefined}
      />
      {status && (
        <div
          style={{
            position: "fixed",
            bottom: 12,
            right: 12,
            padding: "4px 10px",
            borderRadius: 6,
            background: "rgba(0,0,0,.75)",
            color: "#fff",
            font: "12px system-ui, sans-serif",
            zIndex: 10,
          }}
        >
          {status}
        </div>
      )}
    </div>
  );
}

createRoot(document.getElementById("app")!).render(
  <StrictMode>
    <Suspense fallback={<div className="draw-skeleton">loading canvas…</div>}>
      <App />
    </Suspense>
  </StrictMode>,
);
