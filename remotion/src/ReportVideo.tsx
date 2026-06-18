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

const SceneBody: React.FC<{
  scene: ReportScene;
  reportTitle: string;
  subtitle: string;
  dateLabel: string;
  accent: string;
  highlight: string;
}> = ({scene, reportTitle, subtitle, dateLabel, accent, highlight}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const enter = spring({
    frame,
    fps,
    config: {damping: 20, stiffness: 115, mass: 0.85}
  });
  const exitStart = Math.max(15, scene.durationInFrames - 14);
  const exit = interpolate(frame, [exitStart, scene.durationInFrames], [1, 0], clamp);
  const opacity = enter * exit;
  const y = interpolate(enter, [0, 1], [55, 0], clamp);
  const lineDelay = 7;
  const isOpening = scene.type === "opening_summary";
  const isClosing = scene.type === "closing_cta";
  const kicker =
    scene.type === "summary_overview"
      ? "TODAY'S OVERVIEW"
      : scene.type === "signal"
        ? `CORE INSIGHT ${String(scene.index).padStart(2, "0")}`
        : scene.type === "supporting_notes"
          ? "MORE SIGNALS"
          : isClosing
            ? "READ THE FULL REPORT"
            : "DAILY INTELLIGENCE";

  return (
    <AbsoluteFill style={{fontFamily: FONT, color: "#f7fbff"}}>
      <Background accent={accent} highlight={highlight} />
      <Brand dateLabel={dateLabel} accent={accent} />
      <div
        style={{
          position: "absolute",
          left: 76,
          right: 76,
          top: isOpening ? 355 : 300,
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
            marginBottom: 28
          }}
        >
          {kicker}
        </div>
        <div
          style={{
            fontSize: isOpening ? 78 : isClosing ? 66 : 64,
            lineHeight: 1.19,
            fontWeight: 900,
            letterSpacing: -2,
            textShadow: "0 14px 45px rgba(0,0,0,.38)",
            maxHeight: 330,
            overflow: "hidden"
          }}
        >
          {isOpening ? reportTitle : scene.title}
        </div>
        {isOpening && subtitle ? (
          <div
            style={{
              marginTop: 30,
              maxWidth: 860,
              fontSize: 34,
              lineHeight: 1.55,
              color: "#b9c8dc"
            }}
          >
            {subtitle}
          </div>
        ) : null}
        <div
          style={{
            width: 116,
            height: 7,
            marginTop: 34,
            marginBottom: 42,
            borderRadius: 9,
            background: `linear-gradient(90deg,${accent},${highlight})`,
            boxShadow: `0 0 26px ${accent}88`
          }}
        />
        <div style={{display: "flex", flexDirection: "column", gap: 22}}>
          {scene.lines.slice(0, isOpening ? 3 : 4).map((line, index) => {
            const lineIn = spring({
              frame: frame - 12 - index * lineDelay,
              fps,
              config: {damping: 22, stiffness: 120}
            });
            return (
              <div
                key={`${scene.id}-${index}`}
                style={{
                  display: "flex",
                  gap: 20,
                  alignItems: "flex-start",
                  padding: isOpening ? "17px 22px" : "24px 26px",
                  borderRadius: 20,
                  opacity: Math.max(0, lineIn) * exit,
                  transform: `translateX(${interpolate(lineIn, [0, 1], [35, 0], clamp)}px)`,
                  background: "linear-gradient(135deg,rgba(20,39,68,.84),rgba(8,20,36,.7))",
                  border: "1px solid rgba(126,168,218,.22)",
                  boxShadow: "0 18px 55px rgba(0,0,0,.22)",
                  backdropFilter: "blur(18px)"
                }}
              >
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
                <div
                  style={{
                    fontSize: isOpening ? 30 : 35,
                    lineHeight: 1.48,
                    fontWeight: index === 0 ? 750 : 600,
                    color: index === 0 ? "#ffffff" : "#dbe7f4"
                  }}
                >
                  {line}
                </div>
              </div>
            );
          })}
        </div>
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
  subtitle,
  dateLabel,
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
        return (
          <Sequence
            key={scene.id}
            from={from}
            durationInFrames={duration}
            premountFor={30}
          >
            <SceneBody
              scene={{...scene, durationInFrames: duration}}
              reportTitle={title}
              subtitle={subtitle}
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
