import React from "react";
import {
  CalculateMetadataFunction,
  Composition,
  registerRoot
} from "remotion";
import {ReportVideo} from "./ReportVideo";
import {defaultProps, ReportVideoProps} from "./types";

const FPS = 30;

const calculateMetadata: CalculateMetadataFunction<ReportVideoProps> = ({
  props
}) => ({
  durationInFrames: Math.max(
    FPS * 5,
    props.scenes.reduce(
      (total, scene) => total + Math.max(FPS, scene.durationInFrames),
      0
    )
  ),
  defaultOutName: `ai-frontier-radar-${props.dateLabel || "report"}.mp4`
});

const RemotionRoot: React.FC = () => (
  <Composition
    id="RadarReportVideo"
    component={ReportVideo}
    width={1080}
    height={1920}
    fps={FPS}
    durationInFrames={FPS * 10}
    defaultProps={defaultProps}
    calculateMetadata={calculateMetadata}
  />
);

registerRoot(RemotionRoot);
