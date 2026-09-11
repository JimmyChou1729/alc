import React, { useEffect, useRef, useState } from "react";
import { Check, Download, Loader2, Play, Square } from "lucide-react";
import { ttsInstallLabel } from "./TtsLab";

type Language = "zh" | "en";
type Selection = { model_id: string; voice: string } | null;
type Model = {
  id: string;
  name: string;
  license: string;
  license_url?: string;
  source_url?: string;
  download_bytes: number;
  installed: boolean;
  install: { state: string; message: string };
  voices: { id: string; name: string; language: string }[];
  languages: string[];
};
type Status = { models: Model[]; selections: Record<Language, Selection> };
type SelectProps = {
  value: string | number;
  children: React.ReactNode;
  "aria-label": string;
  disabled?: boolean;
  onChange: (event: { target: { value: string } }) => void;
};
const samples = {
  zh: "欢迎使用朗读功能。愿每一次阅读，都带来新的发现。",
  en: "Welcome to your reading companion. Every page brings a new discovery.",
};
const keyFor = (selection: Selection) =>
  selection ? JSON.stringify([selection.model_id, selection.voice]) : "system";
function selectionFrom(key: string): Selection {
  if (key === "system") return null;
  const [model_id, voice] = JSON.parse(key);
  return { model_id, voice };
}
function modelProjectUrl(id: string) {
  if (id.startsWith("kokoro-")) return "https://github.com/hexgrad/kokoro";
  if (id.startsWith("vits-piper-"))
    return "https://github.com/OHF-Voice/piper1-gpl";
  if (id.startsWith("kitten-tts-"))
    return "https://github.com/KittenML/KittenTTS";
  return undefined;
}
function licenseLabel(value: string) {
  if (value.includes("Dataset license unknown"))
    return "训练数据许可未明确，请查看许可说明";
  if (value.includes("Blizzard 2013 Lessac"))
    return "适用 Blizzard 2013 Lessac 数据集条款";
  return value;
}
async function jsonRequest(method = "GET", data?: unknown, path = "") {
  const response = await fetch("/api/tts" + path, {
    method,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: data === undefined ? undefined : JSON.stringify(data),
  });
  const value = await response.json();
  if (!response.ok)
    throw new Error(value.error || value.detail || "请求未完成，请重试。");
  return value;
}

export function TtsSettings({
  Select,
}: {
  Select: React.ComponentType<SelectProps>;
}) {
  const [status, setStatus] = useState<Status | null>(null);
  const [selections, setSelections] = useState<Record<Language, Selection>>({
    zh: null,
    en: null,
  });
  const [installModel, setInstallModel] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [notice, setNotice] = useState("");
  const [audioUrls, setAudioUrls] = useState<Record<Language, string>>({
    zh: "",
    en: "",
  });
  const [previewErrors, setPreviewErrors] = useState<Record<Language, string>>({
    zh: "",
    en: "",
  });
  const [systemPlaying, setSystemPlaying] = useState<Language | null>(null);
  const initialized = useRef(false);
  const active = useRef(true);
  const previewRequest = useRef<AbortController | null>(null);
  const urls = useRef<Record<Language, string>>({ zh: "", en: "" });
  const players = useRef<Partial<Record<Language, HTMLAudioElement | null>>>(
    {},
  );
  const utterance = useRef<SpeechSynthesisUtterance | null>(null);
  const speechSupported =
    "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;

  function stopSystem() {
    if (utterance.current) {
      utterance.current = null;
      window.speechSynthesis.cancel();
    }
    setSystemPlaying(null);
  }
  function clearAudio(language: Language) {
    players.current[language]?.pause();
    if (urls.current[language]) URL.revokeObjectURL(urls.current[language]);
    urls.current[language] = "";
    setAudioUrls((old) => ({ ...old, [language]: "" }));
  }
  useEffect(() => {
    active.current = true;
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const current: Status = await jsonRequest();
        if (!active.current) return;
        setStatus(current);
        setLoadError("");
        if (!initialized.current) {
          setSelections(current.selections);
          setInstallModel(current.models[0]?.id || "");
          initialized.current = true;
        }
      } catch (err) {
        if (active.current) setLoadError((err as Error).message);
      } finally {
        if (active.current) timer = setTimeout(refresh, 2500);
      }
    }
    void refresh();
    return () => {
      active.current = false;
      clearTimeout(timer);
      previewRequest.current?.abort();
      Object.values(urls.current).forEach((url) => {
        if (url) URL.revokeObjectURL(url);
      });
      if (utterance.current) {
        utterance.current = null;
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  function available(language: Language, selection: Selection) {
    if (!selection) return true;
    return (
      status?.models.some(
        (model) =>
          model.installed &&
          model.id === selection.model_id &&
          model.voices.some(
            (voice) =>
              voice.id === selection.voice &&
              voice.language.startsWith(language),
          ),
      ) || false
    );
  }
  async function install() {
    if (!confirmed) return;
    setBusy("install");
    setError("");
    setNotice("");
    try {
      await jsonRequest(
        "POST",
        { confirmed: true, model_id: installModel },
        "/install",
      );
      const current: Status = await jsonRequest();
      if (active.current) {
        setStatus(current);
        setConfirmed(false);
      }
    } catch (err) {
      if (active.current) setError((err as Error).message);
    } finally {
      if (active.current) setBusy("");
    }
  }
  async function save() {
    setBusy("save");
    setError("");
    setNotice("");
    try {
      const current: Status = await jsonRequest("PATCH", { selections });
      if (active.current) {
        setStatus(current);
        setNotice("中英文默认朗读音色已保存。");
      }
    } catch (err) {
      if (active.current) setError((err as Error).message);
    } finally {
      if (active.current) setBusy("");
    }
  }
  async function preview(language: Language) {
    setPreviewErrors((old) => ({ ...old, [language]: "" }));
    const selection = selections[language];
    if (!selection) {
      if (!speechSupported) return;
      if (systemPlaying === language) {
        stopSystem();
        return;
      }
      stopSystem();
      Object.values(players.current).forEach((player) => player?.pause());
      const speech = new SpeechSynthesisUtterance(samples[language]);
      speech.lang = language === "zh" ? "zh-CN" : "en-US";
      speech.rate = 1;
      speech.onend = () => {
        if (active.current && utterance.current === speech) {
          utterance.current = null;
          setSystemPlaying(null);
        }
      };
      speech.onerror = () => {
        if (active.current && utterance.current === speech) {
          utterance.current = null;
          setSystemPlaying(null);
          setPreviewErrors((old) => ({
            ...old,
            [language]: "系统朗读不可用，请检查浏览器或系统语音设置。",
          }));
        }
      };
      utterance.current = speech;
      setSystemPlaying(language);
      window.speechSynthesis.speak(speech);
      return;
    }
    previewRequest.current?.abort();
    const controller = new AbortController();
    previewRequest.current = controller;
    setBusy(language);
    stopSystem();
    clearAudio(language);
    try {
      const response = await fetch("/api/tts/preview", {
        method: "POST",
        credentials: "same-origin",
        signal: controller.signal,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: samples[language],
          language: language === "zh" ? "zh-CN" : "en-US",
          ...selection,
          rate: 1,
        }),
      });
      if (!response.ok) {
        const value = await response.json();
        throw new Error(value.error || value.detail || "试听失败，请重试。");
      }
      const blob = await response.blob();
      if (!active.current || controller.signal.aborted) return;
      urls.current[language] = URL.createObjectURL(blob);
      setAudioUrls((old) => ({ ...old, [language]: urls.current[language] }));
    } catch (err) {
      if (active.current && !controller.signal.aborted)
        setPreviewErrors((old) => ({
          ...old,
          [language]: (err as Error).message,
        }));
    } finally {
      if (active.current && !controller.signal.aborted) setBusy("");
    }
  }

  const model = status?.models.find((item) => item.id === installModel);
  const installing = status?.models.some(
    (item) => item.install.state === "running",
  );
  return (
    <section className="card tts-card" aria-labelledby="tts-settings-title">
      <div className="section-title">
        <Play size={19} />
        <h2 id="tts-settings-title">TTS 朗读引擎</h2>
      </div>
      {!status && !loadError && <p role="status">正在读取朗读设置…</p>}
      {status && (
        <>
          <div className="tts-install-manager">
            <h3>添加自定义语音 TTS 模型</h3>
            <label>
              选择模型
              <Select
                aria-label="安装管理模型"
                value={installModel}
                disabled={!!busy}
                onChange={(e) => {
                  setInstallModel(e.target.value);
                  setConfirmed(false);
                  setError("");
                }}
              >
                {status.models.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                    {item.installed ? "（已安装）" : ""}
                  </option>
                ))}
              </Select>
            </label>
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
                    .filter((value, index, all) => all.indexOf(value) === index)
                    .join(" / ")}{" "}
                  · 模型约 {(model.download_bytes / 1024 / 1024).toFixed(0)}{" "}
                  MB（另需运行依赖） · {licenseLabel(model.license)}
                  {modelProjectUrl(model.id) && (
                    <>
                      {" · "}
                      <a
                        href={modelProjectUrl(model.id)}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        项目源码
                      </a>
                    </>
                  )}
                </p>
                {!model.installed &&
                  ["running", "failed"].includes(model.install.state) && (
                    <p role="status">{ttsInstallLabel(model)}</p>
                  )}
                {!model.installed && (
                  <div className="tts-install">
                    <label className="checkbox">
                      <input
                        type="checkbox"
                        checked={confirmed}
                        disabled={!!busy || installing}
                        onChange={(e) => setConfirmed(e.target.checked)}
                      />
                      <span>
                        我确认下载 {model.name} 及运行依赖，已了解上述许可说明。
                      </span>
                    </label>
                    <button
                      type="button"
                      className="button secondary"
                      disabled={!confirmed || !!busy || installing}
                      onClick={install}
                    >
                      {busy === "install" ||
                      model.install.state === "running" ? (
                        <Loader2 size={15} className="spin" />
                      ) : (
                        <Download size={15} />
                      )}
                      {model.install.state === "failed"
                        ? "重新安装"
                        : "下载并安装"}
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
          <div className="tts-language-settings">
            {(["en", "zh"] as const).map((language) => {
              const label = language === "zh" ? "中文" : "英文";
              const selection = selections[language];
              const ready = available(language, selection);
              return (
                <div className="tts-language-card" key={language}>
                  <label>
                    {label}默认声音
                    <Select
                      aria-label={`${label}默认声音`}
                      value={keyFor(selection)}
                      disabled={!!busy}
                      onChange={(e) => {
                        stopSystem();
                        clearAudio(language);
                        setSelections((old) => ({
                          ...old,
                          [language]: selectionFrom(e.target.value),
                        }));
                        setPreviewErrors((old) => ({ ...old, [language]: "" }));
                        setNotice("");
                      }}
                    >
                      {!ready && selection && (
                        <option value={keyFor(selection)}>
                          {selection.model_id} · {selection.voice}
                          （未安装或不可用）
                        </option>
                      )}
                      {status.models
                        .filter(
                          (item) =>
                            item.installed &&
                            item.voices.some((voice) =>
                              voice.language.startsWith(language),
                            ),
                        )
                        .map((item) => (
                          <optgroup label={item.name} key={item.id}>
                            {item.voices
                              .filter((voice) =>
                                voice.language.startsWith(language),
                              )
                              .map((voice) => (
                                <option
                                  key={voice.id}
                                  value={keyFor({
                                    model_id: item.id,
                                    voice: voice.id,
                                  })}
                                >
                                  {voice.name}
                                </option>
                              ))}
                          </optgroup>
                        ))}
                      <option value="system">系统自动</option>
                    </Select>
                  </label>
                  <button
                    type="button"
                    className="button secondary"
                    disabled={
                      !!busy || !ready || (!selection && !speechSupported)
                    }
                    onClick={() => preview(language)}
                  >
                    {systemPlaying === language ? (
                      <Square size={15} />
                    ) : (
                      <Play size={15} />
                    )}
                    {busy === language
                      ? "正在生成…"
                      : systemPlaying === language
                        ? `停止${label}试听`
                        : `试听${label}`}
                  </button>
                  <div className="tts-language-playback">
                    {audioUrls[language] && (
                      <audio
                        ref={(node) => {
                          players.current[language] = node;
                        }}
                        controls
                        autoPlay
                        src={audioUrls[language]}
                        aria-label={`${label}朗读试听`}
                        onPlay={(e) => {
                          stopSystem();
                          Object.values(players.current).forEach((player) => {
                            if (player !== e.currentTarget) player?.pause();
                          });
                        }}
                      />
                    )}
                    {!selection && (
                      <p className="field-note" role="status">
                        {!speechSupported
                          ? "当前浏览器不支持系统朗读。"
                          : systemPlaying === language
                            ? "正在使用系统声音试听…"
                            : "使用浏览器或系统的默认声音。"}
                      </p>
                    )}
                    {!ready && (
                      <p className="warning-line">
                        此声音暂不可用，请先安装对应模型或重新选择。
                      </p>
                    )}
                    {previewErrors[language] && (
                      <p className="warning-line" role="alert">
                        {previewErrors[language]}
                      </p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
          <div className="tts-settings-footer">
            <button
              type="button"
              className="button primary"
              disabled={
                !!busy ||
                !available("zh", selections.zh) ||
                !available("en", selections.en)
              }
              onClick={save}
            >
              {busy === "save" ? (
                <Loader2 size={15} className="spin" />
              ) : (
                <Check size={15} />
              )}
              {busy === "save" ? "正在保存…" : "保存朗读设置"}
            </button>
            {notice && (
              <p className="success-note" role="status">
                {notice}
              </p>
            )}
          </div>
        </>
      )}
      {(error || loadError) && (
        <p className="warning-line" role="alert">
          {error || loadError}
        </p>
      )}
    </section>
  );
}
