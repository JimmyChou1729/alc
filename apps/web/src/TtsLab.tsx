import React, { useEffect, useRef, useState } from "react";
import { ArrowRight, Download, Loader2, Play } from "lucide-react";

type Voice = { id: string; name: string; language: string };
type Model = {
  id: string;
  name: string;
  license: string;
  license_url?: string;
  source_url?: string;
  download_bytes: number;
  installed: boolean;
  install: { state: string; message: string };
  voices: Voice[];
  languages: string[];
};
type Choice = { model: string; voice: string };
type Result = {
  url?: string;
  elapsed?: number;
  duration?: number;
  error?: string;
  model: string;
  voice: string;
  text: string;
};
type Language = "zh-CN" | "en-US";
type SelectProps = {
  value: string | number;
  children: React.ReactNode;
  "aria-label": string;
  disabled?: boolean;
  onChange: (event: { target: { value: string } }) => void;
};
const samples: Record<Language, string> = {
  "zh-CN":
    "清晨的阳光穿过窗户，落在翻开的书页上。读到这里，我们不妨停下来想一想：一个好的问题，为什么常常比答案更重要？今天是九月十一日，实验将持续三十分钟。",
  "en-US":
    "Morning sunlight falls across the open pages of a book. Let us pause for a moment: why is a good question often more valuable than an answer? Today is September eleventh, and the experiment will last thirty minutes.",
};

export function ttsInstallLabel(model: {
  installed: boolean;
  install: { state: string; message: string };
}) {
  if (model.install.state === "running") return "正在下载和安装，请稍候";
  if (model.installed) return "已安装，可以试听";
  if (model.install.state === "failed") {
    if (/cancel|interrupt/i.test(model.install.message))
      return "安装已中断，可重新安装";
    return "安装失败，请检查网络、磁盘空间和 Python 环境后重试";
  }
  return "未安装";
}

function safeExternalLink(value?: string) {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    return url.protocol === "https:" && !url.username && !url.password
      ? url.href
      : undefined;
  } catch {
    return undefined;
  }
}
function licenseLabel(value: string) {
  if (value === "Dataset license unknown (see MODEL_CARD)")
    return "训练数据许可未明确，请查看模型说明";
  if (value === "Blizzard 2013 Lessac dataset terms (see MODEL_CARD)")
    return "适用 Blizzard 2013 Lessac 数据集条款";
  return value;
}

function voicesFor(model: Model | undefined, language: Language) {
  return (
    model?.voices.filter((voice) =>
      voice.language.startsWith(language.slice(0, 2)),
    ) || []
  );
}
async function jsonRequest(path: string, body?: unknown) {
  const response = await fetch("/api/tts" + path, {
    method: body === undefined ? "GET" : "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const value = await response.json();
  if (!response.ok)
    throw new Error(value.error || value.detail || "请求失败，请重试。");
  return value;
}

export function TtsLab({
  Select,
  onBack,
}: {
  Select: React.ComponentType<SelectProps>;
  onBack: () => void;
}) {
  const [models, setModels] = useState<Model[]>([]);
  const [language, setLanguage] = useState<Language>("zh-CN");
  const [text, setText] = useState(samples["zh-CN"]);
  const [choices, setChoices] = useState<Choice[]>([
    { model: "", voice: "" },
    { model: "", voice: "" },
  ]);
  const [results, setResults] = useState<(Result | null)[]>([null, null]);
  const [confirmations, setConfirmations] = useState<Record<string, boolean>>(
    {},
  );
  const [installing, setInstalling] = useState("");
  const [error, setError] = useState("");
  const [installError, setInstallError] = useState("");
  const [generating, setGenerating] = useState<number | null>(null);
  const initial = useRef(false);
  const currentRequest = useRef<AbortController | null>(null);
  const audioUrls = useRef<string[]>([]);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const data: { models: Model[] } = await jsonRequest("/models");
        if (!active) return;
        setModels(data.models);
        setError("");
        if (!initial.current && data.models.length) {
          const chinese = data.models.filter(
            (model) => voicesFor(model, "zh-CN").length,
          );
          const defaults = chinese.length ? chinese : data.models;
          setChoices(
            [0, 1].map((i) => {
              const model = defaults[i] || defaults[0];
              return {
                model: model.id,
                voice: voicesFor(model, "zh-CN")[0]?.id || "",
              };
            }),
          );
          initial.current = true;
        }
      } catch (err) {
        if (active) setError((err as Error).message);
      } finally {
        if (active) timer = setTimeout(refresh, 2500);
      }
    }
    void refresh();
    return () => {
      active = false;
      clearTimeout(timer);
      currentRequest.current?.abort();
      audioUrls.current.forEach(URL.revokeObjectURL);
    };
  }, []);

  function chooseModel(index: number, id: string) {
    const model = models.find((item) => item.id === id);
    setChoices((old) =>
      old.map((choice, i) =>
        i === index
          ? { model: id, voice: voicesFor(model, language)[0]?.id || "" }
          : choice,
      ),
    );
  }
  function changeLanguage(next: Language) {
    setLanguage(next);
    setChoices((old) =>
      old.map((choice) => ({
        ...choice,
        voice:
          voicesFor(
            models.find((model) => model.id === choice.model),
            next,
          )[0]?.id || "",
      })),
    );
  }
  async function install(model: Model) {
    if (!confirmations[model.id]) return;
    setInstalling(model.id);
    setInstallError("");
    try {
      await jsonRequest("/install", { model_id: model.id, confirmed: true });
      setConfirmations((old) => ({ ...old, [model.id]: false }));
      const data: { models: Model[] } = await jsonRequest("/models");
      setModels(data.models);
    } catch (err) {
      setInstallError((err as Error).message);
    } finally {
      setInstalling("");
    }
  }

  async function generate() {
    if (!text.trim() || text.length > 2000 || generating !== null) return;
    const controller = new AbortController();
    currentRequest.current = controller;
    audioUrls.current.forEach(URL.revokeObjectURL);
    audioUrls.current = [];
    setResults([null, null]);
    for (const index of [0, 1]) {
      if (controller.signal.aborted) break;
      setGenerating(index);
      const choice = choices[index];
      const model = models.find((item) => item.id === choice.model)!;
      const result: Result = {
        model: model.name,
        voice:
          model.voices.find((voice) => voice.id === choice.voice)?.name ||
          choice.voice,
        text,
      };
      try {
        const response = await fetch("/api/tts/preview", {
          method: "POST",
          credentials: "same-origin",
          signal: controller.signal,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text,
            language,
            voice: choice.voice,
            model_id: choice.model,
            rate: 1,
          }),
        });
        if (!response.ok) {
          const value = await response.json();
          throw new Error(value.error || value.detail || "生成失败，请重试。");
        }
        const blob = await response.blob();
        if (controller.signal.aborted) break;
        result.url = URL.createObjectURL(blob);
        audioUrls.current.push(result.url);
        const timing = response.headers.get("X-TTS-Synthesis-Ms");
        if (timing !== null && Number.isFinite(Number(timing)))
          result.elapsed = Number(timing);
      } catch (err) {
        if (controller.signal.aborted) break;
        result.error = (err as Error).message;
      }
      setResults((old) => old.map((item, i) => (i === index ? result : item)));
    }
    if (!controller.signal.aborted) setGenerating(null);
  }

  const busy = generating !== null;
  const anyInstalling =
    !!installing || models.some((model) => model.install.state === "running");
  const ready = choices.every(
    (choice) =>
      models.find((model) => model.id === choice.model)?.installed &&
      !!choice.voice,
  );
  return (
    <div className="page tts-lab-page">
      <button
        type="button"
        className="text-button tts-lab-back"
        onClick={onBack}
      >
        返回模型与设置
      </button>
      <div className="eyebrow">本地语音实验室</div>
      <h1>朗读对比</h1>
      <p className="page-intro">
        让两个模型读同一段文字，听听发音、停顿和语气的差别。这里的选择仅用于试听。
      </p>
      <section className="card">
        <div className="section-title">
          <h2>试听文本</h2>
        </div>
        <div className="tts-lab-language">
          <div>
            <label>文本语言</label>
            <Select
              aria-label="对比文本语言"
              value={language}
              disabled={busy}
              onChange={(e) => changeLanguage(e.target.value as Language)}
            >
              <option value="zh-CN">中文</option>
              <option value="en-US">English</option>
            </Select>
          </div>
          <button
            type="button"
            className="button secondary"
            disabled={busy}
            onClick={() => setText(samples[language])}
          >
            使用{language === "zh-CN" ? "中文" : "英文"}样例
          </button>
        </div>
        <label htmlFor="tts-lab-text">同一段文字用于 A 和 B</label>
        <textarea
          id="tts-lab-text"
          value={text}
          maxLength={2000}
          rows={5}
          disabled={busy}
          onChange={(e) => setText(e.target.value)}
        />
        <p className="field-note">
          {text.length} / 2000 字符 · 两组均使用 1× 语速
        </p>
      </section>
      {error && (
        <p className="warning-line" role="alert">
          {error}
        </p>
      )}
      {!models.length && !error && <p role="status">正在读取可用模型…</p>}
      <div className="tts-lab-grid">
        {choices.map((choice, index) => {
          const model = models.find((item) => item.id === choice.model);
          const voices = voicesFor(model, language);
          const result = results[index];
          const letter = index === 0 ? "A" : "B";
          return (
            <section
              className="card tts-lab-model"
              key={letter}
              aria-labelledby={`tts-model-${letter}`}
            >
              <div className="section-title">
                <span className="tts-lab-letter">{letter}</span>
                <h2 id={`tts-model-${letter}`}>模型 {letter}</h2>
              </div>
              <label>模型</label>
              <Select
                aria-label={`模型 ${letter}`}
                value={choice.model}
                disabled={busy || !!installing}
                onChange={(e) => chooseModel(index, e.target.value)}
              >
                {models.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </Select>
              {model && (
                <>
                  <p className="field-note">
                    {model.languages
                      .map((language) =>
                        language.startsWith("zh")
                          ? "中文"
                          : language.startsWith("en")
                            ? "English"
                            : language,
                      )
                      .filter((v, i, all) => all.indexOf(v) === i)
                      .join(" / ")}{" "}
                    · 模型约 {(model.download_bytes / 1024 / 1024).toFixed(0)}{" "}
                    MB · {licenseLabel(model.license)}
                  </p>
                  <div className="tts-lab-links">
                    {safeExternalLink(model.license_url) && (
                      <a
                        href={safeExternalLink(model.license_url)}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        查看许可说明
                      </a>
                    )}
                    {safeExternalLink(model.source_url) && (
                      <a
                        href={safeExternalLink(model.source_url)}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        模型下载来源
                      </a>
                    )}
                  </div>
                  <p className="tts-lab-install-state" role="status">
                    {ttsInstallLabel(model)}
                  </p>
                  {!model.installed && (
                    <div className="tts-install">
                      <p className="field-note">
                        安装时另需下载运行依赖，安装完成后即可试听。
                      </p>
                      <label className="checkbox">
                        <input
                          type="checkbox"
                          disabled={busy || anyInstalling}
                          checked={!!confirmations[model.id]}
                          onChange={(e) =>
                            setConfirmations((old) => ({
                              ...old,
                              [model.id]: e.target.checked,
                            }))
                          }
                        />
                        <span>
                          我确认下载 {model.name} 及运行依赖，模型许可为{" "}
                          {licenseLabel(model.license)}。
                        </span>
                      </label>
                      <button
                        type="button"
                        className="button secondary"
                        disabled={
                          busy || anyInstalling || !confirmations[model.id]
                        }
                        onClick={() => install(model)}
                      >
                        <Download size={15} />
                        {model.install.state === "failed"
                          ? "重新安装"
                          : "确认下载并安装"}
                      </button>
                    </div>
                  )}
                  {voices.length ? (
                    <>
                      <label>音色</label>
                      <Select
                        aria-label={`音色 ${letter}`}
                        value={choice.voice}
                        disabled={busy}
                        onChange={(e) =>
                          setChoices((old) =>
                            old.map((item, i) =>
                              i === index
                                ? { ...item, voice: e.target.value }
                                : item,
                            ),
                          )
                        }
                      >
                        {voices.map((voice) => (
                          <option key={voice.id} value={voice.id}>
                            {voice.name}
                          </option>
                        ))}
                      </Select>
                    </>
                  ) : (
                    <p className="warning-line">
                      此模型没有当前语言的音色，请更换模型或文本语言。
                    </p>
                  )}
                </>
              )}
              <div className="tts-lab-result">
                <h3>试听结果 {letter}</h3>
                {generating === index && (
                  <p className="tts-lab-progress" role="status">
                    <Loader2 size={16} className="spin" />
                    正在生成 {letter}…
                  </p>
                )}
                {!result && generating !== index && (
                  <p className="field-note">
                    {busy && index === 1
                      ? "等待 A 生成结束…"
                      : "生成后可播放并查看本次计时。"}
                  </p>
                )}
                {result && (
                  <>
                    <p className="field-note">
                      {result.model} · {result.voice}
                    </p>
                    {result.error && (
                      <p className="warning-line" role="alert">
                        {result.error}
                      </p>
                    )}
                    {result.url && (
                      <>
                        <audio
                          controls
                          preload="metadata"
                          src={result.url}
                          aria-label={`播放结果 ${letter}`}
                          onPlay={(e) =>
                            document
                              .querySelectorAll<HTMLAudioElement>(
                                ".tts-lab-result audio",
                              )
                              .forEach((audio) => {
                                if (audio !== e.currentTarget) audio.pause();
                              })
                          }
                          onLoadedMetadata={(e) => {
                            const duration = e.currentTarget.duration;
                            if (Number.isFinite(duration))
                              setResults((old) =>
                                old.map((item, i) =>
                                  i === index && item && item.url === result.url
                                    ? { ...item, duration }
                                    : item,
                                ),
                              );
                          }}
                        />
                        <dl className="tts-lab-metrics">
                          <div>
                            <dt>本次生成耗时</dt>
                            <dd>
                              {result.elapsed === undefined
                                ? "未提供"
                                : `${(result.elapsed / 1000).toFixed(2)} 秒`}
                            </dd>
                          </div>
                          <div>
                            <dt>音频时长</dt>
                            <dd>
                              {result.duration === undefined
                                ? "正在读取…"
                                : `${result.duration.toFixed(1)} 秒`}
                            </dd>
                          </div>
                        </dl>
                      </>
                    )}
                    <details>
                      <summary>查看生成时的文本</summary>
                      <p className="tts-lab-snapshot">{result.text}</p>
                    </details>
                  </>
                )}
              </div>
            </section>
          );
        })}
      </div>
      {installError && (
        <p className="warning-line" role="alert">
          {installError}
        </p>
      )}
      <div className="card tts-lab-run">
        <button
          type="button"
          className="button primary"
          disabled={busy || anyInstalling || !ready || !text.trim()}
          onClick={generate}
        >
          {busy ? <Loader2 size={16} className="spin" /> : <Play size={16} />}
          {busy
            ? `正在生成 ${generating === 0 ? "A" : "B"}…`
            : "生成 A / B 对比"}
          <ArrowRight size={16} />
        </button>
        <p className="field-note">
          {!ready
            ? "先安装两组所选模型，并选择可用音色。"
            : "依次生成 A、B，完成后点击播放器试听。"}{" "}
          计时来自当前设备的本次请求，会受首次加载、模型预热与设备负载影响，不代表音质评分。
        </p>
      </div>
    </div>
  );
}
