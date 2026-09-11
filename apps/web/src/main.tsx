import React, {
  useEffect,
  useLayoutEffect,
  useId,
  useRef,
  useState,
} from "react";
import { createRoot } from "react-dom/client";
import { createPortal } from "react-dom";
import {
  ArrowRight,
  Terminal,
  Cable,
  Pencil,
  Trash2,
  BookOpen,
  Check,
  ChevronDown,
  CircleAlert,
  Clock3,
  Download,
  FileText,
  File,
  FileCode2,
  Link2,
  FolderOpen,
  Globe2,
  Loader2,
  Pause,
  Play,
  Plus,
  Settings2,
  ShieldCheck,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import "./style.css";

type Provider = {
  base_url?: string;
  remember_key?: boolean;
  max_output_tokens?: number;
  vision?: boolean;
  price_currency?: string;
  input_price?: number | null;
  output_price?: number | null;
  cache_read_price?: number | null;
  cache_write_price?: number | null;
  id: string;
  name: string;
  protocol: string;
  model: string;
  default_model?: string;
  models?: Array<{
    id: string;
    name: string;
    description: string;
    reasoning_efforts: string[];
    default_reasoning_effort?: string | null;
    provider_default?: boolean;
  }>;
  model_catalog_status?: "available" | "configured" | "unavailable";
  model_catalog_message?: string | null;
  available?: boolean;
  compatible?: boolean;
  version?: string;
  key_available?: boolean | null;
  reasoning_efforts?: string[];
  configuration_warning?: string;
  credential_override_present?: boolean;
};
type Job = {
  external?: boolean;
  source_messages?: string[];
  translation_notice?: string | null;
  id: string;
  display_title: string;
  state: string;
  phase: string;
  created: number;
  spec: Record<string, any>;
  detail: Record<string, any>;
  error?: Record<string, any>;
  result?: Record<string, any>;
  metrics: Record<string, any>;
  recent_events?: Array<{
    label?: string;
    sequence: number;
    created: number;
    kind: string;
    data: Record<string, any>;
  }>;
};
type Settings = {
  providers: Provider[];
  ocr: null | {
    executable: string | null;
    api_url: string | null;
    token_env: string | null;
    language: "en" | "ch";
  };
  resources: {
    max_jobs: number;
    api_slots: number;
    cli_slots: number;
    translation_window_workers: number;
    companion_workers: number;
  };
  project: string;
};
type JobSummary = Pick<
  Job,
  "id" | "state" | "phase" | "created" | "spec" | "display_title" | "external"
>;
const taskSourceKind = (job: JobSummary) => {
  const source = String(job.spec.source_url || job.spec.title || "").trim();
  if (job.spec.source_url || /^(https?:\/\/|doi:|10\.\d{4,9}\/)/i.test(source))
    return "link";
  if (/\.pdf$/i.test(source)) return "pdf";
  if (/\.(html?|tex)$/i.test(source)) return "code";
  if (/\.(md|markdown|txt)$/i.test(source)) return "text";
  return "file";
};
function TaskSourceIcon({ job }: { job: JobSummary }) {
  const kind = taskSourceKind(job);
  const Icon =
    kind === "link"
      ? Link2
      : kind === "code"
        ? FileCode2
        : kind === "pdf" || kind === "text"
          ? FileText
          : File;
  const label =
    kind === "link"
      ? "链接来源"
      : kind === "pdf"
        ? "PDF 文档"
        : kind === "code"
          ? "HTML / TeX 文档"
          : kind === "text"
            ? "文本文件"
            : "文档";
  return <Icon size={17} aria-label={label} role="img" />;
}
const states: Record<string, string> = {
  queued: "排队中",
  running: "处理中",
  delivering: "交付中",
  completed: "已完成",
  paused: "已暂停",
  pausing: "正在暂停",
  cancelled: "已取消",
  cancelling: "正在取消",
  failed: "处理失败",
  needs_input: "需要处理",
  delivery_failed: "等待重新交付",
};
const phases: Record<string, string> = {
  queued: "等待调度",
  acquisition: "获取文档",
  parse: "解析结构",
  ocr: "PDF识别",
  ocr_proofread: "OCR校对",
  language: "识别语言",
  glossary: "整理术语",
  translation: "翻译与审查",
  companion: "编写 Companion",
  render: "生成 Reader",
  validate: "验证交付",
  completed: "已交付",
};
function taskPhaseLabel(job: { phase: string; detail?: Record<string, any> }) {
  if (job.phase === "companion") {
    const labels: Record<string, string> = {
      source_preparation: "准备原文",
      author_identity: "整理作者信息",
      language_detection: "识别语言",
      glossary: "整理术语",
      translation: "翻译与审查",
      guides: "编写伴读指南",
      chapter_join: "整合章节",
      publication: "生成阅读文档",
      completed: "准备交付",
    };
    return labels[job.detail?.progress?.phase] || "准备翻译与伴读";
  }
  return phases[job.phase] || job.phase;
}
const speeds = [
  {
    id: "draft",
    name: "快速初稿",
    workers: 4,
    reviews: 0,
    note: "4 个批次 · 不校对",
    icon: Sparkles,
  },
  {
    id: "standard",
    name: "标准",
    workers: 2,
    reviews: 1,
    note: "2 个批次 · 校对一轮",
    icon: ArrowRight,
  },
  {
    id: "thorough",
    name: "加强校对",
    workers: 2,
    reviews: 2,
    note: "2 个批次 · 最多两轮",
    icon: ShieldCheck,
  },
];
function processingLabel(spec: Record<string, any>) {
  if (spec.processing_workers != null && spec.review_rounds != null) {
    const preset =
      speeds.find(
        (s) =>
          s.workers === spec.processing_workers &&
          s.reviews === spec.review_rounds,
      )?.name || "自定义";
    const review = ["不校对", "校对一轮", "最多校对两轮"][spec.review_rounds];
    return `${preset} · 并发 ${spec.processing_workers} · ${review}`;
  }
  const preset =
    (
      { economy: "节省", standard: "标准", fast: "快速" } as Record<
        string,
        string
      >
    )[spec.speed] ||
    modes.find((m) => m.id === spec.mode)?.name ||
    "旧版设置";
  return `${preset} · 并发与校对按原任务配置`;
}
const modes = [
  {
    id: "fast",
    name: "快速",
    note: "伴读最多 2 轮",
    icon: ArrowRight,
  },
  {
    id: "standard",
    name: "标准",
    note: "伴读最多 3 轮",
    icon: BookOpen,
  },
  {
    id: "deep",
    name: "深度",
    note: "增加跨章节审查",
    icon: Sparkles,
  },
];

async function api<T = any>(
  path: string,
  method = "GET",
  data?: unknown,
): Promise<T> {
  const response = await fetch("/api" + path, {
    method,
    headers:
      data instanceof FormData ? {} : { "Content-Type": "application/json" },
    body:
      data === undefined
        ? undefined
        : data instanceof FormData
          ? data
          : JSON.stringify(data),
  });
  const value = await response.json();
  if (!response.ok)
    throw new Error(value.error || value.detail || "请求未完成，请稍后重试。");
  return value;
}
const count = (value: number | null | undefined) =>
  value == null
    ? "尚未报告"
    : new Intl.NumberFormat("zh-CN", {
        notation: value > 10000 ? "compact" : "standard",
        maximumFractionDigits: 1,
      }).format(value);
const range = (value?: number[]) =>
  value ? `${count(value[0])}–${count(value[1])}` : "正在估算";
const eta = (job: Job) => {
  const messages: Record<string, string> = {
    completed: "已完成",
    paused: "任务已暂停，继续后更新预计时间",
    pausing: "正在暂停任务",
    cancelled: "任务已取消",
    cancelling: "正在取消任务",
    failed: "任务已中断，重试后更新预计时间",
    needs_input: "等待处理，继续后更新预计时间",
    delivery_failed: "等待重新交付",
  };
  if (messages[job.state]) return messages[job.state];
  const seconds = job.metrics.progress.eta_seconds;
  if (!seconds)
    return job.state === "queued"
      ? "排队中，开始后更新预计时间"
      : "正在估算剩余时间";
  const low = Math.max(1, Math.ceil(seconds[0] / 60));
  const high = Math.max(low, Math.ceil(seconds[1] / 60));
  return `预计剩余 ${low === high ? low : `${low}–${high}`} 分钟`;
};
const duration = (seconds: number = 0) => {
  const n = Math.max(0, Math.floor(seconds));
  return n >= 3600
    ? `${Math.floor(n / 3600)} 小时 ${Math.floor((n % 3600) / 60)} 分钟`
    : `${Math.floor(n / 60)} 分 ${n % 60} 秒`;
};
const sourceNote =
  "no PDF validator was supplied; rich source structure remains authoritative";
const active = (job: Job) =>
  ["running", "queued", "pausing", "cancelling", "delivering"].includes(
    job.state,
  );

const currencies = [
  ["USD", "美元"],
  ["CNY", "人民币"],
  ["EUR", "欧元"],
  ["GBP", "英镑"],
  ["JPY", "日元"],
  ["HKD", "港币"],
];
function optionText(node: React.ReactNode): string {
  return React.Children.toArray(node)
    .map((child) =>
      React.isValidElement<{ children?: React.ReactNode }>(child)
        ? optionText(child.props.children)
        : String(child),
    )
    .join("");
}
function StyledSelect({
  value,
  children,
  onChange,
  "aria-label": label,
  compact = false,
}: {
  value: string | number;
  children: React.ReactNode;
  "aria-label": string;
  compact?: boolean;
  onChange: (event: { target: { value: string } }) => void;
}) {
  const items = React.Children.toArray(children)
    .filter(React.isValidElement)
    .map((node) => {
      const props = (
        node as React.ReactElement<{
          value?: string | number;
          children?: React.ReactNode;
        }>
      ).props;
      return [
        String(props.value ?? optionText(props.children)),
        optionText(props.children),
      ];
    });
  const id = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [index, setIndex] = useState(0);
  const [position, setPosition] = useState<React.CSSProperties>({
    left: 0,
    top: 0,
    width: 180,
    maxHeight: 280,
  });
  const selected = Math.max(
    0,
    items.findIndex(([code]) => code === String(value)),
  );
  function close(focus = false) {
    setOpen(false);
    if (focus) trigger.current?.focus();
  }
  function show() {
    if (!items.length) return;
    setIndex(selected);
    setOpen(true);
  }
  useLayoutEffect(() => {
    if (!open || !trigger.current) return;
    const r = trigger.current.getBoundingClientRect();
    const width = Math.min(
      Math.max(compact ? 200 : r.width, 180),
      document.documentElement.clientWidth - 16,
    );
    const below = window.innerHeight - r.bottom - 12;
    const above = r.top - 12;
    const flip = below < 276 && above > below;
    const height = Math.max(40, Math.min(276, flip ? above : below));
    setPosition({
      left: Math.max(
        8,
        Math.min(r.left, document.documentElement.clientWidth - width - 8),
      ),
      top: flip ? undefined : r.bottom + 6,
      bottom: flip ? window.innerHeight - r.top + 6 : undefined,
      width,
      maxHeight: height,
    });
  }, [open]);
  useEffect(() => {
    if (open)
      menu.current
        ?.querySelector<HTMLElement>(`[data-option="${index}"]`)
        ?.focus();
  }, [open, index]);
  useEffect(() => {
    if (!open) return;
    const outside = (e: PointerEvent) => {
      if (
        !menu.current?.contains(e.target as Node) &&
        !trigger.current?.contains(e.target as Node)
      )
        close();
    };
    const reposition = (e: Event) => {
      if (!menu.current?.contains(e.target as Node)) close();
    };
    document.addEventListener("pointerdown", outside);
    window.addEventListener("resize", reposition);
    window.addEventListener("scroll", reposition, true);
    return () => {
      document.removeEventListener("pointerdown", outside);
      window.removeEventListener("resize", reposition);
      window.removeEventListener("scroll", reposition, true);
    };
  }, [open]);
  return (
    <>
      <button
        type="button"
        ref={trigger}
        className={"currency-trigger" + (compact ? "" : " select-trigger-wide")}
        aria-label={`${label}：${items[selected]?.[1] || ""}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        onClick={() => (open ? close() : show())}
        onKeyDown={(e) => {
          if (["ArrowDown", "ArrowUp"].includes(e.key)) {
            e.preventDefault();
            show();
          }
        }}
      >
        <span>{items[selected]?.[1] || ""}</span>
        <ChevronDown size={15} />
      </button>
      {open &&
        createPortal(
          <div
            ref={menu}
            id={id}
            role="listbox"
            aria-label={label}
            className="currency-menu"
            style={position}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                e.preventDefault();
                e.stopPropagation();
                close(true);
              } else if (e.key === "Tab") {
                close(true);
              } else if (
                ["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)
              ) {
                e.preventDefault();
                setIndex(
                  e.key === "Home"
                    ? 0
                    : e.key === "End"
                      ? items.length - 1
                      : (index +
                          (e.key === "ArrowDown" ? 1 : -1) +
                          items.length) %
                        items.length,
                );
              } else if (e.key.length === 1 && /[a-z]/i.test(e.key)) {
                const n = items.findIndex(([code]) =>
                  code.startsWith(e.key.toUpperCase()),
                );
                if (n >= 0) {
                  e.preventDefault();
                  setIndex(n);
                }
              }
            }}
          >
            {items.map(([code, name], i) => (
              <button
                type="button"
                role="option"
                aria-selected={String(value) === code}
                tabIndex={-1}
                data-option={i}
                key={code}
                onClick={() => {
                  onChange({ target: { value: code } });
                  close(true);
                }}
              >
                <span>{name}</span>
                {String(value) === code && <Check size={16} />}
              </button>
            ))}
          </div>,
          document.body,
        )}
    </>
  );
}

function CurrencySelect({
  value,
  label,
  onChange,
}: {
  value: string;
  label: string;
  onChange: (value: string) => void;
}) {
  return (
    <StyledSelect
      compact
      value={value}
      aria-label={label}
      onChange={(e) => onChange(e.target.value)}
    >
      {currencies.map(([code, name]) => (
        <option key={code} value={code}>
          {code} {name}
        </option>
      ))}
    </StyledSelect>
  );
}

function TaskDialog({
  kind,
  initialTitle,
  onClose,
  onSubmit,
}: {
  kind: "rename" | "delete";
  initialTitle: string;
  onClose: () => void;
  onSubmit: (title: string) => Promise<void>;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [title, setTitle] = useState(initialTitle);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState("");
  useEffect(() => {
    ref.current?.showModal();
    const input = ref.current?.querySelector("input");
    input?.focus();
    input?.select();
  }, []);
  return (
    <dialog
      ref={ref}
      className="task-dialog"
      aria-labelledby="task-dialog-title"
      onCancel={(e) => {
        if (pending) e.preventDefault();
      }}
      onClose={onClose}
    >
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setPending(true);
          setMessage("");
          try {
            await onSubmit(title.trim());
            ref.current?.close();
          } catch (e) {
            setMessage((e as Error).message);
          } finally {
            setPending(false);
          }
        }}
      >
        <div className="dialog-heading">
          <h2 id="task-dialog-title">
            {kind === "rename" ? "修改任务名称" : "删除任务"}
          </h2>
          <button
            type="button"
            className="icon-button"
            aria-label="关闭弹窗"
            disabled={pending}
            onClick={() => ref.current?.close()}
          >
            <X size={18} />
          </button>
        </div>
        {kind === "rename" ? (
          <label>
            任务名称
            <input
              autoFocus
              required
              maxLength={500}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </label>
        ) : (
          <p>
            从最近任务中移除“{initialTitle}”？本地原文和已生成的文件会保留。
          </p>
        )}
        {message && (
          <p role="alert" className="warning-line">
            {message}
          </p>
        )}
        <div className="actions">
          <button
            type="button"
            className="button secondary"
            autoFocus={kind === "delete"}
            disabled={pending}
            onClick={() => ref.current?.close()}
          >
            取消
          </button>
          <button
            className="button primary"
            disabled={pending || (kind === "rename" && !title.trim())}
          >
            {pending
              ? "正在保存…"
              : kind === "rename"
                ? "保存名称"
                : "删除任务"}
          </button>
        </div>
      </form>
    </dialog>
  );
}

function App() {
  const [taskDialog, setTaskDialog] = useState<{
    kind: "rename" | "delete";
    id: string;
    title: string;
  } | null>(null);
  const [sidebarWidth, setSidebarWidth] = useState(() => {
    try {
      const n = Number(localStorage.getItem("alc-sidebar-width"));
      return n ? Math.min(420, Math.max(200, n)) : 238;
    } catch {
      return 238;
    }
  });
  const [draggingSidebar, setDraggingSidebar] = useState(false);
  function resizeSidebar(value: number) {
    const n = Math.min(420, Math.max(200, value));
    setSidebarWidth(n);
    try {
      localStorage.setItem("alc-sidebar-width", String(n));
    } catch {
      /* Optional preference. */
    }
  }
  const query = new URLSearchParams(location.search);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [view, setView] = useState(query.get("job") || "new");
  const [error, setError] = useState("");
  const [connected, setConnected] = useState(false);
  const [sessionReady, setSessionReady] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false);
  const loading = useRef(false);

  async function refresh() {
    if (loading.current) return;
    loading.current = true;
    try {
      setJobs(await api<JobSummary[]>("/jobs"));
      setConnected(true);
    } catch (e) {
      setConnected(false);
    } finally {
      loading.current = false;
    }
  }
  async function refreshSettings() {
    setSettings(await api<Settings>("/settings"));
  }
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setInterval> | undefined;
    (async () => {
      try {
        const token = new URLSearchParams(location.hash.slice(1)).get("token");
        if (token) {
          history.replaceState(null, "", location.pathname + location.search);
          const response = await fetch("/api/session", {
            method: "POST",
            headers: { Authorization: "Bearer " + token },
          });
          if (!response.ok)
            throw new Error("本地访问链接已失效，请重新运行 alc-web。");
        }
        if (alive) {
          setSessionReady(true);
          timer = setInterval(refresh, 2500);
          await refreshSettings();
          await refresh();
        }
      } catch (e) {
        if (alive) setError(String((e as Error).message));
      }
    })();
    return () => {
      alive = false;
      if (timer) clearInterval(timer);
    };
  }, []);
  useEffect(() => {
    if (!sessionReady) return;
    if (view === "new" || view === "settings") {
      setJob(null);
      return;
    }
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const load = async () => {
      try {
        const current = await api<Job>("/jobs/" + view);
        if (alive) setJob(current);
      } catch (e) {
        if (alive) setError((e as Error).message);
      }
    };
    load();
    const stream = view.startsWith("agent-")
      ? null
      : new EventSource("/api/jobs/" + view + "/events");
    stream?.addEventListener("update", () => {
      if (!timer)
        timer = setTimeout(() => {
          timer = undefined;
          load();
          refresh();
        }, 400);
    });
    const fallback = setInterval(load, 4000);
    return () => {
      alive = false;
      stream?.close();
      clearInterval(fallback);
      if (timer) clearTimeout(timer);
    };
  }, [view, sessionReady]);
  useEffect(() => {
    const pop = () =>
      setView(new URLSearchParams(location.search).get("job") || "new");
    addEventListener("popstate", pop);
    return () => removeEventListener("popstate", pop);
  }, []);
  function navigate(next: string) {
    setView(next);
    setError("");
    const params = new URLSearchParams(location.search);
    if (next === "new" || next === "settings") params.delete("job");
    else params.set("job", next);
    history.pushState(null, "", "/?" + params);
  }
  async function control(
    action: string,
    suppliedInput?: Record<string, unknown>,
  ) {
    if (!job) return;
    setBusy(true);
    setError("");
    try {
      setJob(
        await api("/jobs/" + job.id + "/control", "POST", {
          action,
          resume_input: suppliedInput || null,
        }),
      );
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const rawWarnings = (job?.result?.warnings ||
    job?.detail?.source_warnings ||
    []) as string[];
  const warnings =
    job?.source_messages ??
    [...new Set(rawWarnings)].filter((w) => w !== sourceNote);
  const quality = job?.metrics.quality;
  const hasWarnings =
    warnings.length > 0 ||
    quality?.source_fallback_count > 0 ||
    quality?.review_skipped_count > 0 ||
    quality?.translation_warning_count > 0;

  return (
    <div
      className={"shell" + (draggingSidebar ? " resizing-sidebar" : "")}
      style={{ "--sidebar-width": `${sidebarWidth}px` } as React.CSSProperties}
    >
      <aside className="sidebar">
        <a
          className="brand"
          href="/"
          onClick={(e) => {
            e.preventDefault();
            navigate("new");
          }}
        >
          <span className="brand-icon">
            <img
              src={new URL("./assets/alc-logo.png", import.meta.url).href}
              alt="ALC"
            />
          </span>
          <span>
            <small>伴读助手</small>
          </span>
        </a>
        <button className="new-button" onClick={() => navigate("new")}>
          <Plus size={18} />
          新建任务
        </button>
        <div className="nav-label">
          最近任务 <span>{jobs.length}</span>
        </div>
        <nav className="job-nav" aria-label="任务列表">
          {!jobs.length && (
            <div className="empty-nav">
              <FolderOpen size={25} />
              <p>还没有阅读任务</p>
              <span>添加文档后会显示在这里</span>
            </div>
          )}
          {jobs.map((item) => (
            <button
              key={item.id}
              className={"job-nav-item " + (view === item.id ? "selected" : "")}
              onClick={() => navigate(item.id)}
            >
              <TaskSourceIcon job={item} />
              <span>
                <strong>{item.display_title || item.spec.title}</strong>
                <small>
                  <i className={"dot " + item.state} />
                  {states[item.state]}
                  {item.external ? " · Agent 插件" : ""}
                </small>
              </span>
            </button>
          ))}
        </nav>
        <button
          className={"settings-link " + (view === "settings" ? "selected" : "")}
          onClick={() => navigate("settings")}
        >
          <Settings2 size={17} />
          模型与设置
        </button>
        <div className="local-note">
          <span className={"connection-dot " + (connected ? "" : "offline")} />
          {connected ? "本地服务已连接" : "正在连接本地服务"}
        </div>
        <div
          className="sidebar-resizer"
          role="separator"
          aria-label="调整任务侧栏宽度"
          aria-orientation="vertical"
          aria-valuemin={200}
          aria-valuemax={420}
          aria-valuenow={sidebarWidth}
          tabIndex={0}
          onPointerDown={(e) => {
            if (e.button !== 0) return;
            e.currentTarget.focus();
            e.currentTarget.setPointerCapture(e.pointerId);
            setDraggingSidebar(true);
            e.preventDefault();
          }}
          onPointerMove={(e) => {
            if (e.currentTarget.hasPointerCapture(e.pointerId))
              resizeSidebar(e.clientX);
          }}
          onPointerUp={(e) => {
            if (e.currentTarget.hasPointerCapture(e.pointerId))
              e.currentTarget.releasePointerCapture(e.pointerId);
            setDraggingSidebar(false);
          }}
          onLostPointerCapture={() => setDraggingSidebar(false)}
          onKeyDown={(e) => {
            if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
              e.preventDefault();
              resizeSidebar(sidebarWidth + (e.key === "ArrowRight" ? 10 : -10));
            }
          }}
        />
      </aside>
      <main>
        {error && (
          <div className="error-banner" role="alert">
            <CircleAlert size={19} />
            <span>{error}</span>
            <button aria-label="关闭提示" onClick={() => setError("")}>
              <X size={17} />
            </button>
          </div>
        )}
        {view === "new" && (
          <NewJob
            settings={settings}
            onError={setError}
            onOpenSettings={() => navigate("settings")}
            onCreated={async (result) => {
              await refresh();
              navigate(result.id);
            }}
          />
        )}
        {view === "settings" && (
          <SettingsPage
            settings={settings}
            onSaved={async () => {
              await refreshSettings();
              await refresh();
            }}
            onError={setError}
          />
        )}
        {job?.external && view === job.id && (
          <div className="page detail-page">
            <div className="eyebrow">来自 Agent 插件</div>
            <h1>{job.display_title}</h1>
            <div className="actions task-management">
              <button
                className="text-button"
                disabled={busy}
                onClick={() =>
                  setTaskDialog({
                    kind: "rename",
                    id: job.id,
                    title: job.display_title || job.spec.title,
                  })
                }
              >
                <Pencil size={15} /> 重命名
              </button>
              <button
                className="text-button"
                disabled={busy}
                onClick={() =>
                  setTaskDialog({
                    kind: "delete",
                    id: job.id,
                    title: job.display_title || job.spec.title,
                  })
                }
              >
                <Trash2 size={15} color="#c64d4d" /> 删除任务
              </button>
            </div>
            <section className="card">
              <p>任务状态：{states[job.state]}</p>
              {job.detail.progress && (
                <p>
                  当前阶段：{taskPhaseLabel(job)}
                  {job.detail.progress.total_units != null && (
                    <>
                      {" "}
                      · 已完成 {job.detail.progress.completed_units ?? 0} /{" "}
                      {job.detail.progress.total_units}
                    </>
                  )}
                </p>
              )}
              <p>
                项目位置：
                <code style={{ overflowWrap: "anywhere" }}>
                  {job.detail.project}
                </code>
              </p>
              <p>
                这里展示原项目的记录。继续处理、暂停或恢复，请在 Agent
                插件中操作。
              </p>
              {job.detail.artifact_available && (
                <p>
                  <a href={`/api/jobs/${job.id}/artifact`}>下载任务结果数据</a>
                </p>
              )}
              {job.result ? (
                <div className="actions">
                  <a
                    className="button primary"
                    href={`/api/jobs/${job.id}/reader`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <BookOpen size={17} />
                    打开 Reader
                  </a>
                  <a
                    className="button secondary"
                    href={`/api/jobs/${job.id}/reader?download=true`}
                  >
                    <Download size={16} />
                    下载 HTML
                  </a>
                </div>
              ) : (
                <p>尚无可打开的 Reader。任务数据仍保存在上面的项目目录中。</p>
              )}
            </section>
          </div>
        )}
        {job && !job.external && view === job.id && (
          <div className="page detail-page">
            <div className="eyebrow task-identity">
              {job.spec.output === "companion"
                ? "伴读任务"
                : job.spec.output === "source"
                  ? "原文任务"
                  : "翻译任务"}{" "}
              <span>#{job.id.slice(0, 8)}</span>
            </div>
            <div className="detail-heading">
              <div>
                <h1>{job.display_title || job.spec.title}</h1>
              </div>
            </div>
            <div className="detail-meta-row">
              <p>
                {job.spec.output === "source"
                  ? job.spec.ocr_proofread
                    ? "原文 Reader · OCR 校对"
                    : "原文 Reader · 不调用模型"
                  : job.spec.target_language}
                {job.spec.source_url &&
                /^https?:\/\//i.test(job.spec.source_url) ? (
                  <>
                    {" "}
                    <span>·</span>{" "}
                    <a
                      className="source-tag"
                      href={job.spec.source_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {job.spec.source_url}
                    </a>
                  </>
                ) : (
                  <>
                    {" "}
                    <span>·</span>{" "}
                    <span className="source-tag">{job.spec.title}</span>
                  </>
                )}
              </p>
              <div className="actions task-management">
                <button
                  className="text-button"
                  disabled={busy}
                  onClick={() =>
                    setTaskDialog({
                      kind: "rename",
                      id: job.id,
                      title: job.display_title || job.spec.title,
                    })
                  }
                >
                  <Pencil size={15} /> 重命名
                </button>
                <button
                  className="text-button"
                  disabled={
                    busy ||
                    [
                      "queued",
                      "running",
                      "delivering",
                      "pausing",
                      "cancelling",
                    ].includes(job.state)
                  }
                  onClick={() =>
                    setTaskDialog({
                      kind: "delete",
                      id: job.id,
                      title: job.display_title || job.spec.title,
                    })
                  }
                >
                  <Trash2 size={15} color="#c64d4d" /> 删除任务
                </button>
              </div>
            </div>
            <section className="card progress-card" aria-label="任务进度">
              <div className="progress-top">
                <div>
                  <div className="phase-label-row">
                    <span className="section-kicker">当前阶段</span>
                    <span
                      className={
                        "status-badge " + (hasWarnings ? "warning" : job.state)
                      }
                    >
                      {active(job) ? (
                        <Loader2 className="spin" size={15} />
                      ) : hasWarnings || job.error ? (
                        <CircleAlert size={15} />
                      ) : (
                        <Check size={15} />
                      )}{" "}
                      {states[job.state]}
                      {job.state === "completed" && hasWarnings
                        ? " · 有警告"
                        : ""}
                    </span>
                  </div>
                  <h2 aria-live="polite">{taskPhaseLabel(job)}</h2>
                </div>
                <span className="big-percent">
                  {job.metrics.progress.estimated ? "约 " : ""}
                  {job.metrics.progress.percent}
                  <small>%</small>
                </span>
              </div>
              <div
                className="progress-track"
                role="progressbar"
                aria-label="总体估计进度"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={job.metrics.progress.percent}
              >
                <span style={{ width: job.metrics.progress.percent + "%" }} />
              </div>
              <div className="progress-foot">
                <span>
                  {job.metrics.progress.total_units
                    ? "已完成的处理进度会持续保留"
                    : job.metrics.progress.label ||
                      "整体进度按阶段耗时估算，阶段完成后更新"}
                </span>
                <span>
                  <Clock3 size={14} />
                  {eta(job)}
                </span>
                <span title="累计实际处理时间，不计排队和暂停等待">
                  {job.state === "completed" ? "处理用时" : "已用时间"}：
                  {duration(job.metrics.progress.elapsed_seconds)}
                </span>
              </div>
              {(job.spec.output !== "source" || job.spec.ocr_proofread) && (
                <dl
                  className="progress-configuration"
                  aria-label="任务处理配置"
                >
                  {job.spec.output !== "source" && (
                    <div>
                      <dt>处理方式</dt>
                      <dd>{processingLabel(job.spec)}</dd>
                    </div>
                  )}
                  <div>
                    <dt>模型</dt>
                    <dd>
                      {job.spec.model || "默认模型"} ·{" "}
                      {job.spec.reasoning_effort || "effort 未记录"}
                    </dd>
                  </div>
                </dl>
              )}
              {job.translation_notice && (
                <p className="muted" role="status">
                  {job.translation_notice}
                </p>
              )}
              <div className="actions">
                {["queued", "running", "delivering"].includes(job.state) && (
                  <button
                    className="button secondary"
                    disabled={busy}
                    onClick={() => control("pause")}
                  >
                    <Pause size={16} />
                    暂停
                  </button>
                )}
                {job.error?.code === "pdf_text_confirmation" && (
                  <button
                    className="button primary"
                    disabled={busy}
                    onClick={() => control("resume", { pdf_text_only: true })}
                  >
                    按纯文本继续（不含原图）
                  </button>
                )}
                {["paused", "failed", "needs_input"].includes(job.state) &&
                  job.error?.code !== "pdf_text_confirmation" &&
                  !job.error?.resume?.input_required && (
                    <button
                      className="button primary"
                      disabled={busy}
                      onClick={() => control("resume")}
                    >
                      <Play size={16} />
                      恢复任务
                    </button>
                  )}
                {job.state === "delivery_failed" && (
                  <button
                    className="button primary"
                    disabled={busy}
                    onClick={() => control("retry_delivery")}
                  >
                    重试交付
                  </button>
                )}
                {!["completed", "cancelled", "cancelling"].includes(
                  job.state,
                ) && (
                  <button
                    className="button secondary cancel-task"
                    disabled={busy}
                    onClick={() => control("cancel")}
                  >
                    <X size={17} />
                    取消任务
                  </button>
                )}
                {job.result && (
                  <>
                    <a
                      className="button primary"
                      href={`/api/jobs/${job.id}/reader`}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      <BookOpen size={17} />
                      {job.result?.partial ? "打开已完成部分" : "打开 Reader"}
                    </a>
                    <a
                      className="button secondary"
                      href={`/api/jobs/${job.id}/reader?download=true`}
                    >
                      <Download size={16} />
                      下载 HTML
                    </a>
                  </>
                )}
              </div>
            </section>
            {job.detail?.auto_recovery?.retry_at &&
              ["needs_input", "failed"].includes(job.state) && (
                <section className="card">
                  <p>
                    模型服务暂时不可用，将于{" "}
                    {new Date(
                      job.detail.auto_recovery.retry_at * 1000,
                    ).toLocaleTimeString("zh-CN")}{" "}
                    自动重试（第 {job.detail.auto_recovery.attempts} / 3 次）。
                  </p>
                  <button
                    className="button secondary"
                    onClick={() => control("pause")}
                  >
                    暂停自动重试
                  </button>
                </section>
              )}
            {job.result?.partial && (
              <section className="card">
                <p>
                  部分结果已保存：{job.result.completed_chapters} /{" "}
                  {job.result.total_chapters} 个
                  {job.result.unit_label || "章节"}
                  完整完成。恢复任务会复用已完成内容。
                </p>
                <p>
                  尚未完整完成：
                  {(job.result.incomplete_chapters || []).join("、")}
                </p>
              </section>
            )}
            <div className="metric-grid">
              <div className="metric">
                <span>已报告输入 tokens</span>
                <strong>{count(job.metrics.usage.input_tokens)}</strong>
                <small>
                  {job.state === "completed" ? (
                    job.metrics.usage.unknown_calls ? (
                      "已结束，部分用量未报告"
                    ) : (
                      "已按报告用量汇总"
                    )
                  ) : (
                    <>预计总用量 {range(job.metrics.estimate?.input_tokens)}</>
                  )}
                  {job.metrics.estimate?.confidence === "exact"
                    ? " · 不调用模型"
                    : ""}
                </small>
              </div>
              <div className="metric">
                <span>已报告输出 tokens</span>
                <strong>{count(job.metrics.usage.output_tokens)}</strong>
                <small>
                  {job.state === "completed" ? (
                    job.metrics.usage.unknown_calls ? (
                      "已结束，部分用量未报告"
                    ) : (
                      "已按报告用量汇总"
                    )
                  ) : (
                    <>预计总用量 {range(job.metrics.estimate?.output_tokens)}</>
                  )}
                </small>
              </div>
              <div className="metric">
                <span>
                  {job.metrics.cost.reference_only
                    ? "API 等价参考费用"
                    : "API 用量估算金额"}
                </span>
                <strong>
                  {job.metrics.cost.amount == null
                    ? "—"
                    : job.metrics.cost.amount_range &&
                        job.metrics.cost.amount_range[0] !==
                          job.metrics.cost.amount_range[1]
                      ? `${job.metrics.cost.currency} ${Number(job.metrics.cost.amount_range[0]).toFixed(4)}–${Number(job.metrics.cost.amount_range[1]).toFixed(4)}`
                      : job.metrics.cost.currency +
                        " " +
                        Number(job.metrics.cost.amount).toFixed(4)}
                </strong>
                <small>
                  {job.metrics.cost.reference_only
                    ? (job.metrics.cost.amount == null
                        ? job.metrics.cost.source
                          ? "等待已报告用量。"
                          : "尚无此具体模型的官方参考价。"
                        : "按已报告用量和官方 API 价折算，仅供参考。") +
                      (job.spec.provider?.credential_override_present
                        ? "实际计费以 CLI 账号为准。"
                        : "订阅登录时使用订阅额度，不按此金额扣费。")
                    : job.metrics.cost.basis === "cli_managed"
                      ? "CLI 托管认证；不是 API 账单"
                      : job.metrics.cost.amount == null
                        ? "尚无可计算的用量与价格"
                        : "按配置价格计算" +
                          (job.metrics.cost.complete
                            ? "，不是账单实付"
                            : "，仅包含已知部分")}
                </small>
                {job.metrics.cost.reference_only && job.metrics.cost.source && (
                  <small>
                    <a
                      href={job.metrics.cost.source}
                      target="_blank"
                      rel="noreferrer"
                    >
                      价格参考来源 · {job.metrics.cost.verified_on}
                    </a>
                  </small>
                )}
              </div>
            </div>
            {job.error && (
              <section className="card attention">
                <div className="section-title">
                  <CircleAlert size={19} />
                  <h2>需要处理</h2>
                </div>
                <p>{job.error.user_message || job.error.message}</p>
                {job.error.resume?.input_required && (
                  <p>
                    此任务需要补充输入，当前页面暂不支持提交这种内容。任务记录和已完成进度已保留。
                  </p>
                )}
              </section>
            )}
            <section className="card">
              <div className="section-title">
                <ShieldCheck size={18} />
                <h2>质量与来源</h2>
              </div>
              <div className="quality-row">
                <span>
                  保留原文 <b>{quality.source_fallback_count ?? "—"}</b>
                </span>
                <span>
                  未完成审查 <b>{quality.review_skipped_count ?? "—"}</b>
                </span>
                <span>
                  译文待核对 <b>{quality.translation_warning_count ?? 0}</b>
                </span>
                <span>
                  来源提醒 <b>{warnings.length}</b>
                </span>
              </div>
              {job.detail?.ocr_review && (
                <OcrNotices key={job.id} jobId={job.id} />
              )}
              {(quality.translation_issues || []).map((issue: any) => (
                <div className="quality-issue" key={issue.block_id}>
                  <p>{issue.reason}</p>
                  <p className="muted">
                    第 {issue.ordinal} 段：{issue.excerpt}
                  </p>
                  <a
                    href={`/api/jobs/${job.id}/reader#block-${encodeURIComponent(issue.block_id)}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    查看对应段落
                  </a>
                </div>
              ))}
              {warnings.map((w, i) => (
                <p className="warning-line" key={i}>
                  <CircleAlert size={15} />
                  {w}
                </p>
              ))}
              {!hasWarnings && (
                <p className="muted">
                  {quality.available === false
                    ? "质量信息暂不可用，请重新验证交付。"
                    : job.state === "completed"
                      ? "交付已验证，未报告来源或翻译降级。"
                      : "目前没有报告降级。完整交付后，以最终质量状态为准。"}
                </p>
              )}
            </section>
            <p className="footer-note">
              暂停和取消会保留已完成的工作。正在执行的模型请求可能仍产生用量。
            </p>
          </div>
        )}
      </main>
      {taskDialog && (
        <TaskDialog
          kind={taskDialog.kind}
          initialTitle={taskDialog.title}
          onClose={() => setTaskDialog(null)}
          onSubmit={async (title) => {
            if (taskDialog.kind === "rename") {
              const updated = await api(`/jobs/${taskDialog.id}`, "PATCH", {
                title,
              });
              if (view === taskDialog.id) setJob(updated);
            } else {
              await api(`/jobs/${taskDialog.id}`, "DELETE");
              if (view === taskDialog.id) navigate("new");
            }
            await refresh();
          }}
        />
      )}
    </div>
  );
}

function OcrNotices({ jobId }: { jobId: string }) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!open) return;
    let alive = true;
    setData(null);
    setError("");
    api(`/jobs/${jobId}/ocr-notices`)
      .then((value) => {
        if (alive) setData(value);
      })
      .catch((e) => {
        if (alive) setError(e.message);
      });
    return () => {
      alive = false;
    };
  }, [jobId, open]);
  return (
    <details
      className="ocr-notices"
      onToggle={(e) => setOpen(e.currentTarget.open)}
    >
      <summary>查看校对提示</summary>
      {error && <p role="alert">提示暂时无法读取，请收起后重试。</p>}
      {open && !data && !error && <p role="status">正在读取校对记录…</p>}
      {data && (
        <>
          <p className="muted">
            {data.display_count > 0
              ? `有 ${data.display_count} 组模型无法可靠判定的内容，仅供参考，不影响继续处理。`
              : "没有需要展示的内容歧义。版面差异、检查状态和程序诊断不列为不确定内容；这不代表识别结果保证无误。"}
          </p>
          {data.items.map((item: any, index: number) => (
            <section key={index} className={`ocr-notice-item ${item.category}`}>
              <h3>
                {item.label} <small>第 {item.pages.join("、")} 页</small>
              </h3>
              {item.excerpt && <blockquote>{item.excerpt}</blockquote>}
              <p>{item.message}</p>
              {item.records.map((record: any, i: number) => (
                <p key={i}>
                  第 {record.page} 页：
                  {record.display_reason ||
                    "模型无法确定此处内容，请对照原 PDF 核对。"}
                </p>
              ))}
            </section>
          ))}
          {Boolean(data.unapplied_items?.length) && (
            <section>
              <h3>未能应用的修订（{data.unapplied_items.length} 项）</h3>
              <p className="muted">
                以下内容保留了原识别结果，可对照 PDF
                查看。它们是未完成的修改，不是模型无法判断的歧义。
              </p>
              {data.unapplied_items.map((item: any, index: number) => (
                <section className="ocr-notice-item" key={index}>
                  <h3>第 {item.page} 页</h3>
                  {item.excerpt && <blockquote>{item.excerpt}</blockquote>}
                  <p>
                    {item.display_reason ||
                      "此项修订未能应用，已保留原识别结果，请对照原 PDF 核对。"}
                  </p>
                </section>
              ))}
            </section>
          )}
        </>
      )}
    </details>
  );
}

function NewJob({
  settings,
  onCreated,
  onError,
  onOpenSettings,
}: {
  settings: Settings | null;
  onCreated: (job: Job) => void;
  onError: (error: string) => void;
  onOpenSettings: () => void;
}) {
  const query = new URLSearchParams(location.search);
  const [tab, setTab] = useState("url");
  const [source, setSource] = useState<{ id: string; name: string } | null>(
    query.get("source")
      ? { id: query.get("source")!, name: query.get("name") || "已上传文档" }
      : null,
  );
  const [url, setUrl] = useState(query.get("url") || "");
  const [language, setLanguage] = useState(query.get("language") || "zh-CN");
  const [output, setOutput] = useState("reader");
  const [processingWorkers, setProcessingWorkers] = useState(2);
  const [reviewRounds, setReviewRounds] = useState(1);
  const speed =
    speeds.find(
      (s) => s.workers === processingWorkers && s.reviews === reviewRounds,
    )?.id || "custom";
  const [provider, setProvider] = useState("codex");
  const [model, setModel] = useState("");
  const [effort, setEffort] = useState("");
  const [intent, setIntent] = useState("");
  const [pdfMode, setPdfMode] = useState<"mineru" | "text_only">("mineru");
  const [ocrRemoteConsent, setOcrRemoteConsent] = useState(false);
  const [ocrProofread, setOcrProofread] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [starting, setStarting] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const selected = settings?.providers.find((p) => p.id === provider);
  const models = selected?.models || [];
  const resolvedModel =
    model || selected?.default_model || selected?.model || "";
  const defaultModel = models.find(
    (item) => item.id === selected?.default_model,
  );
  const selectedModel = models.find((item) => item.id === resolvedModel);
  const efforts =
    selectedModel?.reasoning_efforts || selected?.reasoning_efforts || [];
  const knownUploadedPdf =
    tab === "file" && Boolean(source?.name.toLowerCase().endsWith(".pdf"));
  const knownNonPdf = tab === "file" && Boolean(source) && !knownUploadedPdf;
  const showPdfOptions =
    !knownNonPdf && (tab === "url" || !source || knownUploadedPdf);
  const remoteOcrUrl = settings?.ocr?.api_url?.trim() || "";
  const ocrConfigured = Boolean(
    settings?.ocr &&
    Boolean(settings.ocr.executable) !== Boolean(settings.ocr.api_url),
  );
  const pdfOptionsBlocked =
    showPdfOptions &&
    pdfMode === "mineru" &&
    ((knownUploadedPdf && !ocrConfigured) ||
      Boolean(remoteOcrUrl && !ocrRemoteConsent));
  const ocrVisionUnavailable = Boolean(
    selected && selected.protocol !== "cli" && !selected.vision,
  );
  const ocrProofreadBlocked =
    ocrProofread && (!resolvedModel.trim() || ocrVisionUnavailable);
  useEffect(() => {
    if (showPdfOptions && pdfMode === "mineru") return;
    setOcrProofread(false);
  }, [showPdfOptions, pdfMode]);
  async function upload(file?: File) {
    if (!file) return;
    setUploading(true);
    onError("");
    try {
      const data = new FormData();
      data.append("file", file);
      setSource(await api("/sources", "POST", data));
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setUploading(false);
    }
  }
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (pdfOptionsBlocked) {
      onError(
        !ocrConfigured
          ? "请先配置 MinerU，或选择“仅提取文字”。"
          : "请确认远端服务地址，并同意上传 PDF。",
      );
      return;
    }
    if (ocrProofreadBlocked) {
      onError(
        !resolvedModel.trim()
          ? "OCR 校对需要明确的视觉模型。请先在模型设置中选择或输入模型。"
          : "当前 API provider 未启用图像输入，不能用于 OCR 校对。",
      );
      return;
    }
    setStarting(true);
    onError("");
    try {
      const result = await api<Job>("/jobs", "POST", {
        source_id: tab === "file" ? source?.id : null,
        source_url: tab === "url" ? url : null,
        target_language: language,
        output,
        mode: "standard",
        processing_workers: processingWorkers,
        review_rounds: reviewRounds,
        provider_id: provider,
        model: ocrProofread ? resolvedModel : model,
        reasoning_effort: effort || null,
        user_intent: intent,
        pdf_mode: pdfMode,
        ocr_remote_consent: ocrRemoteConsent,
        ocr_service_url:
          pdfMode === "mineru" && remoteOcrUrl && ocrRemoteConsent
            ? remoteOcrUrl
            : null,
        ocr_proofread: ocrProofread,
        ocr_proofread_consent: ocrProofread,
        ocr_proofread_provider_id: ocrProofread ? provider : null,
        ocr_proofread_model: ocrProofread ? resolvedModel : null,
      });
      onCreated(result);
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setStarting(false);
    }
  }
  return (
    <div className="page new-page">
      <div className="eyebrow">Agentic Learning Copilot</div>
      <h1>从一份文档开始。</h1>
      <p className="page-intro">翻译、伴读，让知识触手可及。</p>
      <form onSubmit={submit}>
        <section className="card source-card">
          <div className="card-heading">
            <div className="section-title">
              <span className="step">01</span>
              <h2>添加材料</h2>
            </div>
            <div className="tabs" aria-label="输入方式">
              <button
                type="button"
                className={tab === "url" ? "chosen" : ""}
                onClick={() => setTab("url")}
              >
                <Globe2 size={14} />
                链接 / DOI
              </button>
              <button
                type="button"
                className={tab === "file" ? "chosen" : ""}
                onClick={() => setTab("file")}
              >
                <Upload size={14} />
                本地文件
              </button>
            </div>
          </div>
          {tab === "file" ? (
            <>
              <input
                ref={input}
                className="sr-only"
                type="file"
                accept=".pdf,.html,.htm,.md,.markdown,.tex"
                aria-label="上传文档"
                onChange={(e) => upload(e.target.files?.[0])}
              />
              <button
                type="button"
                className={"dropzone " + (source ? "has-file" : "")}
                disabled={uploading}
                onClick={() => input.current?.click()}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  upload(e.dataTransfer.files[0]);
                }}
              >
                <span className="upload-icon">
                  {uploading ? (
                    <Loader2 className="spin" size={26} />
                  ) : source ? (
                    <FileText size={27} />
                  ) : (
                    <Upload size={25} />
                  )}
                </span>
                <strong>
                  {uploading
                    ? "正在保存文档…"
                    : source
                      ? source.name
                      : "拖入文档，或点击选择文件"}
                </strong>
                <span>
                  {source
                    ? "文件已保存在本地 · 点击更换"
                    : "PDF、HTML、Markdown 或单文件 TeX"}
                </span>
              </button>
            </>
          ) : (
            <div className="url-input">
              <label htmlFor="source-url">HTTP 文档地址、DOI 或 arXiv ID</label>
              <input
                id="source-url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://… 或 10.…/…"
              />
            </div>
          )}
        </section>
        <section className="card">
          <div className="section-title">
            <span className="step">02</span>
            <h2>处理方式</h2>
          </div>
          <div className="form-grid">
            <label>
              交付内容
              <StyledSelect
                aria-label="交付内容"
                value={output}
                onChange={(e) => setOutput(e.target.value)}
              >
                <option value="companion">翻译+伴读</option>
                <option value="reader">翻译</option>
                <option value="source">原文</option>
              </StyledSelect>
            </label>
            {output !== "source" && (
              <label>
                目标语言
                <StyledSelect
                  aria-label="目标语言"
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                >
                  <option value="zh-CN">简体中文</option>
                  <option value="zh-TW">繁體中文</option>
                  <option value="en">English</option>
                  <option value="ja">日本語</option>
                  <option value="de">Deutsch</option>
                  <option value="fr">Français</option>
                  <option value="es">Español</option>
                </StyledSelect>
              </label>
            )}
          </div>
          {output !== "source" && (
            <>
              <div className="mode-label">
                处理速度{" "}
                <span aria-live="polite">
                  {speed === "custom"
                    ? "自定义"
                    : speeds.find((s) => s.id === speed)?.name}
                </span>
              </div>
              <div className="mode-grid">
                {speeds.map((m) => (
                  <button
                    type="button"
                    key={m.id}
                    className={"mode " + (speed === m.id ? "chosen" : "")}
                    aria-pressed={speed === m.id}
                    onClick={() => {
                      setProcessingWorkers(m.workers);
                      setReviewRounds(m.reviews);
                    }}
                  >
                    <div>
                      <m.icon size={20} />
                      <span>{m.name}</span>
                      {m.id === "standard" && <small>推荐</small>}
                      {speed === m.id && (
                        <Check className="mode-check" size={17} />
                      )}
                    </div>
                    <p>{m.note}</p>
                  </button>
                ))}
              </div>
              <div className="form-grid processing-options">
                <label>
                  处理并发
                  <StyledSelect
                    aria-label="处理并发"
                    value={processingWorkers}
                    onChange={(e) =>
                      setProcessingWorkers(Number(e.target.value))
                    }
                  >
                    {Array.from({ length: 8 }, (_, i) => (
                      <option key={i + 1} value={i + 1}>
                        同时处理 {i + 1} 个批次
                      </option>
                    ))}
                  </StyledSelect>
                </label>
                <label>
                  内容校对
                  <StyledSelect
                    aria-label="内容校对"
                    value={reviewRounds}
                    onChange={(e) => setReviewRounds(Number(e.target.value))}
                  >
                    <option value={0}>不校对</option>
                    <option value={1}>校对一轮</option>
                    <option value={2}>最多两轮</option>
                  </StyledSelect>
                </label>
              </div>
              <p className="muted">
                并发数为单个任务的上限。增加并发不一定更快，实际速度受电脑性能、网络状况和模型服务限制影响。内容校对针对译文，不包含对照原
                PDF 页面的 OCR 校对。
              </p>
            </>
          )}
          {showPdfOptions && (
            <div className="pdf-options">
              <div className="mode-label">
                PDF 处理 <span>仅当来源为PDF时此设置才生效</span>
              </div>
              <div className="mode-grid pdf-mode-grid">
                <button
                  type="button"
                  className={"mode " + (pdfMode === "mineru" ? "chosen" : "")}
                  aria-pressed={pdfMode === "mineru"}
                  onClick={() => setPdfMode("mineru")}
                >
                  <div>
                    <FileText size={20} />
                    <span>MinerU 识别</span>
                    {pdfMode === "mineru" && (
                      <Check className="mode-check" size={17} />
                    )}
                  </div>
                  <p>识别扫描件、公式与复杂版面</p>
                </button>
                <button
                  type="button"
                  className={
                    "mode " + (pdfMode === "text_only" ? "chosen" : "")
                  }
                  aria-pressed={pdfMode === "text_only"}
                  onClick={() => {
                    setPdfMode("text_only");
                    setOcrRemoteConsent(false);
                    setOcrProofread(false);
                  }}
                >
                  <div>
                    <FileText size={20} />
                    <span>仅提取文字</span>
                    {pdfMode === "text_only" && (
                      <Check className="mode-check" size={17} />
                    )}
                  </div>
                  <p>跳过 OCR，适合已有文字层的 PDF</p>
                </button>
              </div>
              {pdfMode === "mineru" && !ocrConfigured && (
                <p className="warning-line" role="status">
                  <CircleAlert size={15} />
                  <span>
                    {knownUploadedPdf
                      ? "尚未配置 MinerU。请"
                      : "尚未配置 MinerU；若此地址返回 PDF，任务会暂停并允许仅提取文字。也可"}
                    <button
                      type="button"
                      className="inline-link"
                      onClick={onOpenSettings}
                    >
                      前往模型与设置
                    </button>
                    {knownUploadedPdf ? "，或选择“仅提取文字”。" : "。"}{" "}
                    <a
                      href="/mineru-help.html"
                      target="_blank"
                      rel="noreferrer"
                    >
                      查看 MinerU 安装与配置说明
                    </a>
                  </span>
                </p>
              )}
              {pdfMode === "mineru" && remoteOcrUrl && (
                <div className="remote-consent">
                  <p>
                    <Globe2 size={15} />
                    PDF 将上传到 MinerU 服务：<strong>{remoteOcrUrl}</strong>
                  </p>
                  <label className="checkbox">
                    <input
                      type="checkbox"
                      checked={ocrRemoteConsent}
                      onChange={(e) => setOcrRemoteConsent(e.target.checked)}
                    />
                    <span>我同意将 PDF 上传到此服务进行识别</span>
                  </label>
                </div>
              )}
              {pdfMode === "mineru" && (
                <div className="ocr-proofread-option">
                  <label className="checkbox">
                    <input
                      type="checkbox"
                      checked={ocrProofread}
                      onChange={(event) => {
                        setOcrProofread(event.target.checked);
                      }}
                    />
                    <span>对照原PDF校对</span>
                  </label>
                  <p>
                    会把原 PDF
                    的每页图像和对应的识别内容发送给当前所选模型进行校对，尽可能准确还原原文内容，并保留识别后的结构。注意：模型需要支持视觉处理才能使用此选项，且该选项会增加处理时间和模型用量。模型校对完成后自动继续，无法确认的内容保留原识别结果及提示。
                  </p>
                  {ocrProofread && ocrProofreadBlocked && (
                    <p className="warning-line" role="alert">
                      <CircleAlert size={15} />
                      {!resolvedModel.trim()
                        ? "请在下方模型设置中选择或输入明确的视觉模型。"
                        : "当前 API provider 未启用图像输入，请选择支持视觉输入的服务。"}
                    </p>
                  )}
                </div>
              )}
            </div>
          )}
        </section>
        {(output !== "source" || ocrProofread) && (
          <section className="card">
            <div className="section-title">
              <span className="step">03</span>
              <h2>模型设置</h2>
            </div>
            <div className="form-grid model-settings-grid">
              <label>
                调用方式
                <StyledSelect
                  aria-label="调用方式"
                  value={provider}
                  onChange={(e) => {
                    setProvider(e.target.value);
                    setModel("");
                    setEffort("");
                  }}
                >
                  {(
                    settings?.providers || [
                      {
                        id: "codex",
                        name: "Codex CLI",
                        protocol: "cli",
                        model: "",
                      },
                    ]
                  ).map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                      {p.protocol === "cli" && !p.compatible
                        ? " · 尚未就绪"
                        : ""}
                    </option>
                  ))}
                </StyledSelect>
              </label>
              <label>
                模型（model）
                {models.length ? (
                  <StyledSelect
                    aria-label="模型（model）"
                    value={model}
                    onChange={(e) => {
                      setModel(e.target.value);
                      setEffort("");
                    }}
                  >
                    <option value="">
                      默认 ·{" "}
                      {defaultModel?.name ||
                        selected?.default_model ||
                        selected?.model}
                    </option>
                    {models
                      .filter((item) => item.id !== selected?.default_model)
                      .map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.name}
                        </option>
                      ))}
                  </StyledSelect>
                ) : (
                  <input
                    value={model}
                    onChange={(e) => {
                      setModel(e.target.value);
                      setEffort("");
                    }}
                    placeholder={
                      selected?.default_model ||
                      selected?.model ||
                      "输入 provider 支持的精确模型 ID"
                    }
                  />
                )}
              </label>
              <label>
                思考强度（effort）
                <StyledSelect
                  aria-label="思考强度（effort）"
                  value={effort}
                  onChange={(e) => setEffort(e.target.value)}
                >
                  <option value="">
                    默认
                    {selectedModel?.default_reasoning_effort
                      ? ` · ${selectedModel.default_reasoning_effort}`
                      : ""}
                  </option>
                  {efforts.map((v) => (
                    <option key={v} value={v}>
                      {v}
                    </option>
                  ))}
                </StyledSelect>
              </label>
            </div>
            {selected?.protocol === "cli" &&
              (selected.configuration_warning ||
                selected.credential_override_present) && (
                <p className="inline-note">
                  <ShieldCheck size={15} />
                  {selected.configuration_warning}
                  {selected.credential_override_present
                    ? "检测到 API 认证环境变量，可能使用 API 计费。"
                    : ""}
                </p>
              )}
            {output !== "source" && (
              <div className="task-options">
                <label>
                  任务要求（自定义Prompt，可选）
                  <textarea
                    rows={3}
                    value={intent}
                    onChange={(e) => setIntent(e.target.value)}
                    placeholder={
                      output === "companion"
                        ? "例如：假设我了解本科物理，重点解释观测方法和省略的推导。"
                        : "例如：保留领域惯用术语，行文正式简洁。"
                    }
                  />
                  <span className="field-note">
                    {output === "companion"
                      ? "自定义 Prompt 会用于术语、翻译、翻译审查和伴读内容。"
                      : "自定义 Prompt 会用于术语、翻译和翻译审查。"}
                  </span>
                </label>
              </div>
            )}
          </section>
        )}
        <div className="submit-row">
          <p>
            <ShieldCheck size={16} />
            <span>
              任务和产物保存在本地。启用模型后，所需文档内容会发送给选定服务。
            </span>
          </p>
          <button
            className="button primary large"
            disabled={
              starting ||
              uploading ||
              !settings ||
              (tab === "file" ? !source : !url.trim()) ||
              pdfOptionsBlocked ||
              ocrProofreadBlocked
            }
          >
            {starting ? (
              <Loader2 className="spin" size={18} />
            ) : (
              <Play size={16} />
            )}
            开始任务
          </button>
        </div>
      </form>
    </div>
  );
}

type OcrSettings = NonNullable<Settings["ocr"]>;
type OcrDoctorResult = {
  available: boolean;
  inference_verified: boolean;
  warnings?: string[];
};

function OcrSettingsCard({
  settings,
  onSaved,
}: {
  settings: Settings | null;
  onSaved: () => Promise<void>;
}) {
  const [mode, setMode] = useState<"local" | "remote">("local");
  const [executable, setExecutable] = useState("mineru");
  const [apiUrl, setApiUrl] = useState("");
  const [tokenEnv, setTokenEnv] = useState("");
  const [language, setLanguage] = useState<OcrSettings["language"]>("en");
  const [saving, setSaving] = useState(false);
  const [checking, setChecking] = useState(false);
  const [notice, setNotice] = useState("");
  const [formError, setFormError] = useState("");
  const [doctor, setDoctor] = useState<OcrDoctorResult | null>(null);

  useEffect(() => {
    if (!settings) return;
    const current = settings.ocr;
    setMode(current?.api_url ? "remote" : "local");
    setExecutable(current?.executable || "mineru");
    setApiUrl(current?.api_url || "");
    setTokenEnv(current?.token_env || "");
    setLanguage(current?.language || "en");
  }, [
    settings?.ocr?.executable,
    settings?.ocr?.api_url,
    settings?.ocr?.token_env,
    settings?.ocr?.language,
  ]);

  async function saveOcr(e: React.FormEvent) {
    e.preventDefault();
    setFormError("");
    setNotice("");
    setDoctor(null);
    const target = mode === "local" ? executable.trim() : apiUrl.trim();
    if (!target) {
      setFormError(
        mode === "local"
          ? "请填写 MinerU 命令或可执行文件路径。"
          : "请填写已有 MinerU 服务的 URL。",
      );
      return;
    }
    if (mode === "remote") {
      try {
        const parsed = new URL(target);
        if (!["http:", "https:"].includes(parsed.protocol)) throw new Error();
      } catch {
        setFormError("MinerU 服务 URL 无效，请填写完整的 http 或 https 地址。");
        return;
      }
    }
    setSaving(true);
    try {
      await api("/ocr", "POST", {
        executable: mode === "local" ? target : null,
        api_url: mode === "remote" ? target : null,
        token_env: mode === "remote" ? tokenEnv.trim() || null : null,
        language,
      });
      await onSaved();
      setNotice("PDF 识别配置已保存，新任务会使用此配置。");
    } catch (e) {
      setFormError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function checkOcr() {
    setChecking(true);
    setDoctor(null);
    setNotice("");
    setFormError("");
    try {
      setDoctor(await api<OcrDoctorResult>("/ocr/doctor", "POST"));
    } catch (e) {
      setFormError((e as Error).message);
    } finally {
      setChecking(false);
    }
  }

  return (
    <form onSubmit={saveOcr} className="card">
      <div className="section-title">
        <FileText size={19} />
        <h2>PDF 识别</h2>
        <span className={"tiny-badge " + (settings?.ocr ? "ready" : "")}>
          {settings?.ocr ? "已配置" : "尚未配置"}
        </span>
      </div>
      <div className="mode-label">MinerU 运行方式</div>
      <p className="muted">
        需自行安装或连接已有服务。
        <a href="/mineru-help.html" target="_blank" rel="noreferrer">
          查看 MinerU 安装与配置说明
        </a>
      </p>
      <div className="mode-grid pdf-mode-grid">
        <button
          type="button"
          className={"mode " + (mode === "local" ? "chosen" : "")}
          aria-pressed={mode === "local"}
          onClick={() => {
            setMode("local");
            setDoctor(null);
          }}
        >
          <div>
            <Terminal size={20} />
            <span>本机 MinerU</span>
            {mode === "local" && <Check className="mode-check" size={17} />}
          </div>
          <p>调用本机命令或指定的可执行文件</p>
        </button>
        <button
          type="button"
          className={"mode " + (mode === "remote" ? "chosen" : "")}
          aria-pressed={mode === "remote"}
          onClick={() => {
            setMode("remote");
            setDoctor(null);
          }}
        >
          <div>
            <Globe2 size={20} />
            <span>已有 MinerU 服务</span>
            {mode === "remote" && <Check className="mode-check" size={17} />}
          </div>
          <p>将 PDF 上传到指定服务完成识别</p>
        </button>
      </div>
      <div className="form-grid ocr-form-grid">
        {mode === "local" ? (
          <label>
            MinerU 命令或路径
            <input
              value={executable}
              onChange={(e) => setExecutable(e.target.value)}
              placeholder="mineru 或 /path/to/mineru"
              autoComplete="off"
            />
            <span className="field-note">
              可填写 PATH 中的命令名或可执行文件绝对路径。
            </span>
          </label>
        ) : (
          <label>
            MinerU 服务 URL
            <input
              type="url"
              value={apiUrl}
              onChange={(e) => setApiUrl(e.target.value)}
              placeholder="https://mineru.example.com"
              autoComplete="url"
            />
            <span className="field-note">创建任务时会再次显示此上传目标。</span>
          </label>
        )}
        <label>
          OCR 语言
          <StyledSelect
            aria-label="OCR 语言"
            value={language}
            onChange={(e) =>
              setLanguage(e.target.value as OcrSettings["language"])
            }
          >
            <option value="en">English</option>
            <option value="ch">中文</option>
          </StyledSelect>
          <span className="field-note">用于 PDF 文字识别，默认 English。</span>
        </label>
      </div>
      {mode === "remote" && (
        <label>
          Token 环境变量名（可选）
          <input
            value={tokenEnv}
            onChange={(e) => setTokenEnv(e.target.value)}
            placeholder="MINERU_TOKEN"
            pattern="[A-Za-z_][A-Za-z0-9_]*"
            spellCheck={false}
            autoComplete="off"
          />
          <span className="field-note">
            只填写变量名，不要在此输入 token 或 API key。
          </span>
        </label>
      )}
      {formError && (
        <p className="warning-line" role="alert">
          <CircleAlert size={15} />
          {formError}
        </p>
      )}
      {notice && (
        <p className="success-note" role="status">
          <Check size={16} />
          {notice}
        </p>
      )}
      {doctor && (
        <div
          className={doctor.available ? "ocr-doctor ready" : "ocr-doctor"}
          role="status"
        >
          {doctor.available ? <Check size={16} /> : <CircleAlert size={16} />}
          <div>
            <strong>
              {doctor.available
                ? doctor.inference_verified
                  ? "MinerU 可用，识别验证已完成"
                  : "MinerU 可连接，实际识别尚未验证"
                : "MinerU 当前不可用"}
            </strong>
            {Boolean(doctor.warnings?.length) && (
              <ul>
                {doctor.warnings!.map((warning, index) => (
                  <li key={index}>{warning}</li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
      <div className="actions ocr-actions">
        <button className="button primary" disabled={saving || checking}>
          {saving ? (
            <Loader2 className="spin" size={16} />
          ) : (
            <Check size={16} />
          )}
          保存 PDF 识别配置
        </button>
        <button
          type="button"
          className="button secondary"
          disabled={!settings?.ocr || saving || checking}
          onClick={checkOcr}
        >
          {checking ? (
            <Loader2 className="spin" size={16} />
          ) : (
            <ShieldCheck size={16} />
          )}
          {checking ? "正在检测…" : "检测已保存配置"}
        </button>
      </div>
    </form>
  );
}

function SettingsPage({
  settings,
  onSaved,
  onError,
}: {
  settings: Settings | null;
  onSaved: () => Promise<void>;
  onError: (value: string) => void;
}) {
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");
  const [saveError, setSaveError] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const editForm = useRef<HTMLFormElement>(null);
  function newProviderForm() {
    return {
      id: `api-${crypto.randomUUID()}`,
      name: "自定义 API",
      protocol: "chat-completions",
      base_url: "https://api.openai.com/v1",
      model: "",
      key: "",
      remember_key: false,
      reasoning_efforts: "",
      vision: false,
      price_currency: "USD",
      input_price: "",
      output_price: "",
      cache_read_price: "",
      cache_write_price: "",
      max_output_tokens: 8192,
    };
  }
  const [form, setForm] = useState(newProviderForm);
  function editProvider(p: Provider) {
    onError("");
    setSaveError("");
    setEditingId(p.id);
    setForm({
      id: p.id,
      name: p.name,
      protocol: p.protocol,
      base_url: p.base_url || "",
      model: p.model,
      key: "",
      remember_key: p.remember_key || false,
      reasoning_efforts: (p.reasoning_efforts || []).join(","),
      vision: p.vision || false,
      price_currency: p.price_currency || "USD",
      input_price: p.input_price == null ? "" : String(p.input_price),
      output_price: p.output_price == null ? "" : String(p.output_price),
      cache_read_price:
        p.cache_read_price == null ? "" : String(p.cache_read_price),
      cache_write_price:
        p.cache_write_price == null ? "" : String(p.cache_write_price),
      max_output_tokens: p.max_output_tokens || 8192,
    });
    setNotice(
      p.key_available || p.remember_key
        ? "正在编辑已有连接。更改协议或 Base URL 时，请重新填写密钥。"
        : "正在编辑已有连接。当前没有可用密钥，请重新填写 API key。",
    );
    editForm.current?.scrollIntoView({ behavior: "auto", block: "start" });
  }
  function endpointCorrection() {
    try {
      const url = new URL(form.base_url.trim());
      const path = url.pathname.replace(/\/+$/, "");
      const routes = [
        ["/chat/completions", "chat-completions"],
        ["/responses", "responses"],
        ["/messages", "anthropic"],
      ];
      const match = routes.find(([suffix]) => path.endsWith(suffix));
      if (!match) return null;
      url.pathname = path.slice(0, -match[0].length) || "/";
      return {
        base_url: url.toString().replace(/\/$/, ""),
        protocol: match[1],
      };
    } catch {
      return null;
    }
  }
  const correction = endpointCorrection();
  const patch = (key: string, value: any) =>
    setForm((f) => ({ ...f, [key]: value }));
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaveError("");
    setNotice("");
    if (correction) {
      setSaveError(
        "尚未保存：Base URL 填成了完整接口地址。请点击上方“按接口地址修正”，再保存；已输入的密钥会保留在表单中。",
      );
      return;
    }
    setSaving(true);
    onError("");
    setNotice("");
    try {
      const value: any = {
        ...form,
        key: form.key || null,
        reasoning_efforts: form.reasoning_efforts
          .split(",")
          .map((v) => v.trim())
          .filter(Boolean),
      };
      for (const key of [
        "input_price",
        "output_price",
        "cache_read_price",
        "cache_write_price",
      ])
        value[key] = value[key] === "" ? null : Number(value[key]);
      const saved = await api("/providers", "POST", value);
      setEditingId(form.id);
      patch("key", "");
      await onSaved();
      setNotice(
        saved.key_available
          ? "连接与密钥已保存。请新建任务使用当前配置；旧任务不会自动更换连接参数。"
          : "连接已保存，但当前没有可用密钥。请填写 API key 后再次保存。",
      );
    } catch (e) {
      setSaveError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  return (
    <div className="page">
      <div className="eyebrow">MODEL SETTINGS</div>
      <h1>选择自己的模型。</h1>
      <p className="page-intro">复用已有 CLI，或连接自己的 API provider。</p>
      <section className="card">
        <div className="section-title">
          <Settings2 size={19} />
          <h2>当前可用调用方式</h2>
        </div>
        <div className="provider-list">
          {settings?.providers.map((p) => (
            <div key={p.id}>
              <span className="provider-symbol">
                {p.protocol === "cli" ? (
                  <Terminal size={20} />
                ) : (
                  <Cable size={20} />
                )}
              </span>
              <span>
                {p.protocol === "cli" ? (
                  <strong>{p.name}</strong>
                ) : (
                  <button
                    type="button"
                    className="provider-edit"
                    onClick={() => editProvider(p)}
                    aria-label={`编辑 ${p.name}`}
                  >
                    <strong>{p.name}</strong>
                    <span>编辑</span>
                  </button>
                )}
                <small>
                  {p.version || p.model || "尚未检测到"} ·{" "}
                  {p.protocol === "cli" ? "认证由 CLI 管理" : "API 按用量计费"}
                </small>
              </span>
              <span
                className={
                  "tiny-badge " +
                  ((p.protocol === "cli" ? p.compatible : p.key_available)
                    ? "ready"
                    : "")
                }
              >
                {p.protocol === "cli"
                  ? p.compatible
                    ? "接口可用"
                    : "未就绪"
                  : p.key_available
                    ? "接口可用"
                    : p.key_available === null
                      ? "密钥待读取"
                      : "需要密钥"}
              </span>
            </div>
          ))}
        </div>
      </section>
      <form ref={editForm} onSubmit={save} className="card">
        <div className="section-title">
          <Plus size={19} />
          <h2>{editingId ? "编辑 API 连接" : "添加 API 连接"}</h2>
          {editingId && (
            <button
              type="button"
              onClick={() => {
                setEditingId(null);
                setForm(newProviderForm());
                setNotice("");
              }}
            >
              添加其他连接
            </button>
          )}
        </div>
        <div className="form-grid">
          <label>
            显示名称
            <input
              value={form.name}
              onChange={(e) => patch("name", e.target.value)}
              required
            />
          </label>
          <label>
            协议
            <StyledSelect
              aria-label="协议"
              value={form.protocol}
              onChange={(e) => patch("protocol", e.target.value)}
            >
              <option value="chat-completions">
                OpenAI 兼容（Chat Completions）
              </option>
              <option value="responses">OpenAI Responses</option>
              <option value="anthropic">Anthropic Messages</option>
            </StyledSelect>
          </label>
          <label>
            Base URL
            <input
              value={form.base_url}
              onChange={(e) => patch("base_url", e.target.value)}
              required
            />
          </label>
          <label>
            模型 ID
            <input
              value={form.model}
              onChange={(e) => patch("model", e.target.value)}
              required
              placeholder="provider 提供的精确模型名称"
            />
          </label>
        </div>
        {correction && (
          <div className="warning-line" role="status">
            <p>
              这个地址包含完整接口路径，不能直接作为 Base
              URL。修正会同时选择对应协议，不会清空已输入的密钥。
            </p>
            <button
              type="button"
              className="button secondary"
              onClick={() => {
                setForm((f) => ({ ...f, ...correction }));
                setSaveError("");
              }}
            >
              按接口地址修正
            </button>
          </div>
        )}
        <label>
          API key
          <input
            type="password"
            autoComplete="off"
            value={form.key}
            onChange={(e) => patch("key", e.target.value)}
            placeholder="留空保留已经配置的密钥"
          />
        </label>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={form.remember_key}
            onChange={(e) => patch("remember_key", e.target.checked)}
          />
          <span>保存在系统密钥库；不勾选则仅本次服务会话可用</span>
        </label>
        <section className="advanced">
          <h3>能力与价格（选填）</h3>
          <label>
            支持的 reasoning effort（逗号分隔）
            <input
              value={form.reasoning_efforts}
              onChange={(e) => patch("reasoning_efforts", e.target.value)}
              placeholder="low, medium, high"
            />
          </label>
          <div className="form-grid">
            {[
              ["input_price", "输入价格"],
              ["output_price", "输出价格"],
              ["cache_read_price", "缓存读取价格"],
              ["cache_write_price", "缓存写入价格"],
            ].map(([key, label]) => (
              <div key={key} className="price-field">
                <label htmlFor={`price-${key}`}>{label} / 百万 tokens</label>
                <span className="price-input">
                  <input
                    type="number"
                    min="0"
                    step="any"
                    id={`price-${key}`}
                    value={(form as any)[key]}
                    onChange={(e) => patch(key, e.target.value)}
                  />
                  <CurrencySelect
                    label={`${label}币种`}
                    value={form.price_currency}
                    onChange={(value) => patch("price_currency", value)}
                  />
                </span>
              </div>
            ))}
          </div>
        </section>
        {saveError && (
          <p className="warning-line" role="alert">
            {saveError}
          </p>
        )}
        {notice && (
          <p className="success-note" role="status">
            <Check size={16} />
            {notice}
          </p>
        )}
        <button className="button primary" disabled={saving}>
          {saving ? (
            <Loader2 className="spin" size={16} />
          ) : (
            <Check size={16} />
          )}
          {editingId ? "保存修改" : "保存配置"}
        </button>
      </form>
      <OcrSettingsCard settings={settings} onSaved={onSaved} />
      {settings && (
        <section className="card">
          <div className="section-title">
            <Settings2 size={19} />
            <h2>并发与资源</h2>
          </div>
          <div className="form-grid">
            {[["max_jobs", "同时运行的文档任务", 4]].map(
              ([key, label, max]) => (
                <label key={key}>
                  {label}
                  <StyledSelect
                    aria-label={String(label)}
                    value={(settings.resources as any)[key]}
                    onChange={async (e) => {
                      try {
                        await api("/resources", "POST", {
                          ...settings.resources,
                          [key]: Number(e.target.value),
                        });
                        await onSaved();
                      } catch (err) {
                        onError((err as Error).message);
                      }
                    }}
                  >
                    {Array.from({ length: Number(max) }, (_, i) => (
                      <option key={i + 1}>{i + 1}</option>
                    ))}
                  </StyledSelect>
                </label>
              ),
            )}
          </div>
          <p className="path-note">
            <FolderOpen size={15} />
            {settings.project}
          </p>
        </section>
      )}
      <section className="card">
        <h2>插件项目</h2>
        <HistoryImport onImported={onSaved} />
      </section>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<App />);

function HistoryImport({ onImported }: { onImported: () => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [path, setPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (open) ref.current?.showModal();
  }, [open]);
  return (
    <>
      <button
        className="settings-link"
        onClick={() => {
          setOpen(true);
          setMessage("");
        }}
      >
        导入插件项目
      </button>
      {open && (
        <dialog
          ref={ref}
          className="task-dialog"
          aria-labelledby="history-import-title"
          onCancel={(e) => {
            if (busy) e.preventDefault();
          }}
          onClose={() => setOpen(false)}
        >
          <h2 id="history-import-title">导入已有项目</h2>
          <p>
            填写以前 Agent
            使用的项目目录。只添加历史入口，不复制或重新处理文档。
          </p>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              setMessage("");
              try {
                await api("/history/projects", "POST", { path });
                await onImported();
                setOpen(false);
              } catch (error) {
                setMessage((error as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <label htmlFor="history-project-path">项目目录</label>
            <input
              id="history-project-path"
              autoFocus
              value={path}
              onChange={(e) => setPath(e.target.value)}
              required
              placeholder="/Users/你的用户名/ALC/项目"
            />
            {message && <p role="alert">{message}</p>}
            <div className="actions">
              <button
                type="button"
                disabled={busy}
                onClick={() => setOpen(false)}
              >
                取消
              </button>
              <button type="submit" disabled={busy || !path.trim()}>
                {busy ? "正在导入…" : "导入"}
              </button>
            </div>
          </form>
        </dialog>
      )}
    </>
  );
}
