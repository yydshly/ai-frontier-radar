export type ReportScene = {
  id: string;
  type: string;
  title: string;
  lines: string[];
  sourceLabel?: string | null;
  durationInFrames: number;
  index: number;
};

export type ReportVideoProps = {
  title: string;
  subtitle: string;
  dateLabel: string;
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
  scenes: [
    {
      id: "scene_01",
      type: "opening_summary",
      title: "今日 AI 前沿简报",
      lines: ["研究突破", "产业落地", "安全与 Agent"],
      sourceLabel: "2026-06-18",
      durationInFrames: 150,
      index: 0
    },
    {
      id: "scene_02",
      type: "signal",
      title: "核心洞察",
      lines: ["结构化工具调用正在成为", "评估 Agent 的关键维度"],
      sourceLabel: "AI Frontier Radar",
      durationInFrames: 180,
      index: 1
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
