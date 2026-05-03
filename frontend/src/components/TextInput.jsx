import { useCallback, useMemo, useState } from "react";

const MIN_HAN = 5;
const MAX_HAN = 50;

/** 统计 CJK 统一汉字数量 */
export function countHanChars(str) {
  if (!str) return 0;
  const m = str.match(/[\u4e00-\u9fff]/g);
  return m ? m.length : 0;
}

/** 保留顺序，最多保留 maxHan 个汉字（超出汉字丢弃，非标点可保留——为防滥用总长度，仍对整串做合理上限） */
function truncateToMaxHan(str, maxHan) {
  let han = 0;
  let out = "";
  for (const ch of str) {
    const isHan = /[\u4e00-\u9fff]/.test(ch);
    if (isHan) {
      if (han >= maxHan) continue;
      han += 1;
    }
    out += ch;
  }
  return out;
}

const EXAMPLES = [
  { text: "妈麻马骂", hint: "四声练习" },
  { text: "青蛙王子", hint: "混合声调" },
  { text: "天气不错", hint: "日常用语" },
  { text: "我爱北京", hint: "常用短句" }
];

/**
 * @param {object} props
 * @param {string} props.value
 * @param {(text: string) => void} props.onChange
 * @param {boolean} [props.disabled]
 */
export default function TextInput({ value, onChange, disabled = false }) {
  const [truncateHint, setTruncateHint] = useState("");

  const hanCount = useMemo(() => countHanChars(value), [value]);

  const emitChange = useCallback(
    (nextRaw) => {
      const next = truncateToMaxHan(nextRaw, MAX_HAN);
      if (countHanChars(nextRaw) > MAX_HAN) {
        setTruncateHint(`已超过 ${MAX_HAN} 个汉字，已自动截断。`);
      } else {
        setTruncateHint("");
      }
      onChange(next);
    },
    [onChange]
  );

  const handleTextareaChange = (e) => {
    emitChange(e.target.value);
  };

  const handleChip = (text) => {
    if (disabled) return;
    setTruncateHint("");
    onChange(text);
  };

  const tooFew = hanCount > 0 && hanCount < MIN_HAN;
  const borderClass = tooFew
    ? "border-2 border-orange-400 focus:border-orange-500 focus:ring-orange-200"
    : "border border-slate-200 focus:border-blue-500 focus:ring-blue-500/30";

  return (
    <div className="rounded-2xl bg-white p-6 shadow ring-1 ring-slate-200/80">
      <label htmlFor="ref-textarea" className="mb-2 block text-sm font-medium text-slate-700">
        请输入要朗读的文字
      </label>
      <textarea
        id="ref-textarea"
        value={value}
        onChange={handleTextareaChange}
        disabled={disabled}
        rows={5}
        placeholder="在此输入 5～50 个汉字…"
        className={`w-full resize-y rounded-xl px-4 py-3 text-base text-slate-900 outline-none ring-2 ring-transparent transition placeholder:text-slate-400 focus:ring-2 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-500 ${borderClass}`}
      />

      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-sm">
        <span className={tooFew ? "font-medium text-orange-700" : "text-slate-600"}>
          已输入 <span className="tabular-nums font-semibold text-slate-800">{hanCount}</span> 个汉字
          <span className="text-slate-400"> / {MIN_HAN}～{MAX_HAN}</span>
        </span>
        {truncateHint ? (
          <span className="text-xs font-medium text-amber-700">{truncateHint}</span>
        ) : null}
      </div>

      {tooFew ? (
        <p className="mt-2 text-sm text-orange-700">
          至少需要 {MIN_HAN} 个汉字才能作为评测基准，请继续输入或点击下方示例。
        </p>
      ) : null}

      <div className="mt-4">
        <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">快速选择</p>
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map(({ text, hint }) => {
            const selected = value === text;
            return (
              <button
                key={text}
                type="button"
                disabled={disabled}
                onClick={() => handleChip(text)}
                className={`min-h-12 rounded-full border px-4 py-2 text-left text-sm transition focus:outline-none focus:ring-2 focus:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-50 ${
                  selected
                    ? "border-blue-500 bg-blue-50 text-blue-900 ring-2 ring-blue-400/60"
                    : "border-transparent bg-slate-100 text-slate-800 hover:bg-slate-200"
                }`}
              >
                <span className="font-medium">{text}</span>
                <span className={`ml-1.5 text-xs ${selected ? "text-blue-700/80" : "text-slate-500"}`}>
                  （{hint}）
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
