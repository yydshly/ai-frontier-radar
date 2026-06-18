export type ReportScene = {
  id: string;
  type: string;
  title: string;
  lines: string[];
  sourceLabel?: string | null;
  durationInFrames: number;
  index: number;
  /** Override kicker label (e.g. "CORE INSIGHT 01 · PART 2"). */
  kicker?: string;
  /** Share URL passed to the closing scene. */
  shareUrl?: string | null;
  /** Data URL of the QR code (PNG base64). */
  qrCodeDataUrl?: string | null;
  /** Optional metadata bag forwarded from the storyboard. */
  metadata?: Record<string, unknown>;
};

export type ReportVideoProps = {
  title: string;
  subtitle: string;
  dateLabel: string;
  shareUrl?: string | null;
  qrCodeDataUrl?: string | null;
  scenes: ReportScene[];
  style: {
    backgroundPreset: "tech_grid_dark";
    transitionStyle: "slide_fade";
    accentColor: string;
    highlightColor: string;
    motionIntensity: "medium";
  };
};

export const defaultProps: ReportVideoProps = {
  title: "AI 前沿雷达",
  subtitle: "每日核心报告",
  dateLabel: "2026-06-18",
  shareUrl: null,
  qrCodeDataUrl: null,
  scenes: [
    {
      id: "scene_01",
      type: "opening",
      title: "AI 前沿雷达 · 入口",
      lines: [
        "今日 AI 前沿雷达",
        "本期主题：每日核心报告",
        "本期包含 3 个核心观察"
      ],
      kicker: "AI FRONTIER RADAR",
      sourceLabel: "2026-06-18",
      durationInFrames: 180,
      index: 0
    },
    {
      id: "scene_02",
      type: "overview_paged",
      title: "今日整体判断",
      lines: [
        "今日 AI 研究呈现多维突破",
        "多语言推理与智能体安全齐头并进",
        "效率优化方面出现混合专家架构"
      ],
      kicker: "TODAY'S OVERVIEW",
      sourceLabel: "AI Frontier Radar",
      durationInFrames: 240,
      index: 1
    },
    {
      id: "scene_03",
      type: "core_insight",
      title: "AdaMame：两阶段训练方案",
      lines: [
        "AdaMame 提出两阶段训练方案",
        "在 12 种语言上实现准确率与语言一致性平衡",
        "达到帕累托最优"
      ],
      kicker: "CORE INSIGHT 01",
      sourceLabel: "AdaMame",
      durationInFrames: 240,
      index: 2
    },
    {
      id: "scene_04",
      type: "closing",
      title: "查看完整报告",
      lines: [
        "本期共播报 3 个核心观察",
        "扫码查看完整报告",
        "或访问分享页"
      ],
      kicker: "READ THE FULL REPORT",
      sourceLabel: "2026-06-18",
      shareUrl: null,
      qrCodeDataUrl: null,
      durationInFrames: 240,
      index: 3
    }
  ],
  style: {
    backgroundPreset: "tech_grid_dark",
    transitionStyle: "slide_fade",
    accentColor: "#3b82f6",
    highlightColor: "#f59e0b",
    motionIntensity: "medium"
  }
};