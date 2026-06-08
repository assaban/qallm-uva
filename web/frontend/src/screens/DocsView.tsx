/**
 * DocsView: read the project's own documentation inside the app.
 *
 * The README and key docs are a treasure for the project and the thesis;
 * this surfaces them in the UI. The backend renders the Markdown to HTML
 * (the content is first-party and trusted), so this component fetches and
 * displays it, with a sidebar to switch between docs. Styling for the
 * rendered HTML is scoped here since the project does not use a Tailwind
 * typography plugin.
 */

import { useEffect, useRef, useState } from "react";
import { BookOpen } from "lucide-react";
import * as api from "../api";

interface DocMeta {
  id: string;
  title: string;
  path: string;
}

export default function DocsView() {
  const [docs, setDocs] = useState<DocMeta[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [html, setHtml] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const contentRef = useRef<HTMLElement | null>(null);

  // Load the doc list once, then select the first (README).
  useEffect(() => {
    let alive = true;
    api.listDocs()
      .then((r) => {
        if (!alive) return;
        setDocs(r.docs);
        if (r.docs.length) setActiveId(r.docs[0].id);
        else setLoading(false);
      })
      .catch((e) => {
        if (!alive) return;
        setError(String(e));
        setLoading(false);
      });
    return () => { alive = false; };
  }, []);

  // Fetch the active doc's HTML whenever the selection changes.
  useEffect(() => {
    if (!activeId) return;
    let alive = true;
    setLoading(true);
    setError(null);
    api.getDoc(activeId)
      .then((r) => { if (alive) { setHtml(r.html); setLoading(false); } })
      .catch((e) => { if (alive) { setError(String(e)); setLoading(false); } });
    return () => { alive = false; };
  }, [activeId]);

  // After the rendered HTML lands in the DOM, turn any <pre class="mermaid">
  // blocks into diagrams. Mermaid is large and only needed here, so it is
  // dynamically imported (and initialised once) the first time a doc with a
  // diagram is shown, keeping it out of the main bundle. Guarded so a
  // malformed diagram does not break the rest of the page.
  useEffect(() => {
    if (loading || error || !contentRef.current) return;
    const blocks = contentRef.current.querySelectorAll<HTMLElement>("pre.mermaid");
    if (blocks.length === 0) return;
    let cancelled = false;
    (async () => {
      try {
        const mermaid = (await import("mermaid")).default;
        if (cancelled) return;
        mermaid.initialize({ startOnLoad: false, theme: "neutral", securityLevel: "strict" });
        await mermaid.run({ nodes: Array.from(blocks) });
      } catch (e) {
        if (!cancelled) console.error("Mermaid render failed:", e);
      }
    })();
    return () => { cancelled = true; };
  }, [html, loading, error]);

  return (
    <div className="mx-auto flex max-w-5xl gap-6">
      <style>{docStyles}</style>

      {/* Sidebar */}
      <nav className="w-56 shrink-0">
        <div className="mb-2 flex items-center gap-1.5 px-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
          <BookOpen className="h-3.5 w-3.5" /> Documentation
        </div>
        <ul className="space-y-0.5">
          {docs.map((d) => (
            <li key={d.id}>
              <button
                onClick={() => setActiveId(d.id)}
                className={`w-full rounded-lg px-3 py-1.5 text-left text-sm ${
                  d.id === activeId
                    ? "bg-slate-900 text-white"
                    : "text-slate-600 hover:bg-slate-100"
                }`}
              >
                {d.title}
              </button>
            </li>
          ))}
          {docs.length === 0 && !loading && (
            <li className="px-3 py-1.5 text-sm text-slate-400">No docs found.</li>
          )}
        </ul>
      </nav>

      {/* Content */}
      <main className="min-w-0 flex-1">
        {error && (
          <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            Could not load documentation: {error}
          </div>
        )}
        {loading && !error && (
          <div className="animate-pulse text-sm text-slate-400">Loading…</div>
        )}
        {!loading && !error && (
          <article
            ref={contentRef}
            className="qallm-doc rounded-2xl border border-slate-200 bg-white p-8"
            dangerouslySetInnerHTML={{ __html: html }}
          />
        )}
      </main>
    </div>
  );
}

// Scoped typographic styles for the rendered Markdown. Kept minimal and
// readable; matches the app's slate palette.
const docStyles = `
.qallm-doc { color: #334155; line-height: 1.7; font-size: 0.925rem; }
.qallm-doc h1 { font-size: 1.6rem; font-weight: 600; margin: 0 0 0.75rem; color: #0f172a; }
.qallm-doc h2 { font-size: 1.25rem; font-weight: 600; margin: 1.75rem 0 0.6rem; color: #0f172a; border-bottom: 1px solid #e2e8f0; padding-bottom: 0.3rem; }
.qallm-doc h3 { font-size: 1.05rem; font-weight: 600; margin: 1.4rem 0 0.4rem; color: #1e293b; }
.qallm-doc p { margin: 0.7rem 0; }
.qallm-doc a { color: #4f46e5; text-decoration: none; }
.qallm-doc a:hover { text-decoration: underline; }
.qallm-doc ul, .qallm-doc ol { margin: 0.7rem 0; padding-left: 1.4rem; }
.qallm-doc li { margin: 0.3rem 0; }
.qallm-doc code { background: #f1f5f9; padding: 0.1rem 0.35rem; border-radius: 0.3rem; font-size: 0.85em; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.qallm-doc pre { background: #0f172a; color: #e2e8f0; padding: 1rem; border-radius: 0.6rem; overflow-x: auto; margin: 0.9rem 0; }
.qallm-doc pre code { background: transparent; color: inherit; padding: 0; }
.qallm-doc pre.mermaid { background: transparent; color: inherit; padding: 0.5rem 0; text-align: center; }
.qallm-doc table { border-collapse: collapse; margin: 1rem 0; width: 100%; font-size: 0.875rem; }
.qallm-doc th, .qallm-doc td { border: 1px solid #e2e8f0; padding: 0.4rem 0.7rem; text-align: left; }
.qallm-doc th { background: #f8fafc; font-weight: 600; }
.qallm-doc blockquote { border-left: 3px solid #cbd5e1; margin: 0.9rem 0; padding: 0.2rem 0 0.2rem 1rem; color: #64748b; }
.qallm-doc hr { border: none; border-top: 1px solid #e2e8f0; margin: 1.5rem 0; }
`;
