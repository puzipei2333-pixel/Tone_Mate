import { useCallback, useEffect, useRef, useState } from "react";

const MAX_MS = 30_000;
const TICK_MS = 200;

function pickMimeType() {
  const candidates = ["audio/webm;codecs=opus", "audio/webm"];
  for (const t of candidates) {
    if (typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(t)) {
      return t;
    }
  }
  return "audio/webm";
}

function formatClock(ms) {
  const totalSec = Math.floor(ms / 1000);
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/**
 * @param {object} props
 * @param {(blob: Blob) => void} [props.onAudioReady]
 * @param {(blob: Blob) => void} [props.onSubmit]
 * @param {boolean} [props.isLoading]
 */
export default function Recorder({ onAudioReady, onSubmit, isLoading = false }) {
  const [internalPhase, setInternalPhase] = useState("idle");
  const [error, setError] = useState(null);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [playbackUrl, setPlaybackUrl] = useState(null);

  const mediaRecorderRef = useRef(null);
  const streamRef = useRef(null);
  const chunksRef = useRef([]);
  const timerRef = useRef(null);
  const audioBlobRef = useRef(null);
  const playbackUrlRef = useRef(null);

  const revokeUrl = useCallback((url) => {
    if (url) {
      try {
        URL.revokeObjectURL(url);
      } catch {
        /* ignore */
      }
    }
  }, []);

  const clearPlaybackUrl = useCallback(() => {
    revokeUrl(playbackUrlRef.current);
    playbackUrlRef.current = null;
    setPlaybackUrl(null);
  }, [revokeUrl]);

  const stopStream = useCallback(() => {
    const s = streamRef.current;
    if (s) {
      s.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
  }, []);

  const stopTimer = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const teardownRecorder = useCallback(() => {
    stopTimer();
    const mr = mediaRecorderRef.current;
    if (mr) {
      mr.ondataavailable = null;
      mr.onstop = null;
      if (mr.state !== "inactive") {
        try {
          mr.stop();
        } catch {
          /* ignore */
        }
      }
      mediaRecorderRef.current = null;
    }
    chunksRef.current = [];
    stopStream();
  }, [stopStream, stopTimer]);

  const finalizeRecording = useCallback(
    (mimeType) => {
      const type = mimeType || "audio/webm";
      const blob = new Blob(chunksRef.current, { type });
      chunksRef.current = [];
      audioBlobRef.current = blob;
      clearPlaybackUrl();
      const url = URL.createObjectURL(blob);
      playbackUrlRef.current = url;
      setPlaybackUrl(url);
      setInternalPhase("recorded");
      setElapsedMs(0);
      onAudioReady?.(blob);
    },
    [clearPlaybackUrl, onAudioReady]
  );

  const stopRecording = useCallback(() => {
    stopTimer();
    const mr = mediaRecorderRef.current;
    if (mr && mr.state === "recording") {
      try {
        mr.requestData?.();
      } catch {
        /* ignore */
      }
      mr.stop();
    } else {
      teardownRecorder();
      setInternalPhase("idle");
    }
  }, [stopTimer, teardownRecorder]);

  const startRecording = useCallback(async () => {
    setError(null);
    clearPlaybackUrl();
    audioBlobRef.current = null;
    chunksRef.current = [];
    setElapsedMs(0);

    if (!navigator.mediaDevices?.getUserMedia) {
      setError("当前浏览器不支持录音（缺少 getUserMedia）。");
      return;
    }

    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      const name = err?.name || "";
      if (name === "NotAllowedError" || name === "PermissionDeniedError") {
        setError("麦克风权限被拒绝。请在浏览器设置中允许本站使用麦克风后重试。");
      } else if (name === "NotFoundError") {
        setError("未检测到麦克风设备。");
      } else {
        setError(err?.message || "无法访问麦克风，请重试。");
      }
      return;
    }

    streamRef.current = stream;
    const mimeType = pickMimeType();
    let recorder;
    try {
      recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);
    } catch {
      recorder = new MediaRecorder(stream);
    }

    recorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) {
        chunksRef.current.push(e.data);
      }
    };
    recorder.onstop = () => {
      stopStream();
      const mime = recorder.mimeType || pickMimeType();
      finalizeRecording(mime);
    };

    mediaRecorderRef.current = recorder;
    setInternalPhase("recording");

    const startedAt = performance.now();
    timerRef.current = setInterval(() => {
      const now = performance.now();
      const elapsed = Math.min(now - startedAt, MAX_MS);
      setElapsedMs(elapsed);
      if (elapsed >= MAX_MS) {
        stopRecording();
      }
    }, TICK_MS);

    try {
      recorder.start(250);
    } catch (e) {
      recorder.ondataavailable = null;
      recorder.onstop = null;
      teardownRecorder();
      setInternalPhase("idle");
      setError(e?.message || "无法开始录音。");
    }
  }, [clearPlaybackUrl, finalizeRecording, stopRecording, teardownRecorder]);

  const resetToIdle = useCallback(() => {
    teardownRecorder();
    clearPlaybackUrl();
    audioBlobRef.current = null;
    chunksRef.current = [];
    setElapsedMs(0);
    setInternalPhase("idle");
    setError(null);
  }, [clearPlaybackUrl, teardownRecorder]);

  const handleSubmit = useCallback(() => {
    const blob = audioBlobRef.current;
    if (!blob || isLoading) return;
    onSubmit?.(blob);
  }, [isLoading, onSubmit]);

  useEffect(() => {
    return () => {
      stopTimer();
      const mr = mediaRecorderRef.current;
      if (mr) {
        mr.ondataavailable = null;
        mr.onstop = null;
        if (mr.state !== "inactive") {
          try {
            mr.stop();
          } catch {
            /* ignore */
          }
        }
        mediaRecorderRef.current = null;
      }
      chunksRef.current = [];
      stopStream();
      revokeUrl(playbackUrlRef.current);
      playbackUrlRef.current = null;
    };
  }, [revokeUrl, stopStream, stopTimer]);

  const showLoading = isLoading;
  const remainingMs = Math.max(0, MAX_MS - elapsedMs);

  return (
    <div className="relative mx-auto w-full max-w-md rounded-2xl bg-white p-6 shadow-lg ring-1 ring-slate-200/80">
      {showLoading && (
        <div
          className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 rounded-2xl bg-white/90 backdrop-blur-sm"
          aria-live="polite"
        >
          <div
            className="h-10 w-10 animate-spin rounded-full border-2 border-blue-600 border-t-transparent"
            role="status"
            aria-label="加载中"
          />
          <p className="text-sm font-medium text-slate-700">分析中...</p>
        </div>
      )}

      <div className={showLoading ? "pointer-events-none select-none opacity-60" : ""}>
        <h2 className="mb-4 text-center text-lg font-semibold text-slate-800">朗读录音</h2>

        {error && (
          <p className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 ring-1 ring-red-100">
            {error}
          </p>
        )}

        {internalPhase === "idle" && (
          <div className="flex flex-col items-center gap-6">
            <div className="flex h-20 w-20 items-center justify-center rounded-full bg-slate-100 text-slate-500">
              <svg className="h-10 w-10" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.91-3c-.49 0-.9.36-.98.85C16.52 14.2 14.47 16 12 16s-4.52-1.8-4.93-4.15c-.08-.49-.49-.85-.98-.85-.61 0-1.09.54-1 1.14.49 3 2.89 5.35 5.91 5.78V20c0 .55.45 1 1 1s1-.45 1-1v-2.08c3.02-.43 5.42-2.78 5.91-5.78.1-.6-.39-1.14-1-1.14z" />
              </svg>
            </div>
            <button
              type="button"
              onClick={startRecording}
              disabled={showLoading}
              className="min-h-12 w-full rounded-xl bg-blue-600 px-4 py-3 text-base font-semibold text-white shadow-md transition hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
            >
              点击开始录音
            </button>
          </div>
        )}

        {internalPhase === "recording" && (
          <div className="flex flex-col items-center gap-6">
            <div className="relative flex h-24 w-24 items-center justify-center">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-400/40" />
              <span className="absolute inline-flex h-[85%] w-[85%] rounded-full bg-red-500/25" />
              <div className="relative flex h-16 w-16 items-center justify-center rounded-full bg-red-500 text-white shadow-lg">
                <svg className="h-8 w-8" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                  <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z" />
                </svg>
              </div>
            </div>
            <div className="w-full text-center">
              <p className="font-mono text-2xl font-bold tabular-nums text-slate-800">
                {formatClock(elapsedMs)}
                <span className="text-base font-normal text-slate-500"> / {formatClock(MAX_MS)}</span>
              </p>
              <p className="mt-1 text-sm text-slate-500">剩余 {formatClock(remainingMs)}</p>
            </div>
            <button
              type="button"
              onClick={stopRecording}
              disabled={showLoading}
              className="min-h-12 w-full rounded-xl bg-red-600 px-4 py-3 text-base font-semibold text-white shadow-md transition hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
            >
              停止
            </button>
          </div>
        )}

        {internalPhase === "recorded" && playbackUrl && (
          <div className="flex flex-col gap-5">
            <audio
              className="w-full min-h-12"
              controls
              src={playbackUrl}
              preload="metadata"
            >
              您的浏览器不支持音频回放。
            </audio>
            <div className="flex flex-col gap-3 sm:flex-row">
              <button
                type="button"
                onClick={resetToIdle}
                disabled={showLoading}
                className="min-h-12 flex-1 rounded-xl border-2 border-slate-200 bg-white px-4 py-3 text-base font-semibold text-slate-700 transition hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-slate-400 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
              >
                重新录音
              </button>
              <button
                type="button"
                onClick={handleSubmit}
                disabled={showLoading}
                className="min-h-12 flex-1 rounded-xl bg-blue-600 px-4 py-3 text-base font-semibold text-white shadow-md transition hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
              >
                提交分析
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
