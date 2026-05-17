"use client";

import { useState } from "react";

import Alert from "@/app/components/ui/alert";

export default function JobOutputDisclosure({
  endpoint,
  lineCount = 0,
  className = "",
}) {
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [output, setOutput] = useState("");

  async function onToggle(event) {
    if (!event.currentTarget.open || loaded || loading) {
      return;
    }

    setLoading(true);
    setError("");

    const response = await fetch(endpoint);
    const body = await response.json().catch(() => ({}));

    if (!response.ok) {
      setError(body.detail || "Unable to load output.");
      setLoading(false);
      return;
    }

    setOutput(body.job?.log_output || "");
    setLoaded(true);
    setLoading(false);
  }

  return (
    <details
      onToggle={onToggle}
      className={`group rounded-lg border border-white/10 bg-slate-950/70 ${className}`}
    >
      <summary className="cursor-pointer list-none px-4 py-3 text-sm font-medium text-slate-200 marker:hidden">
        <span className="inline-flex items-center gap-2">
          <span className="group-open:hidden">View output</span>
          <span className="hidden group-open:inline">Hide output</span>
          {lineCount ? <span className="text-xs text-slate-400">{lineCount} lines</span> : null}
        </span>
      </summary>
      <div className="border-t border-white/10">
        {loading ? (
          <p className="px-4 py-4 text-xs leading-5 text-slate-300">Loading output...</p>
        ) : error ? (
          <Alert tone="rose" className="m-4">{error}</Alert>
        ) : loaded && output ? (
          <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words px-4 py-4 text-xs leading-5 text-slate-200 sm:max-h-none sm:overflow-x-auto sm:whitespace-pre sm:break-normal">
            {output}
          </pre>
        ) : loaded ? (
          <p className="px-4 py-4 text-xs leading-5 text-slate-300">No output captured.</p>
        ) : (
          <p className="px-4 py-4 text-xs leading-5 text-slate-300">Open to load output.</p>
        )}
      </div>
    </details>
  );
}
