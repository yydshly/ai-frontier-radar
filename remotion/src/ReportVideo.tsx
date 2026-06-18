import React from "react";
import {
  AbsoluteFill,
  interpolate,
  Sequence,
  spring,
  useCurrentFrame,
  useVideoConfig
} from "remotion";
import {ReportScene, ReportVideoProps} from "./types";

const FONT =
  '"Microsoft YaHei","PingFang SC","Noto Sans CJK SC",system-ui,sans-serif';

const clamp = {
  extrapolateLeft: "clamp" as const,
  extrapolateRight: "clamp" as const
};

// Per-scene-type font sizes for body lines (prevent overflow).
// We size DOWN automatically when the content is too long.
const SCENE_FONT_SIZE: Record<string, number> = {
  opening: 38,
  overview_paged: 32,
  core_insight: 30,
  core_insight_continuation: 30,
  supporting_notes: 28,
  closing: 30
};

const SCENE_TITLE_SIZE: Record<string, number> = {
  opening: 64,
  overview_paged: 56,
  core_insight: 56,
  core_insight_continuation: 50,
  supporting_notes: 50,
  closing: 56
};

const Background: React.FC<{accent: string; highlight: string}> = ({
  accent,
  highlight
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const scan = ((frame / fps) * 105) % 130 - 15;
  const breathe = 0.7 + Math.sin(frame / 38) * 0.12;
  return (
    <AbsoluteFill
      style={{
        overflow: "hidden",
        background:
          "radial-gradient(circle at 75% 12%, #142d58 0%, #081424 34%, #040a12 78%)"
      }}
    >
      <AbsoluteFill
        style={{
          opacity: 0.22,
          backgroundImage:
            "linear-gradient(rgba(56,189,248,.22) 1px,transparent 1px),linear-gradient(90deg,rgba(56,189,248,.18) 1px,transparent 1px)",
          backgroundSize: "64px 64px",
          transform: `perspective(900px) rotateX(59deg) scale(1.55) translateY(${frame % 64}px)`,
          transformOrigin: "center 65%"
        }}
      />
      <div
        style={{
          position: "absolute",
          left: "-20%",
          top: `${scan}%`,
          width: "140%",
          height: 180,
          transform: "rotate(-7deg)",
          background: `linear-gradient(180deg,transparent,${accent}22,transparent)`,
          filter: "blur(18px)"
        }}
      />
      <div
        style={{
          position: "absolute",
          right: -180,
          top: 160,
          width: 520,
          height: 520,
          borderRadius: "50%",
          opacity: breathe,
          background: `radial-gradient(circle,${highlight}26,transparent 68%)`,
          filter: "blur(12px)"
        }}
      />
      {Array.from({length: 18}).map((_, index) => {
        const y = (frame * (0.45 + (index % 4) * 0.08) + index * 127) % 2100;
        return (
          <div
            key={index}
            style={{
              position: "absolute",
              left: 45 + ((index * 83) % 980),
              top: 1980 - y,
              width: index % 3 === 0 ? 5 : 3,
              height: index % 3 === 0 ? 5 : 3,
              borderRadius: "50%",
              background: index % 4 === 0 ? highlight : accent,
              opacity: 0.18 + (index % 5) * 0.07,
              boxShadow: `0 0 15px ${accent}`
            }}
          />
        );
      })}
    </AbsoluteFill>
  );
};

const Brand: React.FC<{dateLabel: string; accent: string}> = ({
  dateLabel,
  accent
}) => (
  <div
    style={{
      position: "absolute",
      top: 92,
      left: 76,
      right: 76,
      display: "flex",
      justifyContent: "space-between",
      alignItems: "center",
      fontFamily: FONT,
      fontSize: 28,
      letterSpacing: 2,
      color: "#b9c8dc"
    }}
  >
    <div>
      <span style={{color: accent, fontWeight: 800}}>AI</span> FRONTIER RADAR
    </div>
    <div style={{fontSize: 24, color: "#8293aa"}}>{dateLabel}</div>
  </div>
);

// Auto-scale font size so the longest line fits inside a target width.
const fitFontSize = (line: string, base: number, maxChars: number): number => {
  const len = Array.from(line).length;
  if (len <= maxChars) {
    return base;
  }
  const scaled = Math.max(18, Math.floor((base * maxChars) / len));
  return scaled;
};

const LinesBlock: React.FC<{
  scene: ReportScene;
  exit: number;
  accent: string;
  highlight: string;
}> = ({scene, exit, accent, highlight}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const isOpening = scene.type === "opening";
  const isClosing = scene.type === "closing";

  const baseFont = SCENE_FONT_SIZE[scene.type] ?? 30;
  const maxCharsPerLine = scene.lines.reduce(
    (acc, ln) => Math.max(acc, Array.from(ln).length),
    0
  );

  // Adjust base font if any line is unusually long.
  const fontSize = maxCharsPerLine > 24 ? Math.max(22, baseFont - 4) : baseFont;

  const lineDelay = 6;

  return (
    <div style={{display: "flex", flexDirection: "column", gap: 18}}>
      {scene.lines.map((line, index) => {
        const lineIn = spring({
          frame: frame - 10 - index * lineDelay,
          fps,
          config: {damping: 22, stiffness: 120}
        });
        const lineFont = fitFontSize(line, fontSize, 22);
        return (
          <div
            key={`${scene.id}-${index}`}
            style={{
              display: "flex",
              gap: 18,
              alignItems: "flex-start",
              padding: isOpening ? "16px 22px" : "20px 24px",
              borderRadius: 20,
              opacity: Math.max(0, lineIn) * exit,
              transform: `translateX(${interpolate(
                lineIn,
                [0, 1],
                [35, 0],
                clamp
              )}px)`,
              background:
                "linear-gradient(135deg,rgba(20,39,68,.84),rgba(8,20,36,.7))",
              border: "1px solid rgba(126,168,218,.22)",
              boxShadow: "0 18px 55px rgba(0,0,0,.22)",
              backdropFilter: "blur(18px)"
            }}
          >
            {isOpening || isClosing ? null : (
              <div
                style={{
                  flex: "0 0 auto",
                  width: 36,
                  height: 36,
                  marginTop: 3,
                  borderRadius: 12,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: "#08111f",
                  background: index === 0 ? highlight : accent,
                  fontWeight: 900,
                  fontSize: 19
                }}
              >
                {String(index + 1).padStart(2, "0")}
              </div>
            )}
            <div
              style={{
                fontSize: lineFont,
                lineHeight: 1.45,
                fontWeight: index === 0 ? 750 : 600,
                color: "#ffffff",
                whiteSpace: "pre-wrap",
                wordBreak: "break-word"
              }}
            >
              {line}
            </div>
          </div>
        );
      })}
    </div>
  );
};

const ClosingExtras: React.FC<{
  scene: ReportScene;
  accent: string;
  highlight: string;
}> = ({scene, accent, highlight}) => {
  const qrUrl = scene.qrCodeDataUrl || null;
  const shareUrl = scene.shareUrl || null;

  return (
    <div
      style={{
        display: "flex",
        gap: 36,
        alignItems: "center",
        marginTop: 20,
        padding: 20,
        borderRadius: 20,
        background:
          "linear-gradient(135deg,rgba(20,39,68,.74),rgba(8,20,36,.6))",
        border: "1px solid rgba(126,168,218,.22)",
        boxShadow: "0 18px 55px rgba(0,0,0,.22)",
        backdropFilter: "blur(18px)"
      }}
    >
      <div
        style={{
          width: 220,
          height: 220,
          flex: "0 0 auto",
          borderRadius: 18,
          background: qrUrl
            ? `url(${qrUrl}) center/cover no-repeat #0a1322`
            : "linear-gradient(135deg,#0a1322,#050a14)",
          border: `1px solid ${accent}55`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "#b9c8dc",
          fontSize: 18,
          fontFamily: FONT,
          textAlign: "center",
          padding: 12
        }}
      >
        {!qrUrl ? (
          <span>{shareUrl ? "完整报告链接见右侧" : "完整报告入口暂不可用"}</span>
        ) : null}
      </div>
      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          gap: 12,
          fontFamily: FONT,
          color: "#f7fbff"
        }}
      >
        <div
          style={{
            color: highlight,
            fontSize: 26,
            fontWeight: 800,
            letterSpacing: 3
          }}
        >
          READ THE FULL REPORT
        </div>
        <div style={{fontSize: 24, lineHeight: 1.4, color: "#dbe7f4"}}>
          扫描二维码或在浏览器打开下方链接，查看完整报告、全部来源与原文链接。
        </div>
        {shareUrl ? (
          <div
            style={{
              marginTop: 6,
              padding: "10px 14px",
              borderRadius: 12,
              background: "rgba(8,20,36,.6)",
              border: "1px solid rgba(126,168,218,.22)",
              fontSize: 20,
              color: accent,
              wordBreak: "break-all"
            }}
          >
            {shareUrl}
          </div>
        ) : null}
      </div>
    </div>
  );
};

const SceneBody: React.FC<{
  scene: ReportScene;
  reportTitle: string;
  dateLabel: string;
  accent: string;
  highlight: string;
}> = ({scene, reportTitle, dateLabel, accent, highlight}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const enter = spring({
    frame,
    fps,
    config: {damping: 20, stiffness: 115, mass: 0.85}
  });
  const exitStart = Math.max(15, scene.durationInFrames - 14);
  const exit = interpolate(
    frame,
    [exitStart, scene.durationInFrames],
    [1, 0],
    clamp
  );
  const opacity = enter * exit;
  const y = interpolate(enter, [0, 1], [55, 0], clamp);

  const isOpening = scene.type === "opening";
  const isClosing = scene.type === "closing";
  const kicker =
    scene.kicker ||
    (scene.type === "overview_paged"
      ? "TODAY'S OVERVIEW"
      : scene.type === "core_insight"
        ? `CORE INSIGHT ${String(scene.index + 1).padStart(2, "0")}`
        : scene.type === "core_insight_continuation"
          ? "CORE INSIGHT · CONTINUED"
          : scene.type === "supporting_notes"
            ? "MORE SIGNALS"
            : isClosing
              ? "READ THE FULL REPORT"
              : "DAILY INTELLIGENCE");

  // Title shows reportTitle on opening, scene.title otherwise.  We do NOT
  // apply overflow:hidden to the title — long titles wrap onto the next
  // line.  Storyboard pages content instead of CSS-clipping it.
  const displayTitle = isOpening ? reportTitle : scene.title;
  const titleFontSize = SCENE_TITLE_SIZE[scene.type] ?? 56;
  const titleFontSizeAdjusted = Math.max(
    24,
    titleFontSize - Math.max(0, Array.from(displayTitle).length - 18) * 1.5
  );

  return (
    <AbsoluteFill style={{fontFamily: FONT, color: "#f7fbff"}}>
      <Background accent={accent} highlight={highlight} />
      <Brand dateLabel={dateLabel} accent={accent} />
      <div
        style={{
          position: "absolute",
          left: 76,
          right: 76,
          top: 220,
          opacity,
          transform: `translateY(${y}px)`
        }}
      >
        <div
          style={{
            color: accent,
            fontSize: 25,
            fontWeight: 800,
            letterSpacing: 4,
            marginBottom: 24
          }}
        >
          {kicker}
        </div>
        <div
          style={{
            fontSize: titleFontSizeAdjusted,
            lineHeight: 1.18,
            fontWeight: 900,
            letterSpacing: -2,
            textShadow: "0 14px 45px rgba(0,0,0,.38)",
            marginBottom: 18,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word"
          }}
        >
          {displayTitle}
        </div>
        <div
          style={{
            width: 116,
            height: 7,
            marginTop: 4,
            marginBottom: 28,
            borderRadius: 9,
            background: `linear-gradient(90deg,${accent},${highlight})`,
            boxShadow: `0 0 26px ${accent}88`
          }}
        />
        <LinesBlock
          scene={scene}
          exit={exit}
          accent={accent}
          highlight={highlight}
        />
        {isClosing ? (
          <ClosingExtras scene={scene} accent={accent} highlight={highlight} />
        ) : null}
      </div>
      <div
        style={{
          position: "absolute",
          left: 76,
          right: 76,
          bottom: 78,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          color: "#74869d",
          fontFamily: FONT,
          fontSize: 24
        }}
      >
        <span>{scene.sourceLabel || "AI Frontier Radar"}</span>
        <span style={{color: accent}}>完整报告见分享页</span>
      </div>
    </AbsoluteFill>
  );
};

export const ReportVideo: React.FC<ReportVideoProps> = ({
  title,
  dateLabel,
  shareUrl,
  qrCodeDataUrl,
  scenes,
  style
}) => {
  let offset = 0;
  return (
    <AbsoluteFill style={{backgroundColor: "#040a12"}}>
      {scenes.map((scene) => {
        const from = offset;
        const duration = Math.max(30, scene.durationInFrames);
        offset += duration;
        // Forward shareUrl/qrCodeDataUrl to the closing scene only —
        // other scenes don't need them.
        const isClosing = scene.type === "closing";
        return (
          <Sequence
            key={scene.id}
            from={from}
            durationInFrames={duration}
            premountFor={30}
          >
            <SceneBody
              scene={{
                ...scene,
                durationInFrames: duration,
                shareUrl: isClosing ? scene.shareUrl || shareUrl || null : null,
                qrCodeDataUrl: isClosing
                  ? scene.qrCodeDataUrl || qrCodeDataUrl || null
                  : null
              }}
              reportTitle={title}
              dateLabel={dateLabel}
              accent={style.accentColor}
              highlight={style.highlightColor}
            />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
