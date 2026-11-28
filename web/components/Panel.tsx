"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { PanelView } from "@/lib/types";

/** Draws a view the API builds whole: a title, a note, tables of rows and lists of items.
 *  It knows nothing about what the view shows; the path comes from /me's links. */
export function Panel({ path, onClose }: { path: string; onClose: () => void }) {
  const [view, setView] = useState<PanelView | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.panel(path).then(setView, (e) => setError((e as Error).message));
  }, [path]);

  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, [onClose]);

  return (
    <div role="dialog" aria-modal="true" className="fixed inset-0 z-50 overflow-y-auto bg-bg">
      <div className="page gap-3 pb-6">
        <div className="flex items-center justify-between gap-2">
          <h1 className="font-display text-xl font-medium">{view?.title ?? ""}</h1>
          <button onClick={onClose} className="border border-text px-2.5 py-1.5 text-sm leading-none hover:bg-card">
            Close
          </button>
        </div>
        {error && <p className="text-sm text-muted">{error}</p>}
        {!view && !error && <p className="text-sm text-muted">Loading…</p>}
        {view?.note && <p className="text-xs text-muted">{view.note}</p>}
        {view?.tables.map((t) => (
          <section key={t.title} className="box p-4">
            <h2 className="mb-2 font-display text-base font-medium">{t.title}</h2>
            <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-sm">
              {t.rows.map(([k, v]) => (
                <div key={k} className="contents">
                  <dt className="text-muted">{k}</dt>
                  <dd className="text-right tabular-nums">{v}</dd>
                </div>
              ))}
            </dl>
          </section>
        ))}
        {view?.lists.map((l) => (
          <section key={l.title} className="box">
            <h2 className="flex items-baseline justify-between border-b border-text px-4 py-3 font-display text-base font-medium">
              {l.title}
              {l.aside && <span className="text-sm font-normal text-muted">{l.aside}</span>}
            </h2>
            {l.items.length === 0 ? (
              <p className="px-4 py-3 text-sm text-muted">{l.empty}</p>
            ) : (
              <ol>
                {l.items.map((it, i) => (
                  <li key={i} className="border-t border-text px-4 py-3 text-sm first:border-t-0">
                    <div className="mb-1 flex flex-wrap items-center gap-1.5 text-xs text-muted">
                      {it.tags.map((t) => (
                        <span key={t.text} className={`chip ${t.on ? "bg-primary text-on-primary" : ""}`}>{t.text}</span>
                      ))}
                      {it.meta && <span>{it.meta}</span>}
                    </div>
                    <p className="whitespace-pre-wrap break-words">{it.text}</p>
                    {it.foot && <p className="mt-1 text-xs text-muted">{it.foot}</p>}
                  </li>
                ))}
              </ol>
            )}
          </section>
        ))}
      </div>
    </div>
  );
}
