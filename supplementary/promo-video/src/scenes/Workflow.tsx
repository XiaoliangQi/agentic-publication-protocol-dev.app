import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { C, MONO, SERIF } from "../theme";
import { easeInOut, fadeUp, Grain, Overline } from "../common";

export const WORKFLOW_DURATION = 260;

const STEPS = [
  "reproduce-results",
  "prepare-staging",
  "define-paper-agent",
  "validate-publication",
  "release-outcome",
];

const ACTIVATE_AT = (i: number) => 64 + i * 34;

const Node: React.FC<{ index: number }> = ({ index }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const at = ACTIVATE_AT(index);
  const active = frame >= at;
  const spr = spring({
    frame: frame - at,
    fps,
    config: { damping: 13, stiffness: 220, mass: 0.7 },
  });
  const scale = active ? interpolate(spr, [0, 1], [1.45, 1]) : 1;
  const appear = interpolate(frame, [14 + index * 5, 30 + index * 5], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        width: 300,
        opacity: appear,
      }}
    >
      <div
        style={{
          width: 88,
          height: 88,
          borderRadius: 44,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: MONO,
          fontWeight: 600,
          fontSize: 36,
          transform: `scale(${scale})`,
          background: active ? C.amber : "transparent",
          color: active ? C.night : C.creamDim,
          border: `3px solid ${active ? C.amber : C.nightBorder}`,
        }}
      >
        {active ? "✓" : index + 1}
      </div>
      <div
        style={{
          marginTop: 28,
          fontFamily: MONO,
          fontSize: 26,
          fontWeight: active ? 600 : 400,
          color: active ? C.cream : C.creamDim,
          textAlign: "center",
        }}
      >
        {STEPS[index]}
      </div>
    </div>
  );
};

export const Workflow: React.FC = () => {
  const frame = useCurrentFrame();
  const exit = interpolate(frame, [WORKFLOW_DURATION - 16, WORKFLOW_DURATION], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const lineFull = 1320;
  const lineProgress = interpolate(frame, [56, ACTIVATE_AT(4) + 10], [0, lineFull], {
    easing: easeInOut,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ background: C.night }}>
      <AbsoluteFill style={{ alignItems: "center", paddingTop: 130, opacity: exit }}>
        <div style={fadeUp(frame, 4, 26, 18)}>
          <Overline color={C.amber} style={{ textAlign: "center" }}>
            Author workflow
          </Overline>
        </div>
        <div style={{ height: 36 }} />
        <div
          style={{
            fontFamily: SERIF,
            fontWeight: 900,
            fontSize: 86,
            color: C.cream,
            letterSpacing: "-0.01em",
            ...fadeUp(frame, 10),
          }}
        >
          Five skills. One release.
        </div>
        <div style={{ height: 30 }} />
        <div
          style={{
            fontFamily: MONO,
            fontSize: 33,
            color: C.creamDim,
            ...fadeUp(frame, 36, 28, 22),
          }}
        >
          <span style={{ color: C.amber }}>$</span> /publish-paper
        </div>

        {/* pipeline */}
        <div style={{ position: "relative", marginTop: 130, width: 1500 }}>
          <div
            style={{
              position: "absolute",
              top: 43,
              left: 90,
              width: lineFull,
              height: 3,
              background: C.nightBorder,
            }}
          />
          <div
            style={{
              position: "absolute",
              top: 43,
              left: 90,
              width: lineProgress,
              height: 3,
              background: C.amber,
            }}
          />
          <div style={{ display: "flex", justifyContent: "space-between", position: "relative" }}>
            {STEPS.map((s, i) => (
              <Node key={s} index={i} />
            ))}
          </div>
        </div>

        <div
          style={{
            marginTop: 110,
            fontFamily: MONO,
            fontSize: 27,
            color: C.creamDim,
            ...fadeUp(frame, 215, 28, 20),
          }}
        >
          → a tagged, author-approved, agent-readable release
        </div>
      </AbsoluteFill>
      <Grain opacity={0.05} blend="screen" />
    </AbsoluteFill>
  );
};
