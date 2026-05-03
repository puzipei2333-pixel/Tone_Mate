import { useEffect, useMemo, useState } from "react";

function scoreRingClass(score) {
  const n = Number(score);
  if (Number.isNaN(n)) return "text-slate-600 bg-slate-50 ring-slate-200";
  if (n >= 90) return "text-emerald-700 bg-emerald-50 ring-emerald-200";
  if (n >= 75) return "text-blue-700 bg-blue-50 ring-blue-200";
  if (n >= 60) return "text-orange-700 bg-orange-50 ring-orange-200";
  return "text-red-700 bg-red-50 ring-red-200";
}

function feedbackForChar(charFeedback, ch) {
  if (!Array.isArray(charFeedback)) return null;
  return charFeedback.find((f) => f && f.char === ch) || null;
}

function expectedToneHint(syllable, fb) {
  if (fb?.correct_tone) {
    const t = String(fb.correct_tone).trim();
    return `应读${t}`;
  }
  const n = syllable?.tone_num;
  const map = { 1: "第一声", 2: "第二声", 3: "第三声", 4: "第四声", 5: "轻声" };
  if (n && map[n]) return `应读${map[n]}`;
  return "请对照标准拼音练习";
}

export default function ResultPanel({ result, onReset }) {
  const [fadeIn, setFadeIn] = useState(false);
  const [expandedKey, setExpandedKey] = useState(null);

  useEffect(() => {
    setExpandedKey(null);
    setFadeIn(false);
    const id = requestAnimationFrame(() => {
      setFadeIn(true);
    });
    return () => cancelAnimationFrame(id);
  }, [result]);

  const score = Number(result?.overall_score ?? 0);
  const grade = result?.grade ?? "—";
  const summary = result?.feedback?.summary ?? "";
  const syllables = useMemo(
    () => (Array.isArray(result?.syllables) ? result.syllables : []),
    [result]
  );
  const charFeedback = result?.feedback?.char_feedback;
  const suggestions = useMemo(() => {
    const list = result?.feedback?.practice_suggestions;
    if (!Array.isArray(list)) return [];
    return list.filter(Boolean).slice(0, 2);
  }, [result]);

  const toggleExpand = (key, isWrong) => {
    if (!isWrong) return;
    setExpandedKey((k) => (k === key ? null : key));
  };

  if (!result) return null;

  return (
    <section
      className={`mx-auto w-full max-w-3xl space-y-8 transition-opacity duration-500 ease-out ${
        fadeIn ? "opacity-100" : "opacity-0"
      }`}
      aria-live="polite"
    >
      {/* 得分卡片 */}
      <div className="rounded-2xl bg-white p-6 shadow-lg ring-1 ring-slate-200/80">
        <div className="flex flex-col items-center gap-4 sm:flex-row sm:justify-center sm:gap-10">
          <div
            className={`flex h-36 w-36 shrink-0 flex-col items-center justify-center rounded-full text-4xl font-bold tabular-nums ring-4 ring-offset-2 ring-offset-white ${scoreRingClass(score)}`}
          >
            <span>{Number.isFinite(score) ? Math.round(score) : "—"}</span>
            <span className="mt-1 text-xs font-medium opacity-80">分</span>
          </div>
          <div className="max-w-md text-center sm:text-left">
            <p className="text-lg font-semibold text-slate-800">{grade}</p>
            {summary ? (
              <p className="mt-2 text-sm leading-relaxed text-slate-600">{summary}</p>
            ) : (
              <p className="mt-2 text-sm text-slate-400">暂无整体评语</p>
            )}
          </div>
        </div>
      </div>

      {/* 逐字声调 */}
      <div className="rounded-2xl bg-white p-6 shadow-lg ring-1 ring-slate-200/80">
        <h2 className="mb-4 text-center text-base font-semibold text-slate-800">逐字声调</h2>
        {syllables.length === 0 ? (
          <p className="py-8 text-center text-sm text-slate-500">未能识别声调，请重试</p>
        ) : (
          <div className="grid grid-cols-4 gap-3 sm:grid-cols-5 md:grid-cols-6">
            {syllables.map((s, idx) => {
              const ch = s?.char ?? "";
              const py = s?.pinyin ?? "";
              const ok = Boolean(s?.tone_correct);
              const fb = feedbackForChar(charFeedback, ch);
              const key = `${ch}-${idx}`;
              const expanded = expandedKey === key;
              const wrongHint = !ok ? expectedToneHint(s, fb) : "";

              const cardInner = (
                <>
                  <span className="text-[20px] font-semibold leading-none text-slate-900">{ch || "·"}</span>
                  <span className="mt-1 text-center text-xs leading-tight text-slate-600">{py || "—"}</span>
                  <div className="mt-2 flex items-center justify-center gap-1">
                    {ok ? (
                      <span className="text-lg text-green-600" aria-label="正确" title="正确">
                        ✓
                      </span>
                    ) : (
                      <span className="text-lg text-red-600" aria-label="错误" title="错误">
                        ✗
                      </span>
                    )}
                  </div>
                  {!ok && wrongHint ? (
                    <p className="mt-1 text-center text-[11px] font-medium leading-tight text-red-700">{wrongHint}</p>
                  ) : null}
                </>
              );

              return (
                <div key={key} className="flex min-w-0 flex-col">
                  {!ok ? (
                    <button
                      type="button"
                      onClick={() => toggleExpand(key, true)}
                      className={`w-full rounded-xl border-2 px-2 py-3 text-left transition hover:brightness-[0.98] focus:outline-none focus:ring-2 focus:ring-red-300 ${
                        expanded
                          ? "border-red-400 bg-red-50 ring-2 ring-red-200"
                          : "border-red-100 bg-red-50"
                      }`}
                    >
                      {cardInner}
                    </button>
                  ) : (
                    <div className="w-full rounded-xl border-2 border-green-100 bg-green-50 px-2 py-3">{cardInner}</div>
                  )}
                  {!ok && expanded ? (
                    <div className="mt-2 rounded-lg border border-red-100 bg-white px-2 py-2 text-xs leading-relaxed text-slate-700 shadow-sm">
                      {fb?.description ? <p className="mb-1">{fb.description}</p> : null}
                      {fb?.tip ? <p className="text-slate-600">💡 {fb.tip}</p> : null}
                      {!fb?.description && !fb?.tip ? (
                        <p className="text-slate-500">暂无该字的详细说明，可参考上方「{wrongHint}」。</p>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* AI 建议 */}
      <div className="relative rounded-2xl bg-white p-6 pb-16 shadow-lg ring-1 ring-slate-200/80">
        <h2 className="mb-3 text-base font-semibold text-slate-800">本次练习建议</h2>
        {suggestions.length > 0 ? (
          <ul className="space-y-2 text-sm leading-relaxed text-slate-700">
            {suggestions.map((line, i) => (
              <li key={i} className="flex gap-2">
                <span className="shrink-0" aria-hidden="true">
                  💡
                </span>
                <span>{line}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-slate-500">暂无练习建议</p>
        )}
        <button
          type="button"
          onClick={() => onReset?.()}
          className="absolute bottom-4 right-4 min-h-12 rounded-xl bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-md transition hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
        >
          再练一次
        </button>
      </div>
    </section>
  );
}
