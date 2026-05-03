import { useCallback, useEffect, useState } from "react";
import Recorder from "./components/Recorder.jsx";
import ResultPanel from "./components/ResultPanel.jsx";
import TextInput from "./components/TextInput.jsx";

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").trim().replace(/\/$/, "");
const ANALYZE_URL = API_BASE ? `${API_BASE}/api/analyze` : "/api/analyze";
const REQUEST_TIMEOUT_MS = 35_000;

export default function App() {
  const [refText, setRefText] = useState("妈麻马骂");
  const [audioBlob, setAudioBlob] = useState(null);
  const [result, setResult] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [recorderKey, setRecorderKey] = useState(0);

  useEffect(() => {
    if (!error) return;
    const t = setTimeout(() => setError(null), 5000);
    return () => clearTimeout(t);
  }, [error]);

  const handleSubmit = useCallback(
    async (blob) => {
      const text = refText.trim();
      if (!text || text.length < 2) {
        setError("请先输入参考文本（至少 2 个字）。");
        return;
      }

      setError(null);
      setResult(null);
      setIsLoading(true);

      const controller = new AbortController();
      const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

      try {
        const fd = new FormData();
        fd.append("audio", blob, "recording.webm");
        fd.append("ref_text", text);
        // 勿手动设置 Content-Type：浏览器会为 multipart 自动带 boundary

        const res = await fetch(ANALYZE_URL, {
          method: "POST",
          body: fd,
          signal: controller.signal
        });

        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          const msg =
            typeof data.detail === "string"
              ? data.detail
              : JSON.stringify(data.detail || data);
          throw new Error(msg || res.statusText || "请求失败");
        }
        setResult(data);
      } catch (e) {
        if (e?.name === "AbortError") {
          setError("分析超时，请检查网络后重试");
        } else {
          setError(e?.message || String(e));
        }
      } finally {
        window.clearTimeout(timeoutId);
        setIsLoading(false);
      }
    },
    [refText]
  );

  const handleReset = useCallback(() => {
    setResult(null);
    setError(null);
    setAudioBlob(null);
    setRecorderKey((k) => k + 1);
  }, []);

  return (
    <div className="flex min-h-screen flex-col bg-gray-50 text-slate-900">
      <header className="border-b border-slate-200/80 bg-white px-4 py-4 shadow-sm">
        <div className="mx-auto flex max-w-[480px] items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-bold tracking-tight text-blue-600 sm:text-2xl">声调校准</h1>
            <p className="mt-1 text-sm text-slate-600">普通话四声练习助手</p>
          </div>
          <div className="group relative shrink-0 pt-1">
            <button
              type="button"
              className="flex h-9 w-9 items-center justify-center rounded-full border border-slate-200 bg-slate-50 text-slate-500 transition hover:border-blue-300 hover:bg-blue-50 hover:text-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
              aria-label="说明"
            >
              <svg className="h-5 w-5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z" />
              </svg>
            </button>
            <div
              className="pointer-events-none absolute right-0 top-full z-20 mt-2 w-max max-w-[220px] rounded-lg bg-slate-800 px-3 py-2 text-xs text-white opacity-0 shadow-lg transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100"
              role="tooltip"
            >
              支持普通话四声练习
            </div>
          </div>
        </div>
      </header>

      <main className="flex flex-1 flex-col items-center justify-center px-4 py-8">
        <div className="w-full max-w-[480px] space-y-6">
          <section>
            <div className="mb-3">
              <span className="text-xs font-semibold uppercase tracking-wide text-blue-600">Step 1</span>
              <h2 className="text-base font-semibold text-slate-800">参考文本</h2>
            </div>
            <TextInput value={refText} onChange={setRefText} disabled={isLoading} />
          </section>

          {error ? (
            <div
              className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 shadow-sm"
              role="alert"
            >
              {error}
            </div>
          ) : null}

          <section>
            <div className="mb-3">
              <span className="text-xs font-semibold uppercase tracking-wide text-blue-600">Step 2</span>
              <h2 className="text-base font-semibold text-slate-800">录音</h2>
            </div>
            <Recorder
              key={recorderKey}
              isLoading={isLoading}
              onAudioReady={(blob) => {
                setAudioBlob(blob);
                setError(null);
                setResult(null);
              }}
              onSubmit={handleSubmit}
            />
            {audioBlob ? (
              <p className="mt-2 text-center text-xs text-slate-400" aria-live="polite">
                已缓存本段录音（约 {Math.max(1, Math.round(audioBlob.size / 1024))} KB）
              </p>
            ) : null}
          </section>

          {result?.success ? <ResultPanel result={result} onReset={handleReset} /> : null}
        </div>
      </main>

      <footer className="border-t border-slate-200/80 bg-white py-4 text-center text-xs text-slate-500">
        由 AI 提供发音分析
      </footer>
    </div>
  );
}
