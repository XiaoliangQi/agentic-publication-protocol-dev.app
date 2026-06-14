import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { C, MONO, SERIF } from "../theme";
import { easeOut, fadeUp, Grain, Overline } from "../common";

export const RESULTS_DURATION = 280;

const BAR_MAX_WIDTH = 880;

const Bar: React.FC<{
  label: string;
  score: number;
  color: string;
  textColor: string;
  delay: number;
}> = ({ label, score, color, textColor, delay }) => {
  const frame = useCurrentFrame();
  const progress = interpolate(frame, [delay, delay + 55], [0, 1], {
    easing: easeOut,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const width = (score / 10) * BAR_MAX_WIDTH * progress;
  const shown = (score * progress).toFixed(2);
  const appear = interpolate(frame, [delay - 8, delay + 8], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div style={{ marginBottom: 56, opacity: appear }}>
      <div
        style={{
          fontFamily: MONO,
          fontSize: 27,
          color: C.cream,
          marginBottom: 16,
        }}
      >
        {label}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 28 }}>
        <div
          style={{
            width,
            height: 74,
            background: color,
            borderRadius: 6,
          }}
        />
        <div
          style={{
            fontFamily: MONO,
            fontWeight: 600,
            fontSize: 46,
            color: textColor,
          }}
        >
          {shown}
        </div>
      </div>
    </div>
  );
};

export const Results: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const exit = interpolate(frame, [RESULTS_DURATION - 16, RESULTS_DURATION], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const statSpr = spring({
    frame: frame - 135,
    fps,
    config: { damping: 14, stiffness: 180, mass: 0.9 },
  });
  const statScale = interpolate(statSpr, [0, 1], [1.6, 1]);
  const statOpacity = interpolate(frame, [135, 143], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ background: C.night }}>
      <AbsoluteFill style={{ padding: "120px 150px", opacity: exit }}>
        <div style={fadeUp(frame, 4, 26, 18)}>
          <Overline color={C.amber}>
            Blind evaluation · 11 arXiv papers · same questions
          </Overline>
        </div>
        <div style={{ height: 36 }} />
        <div
          style={{
            fontFamily: SERIF,
            fontWeight: 900,
            fontSize: 92,
            color: C.cream,
            letterSpacing: "-0.01em",
            ...fadeUp(frame, 10),
          }}
        >
          Does it work?
        </div>

        <div style={{ display: "flex", marginTop: 90, alignItems: "flex-start" }}>
          <div style={{ width: 1130 }}>
            <Bar
              label="APP paper agent"
              score={9.25}
              color={C.amber}
              textColor={C.amber}
              delay={42}
            />
            <Bar
              label="general repo-aware agent"
              score={8.50}
              color="#3B352A"
              textColor={C.creamDim}
              delay={62}
            />
            <div
              style={{
                fontFamily: MONO,
                fontSize: 23,
                color: C.creamDim,
                ...fadeUp(frame, 112, 26, 16),
              }}
            >
              mean evaluator score / 10 — accuracy · informativeness · grounding · honesty
            </div>
          </div>

          <div style={{ flex: 1, textAlign: "center", paddingTop: 10 }}>
            <div
              style={{
                fontFamily: SERIF,
                fontWeight: 900,
                fontSize: 210,
                lineHeight: 1,
                color: C.cream,
                transform: `scale(${statScale})`,
                opacity: statOpacity,
              }}
            >
              11<span style={{ color: C.accent }}>/</span>11
            </div>
            <div
              style={{
                fontFamily: MONO,
                fontSize: 28,
                color: C.creamDim,
                marginTop: 26,
                ...fadeUp(frame, 158, 26, 16),
              }}
            >
              head-to-head wins
            </div>
          </div>
        </div>

        <div
          style={{
            marginTop: 70,
            fontFamily: MONO,
            fontSize: 28,
            color: C.cream,
            ...fadeUp(frame, 195, 28, 20),
          }}
        >
          largest margins: <span style={{ color: C.amber }}>grounding</span> &{" "}
          <span style={{ color: C.amber }}>honesty</span> — exactly what APP is for
        </div>
      </AbsoluteFill>
      <Grain opacity={0.05} blend="screen" />
    </AbsoluteFill>
  );
};
