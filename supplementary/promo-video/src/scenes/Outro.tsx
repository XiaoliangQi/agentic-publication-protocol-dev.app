import React from "react";
import { AbsoluteFill, Easing, interpolate, useCurrentFrame } from "remotion";
import { C, MONO, SERIF } from "../theme";
import { Cursor, fadeUp, Grain, Overline } from "../common";

export const OUTRO_DURATION = 220;

export const Outro: React.FC = () => {
  const frame = useCurrentFrame();
  const radius = interpolate(frame, [0, 34], [0, 1500], {
    easing: Easing.bezier(0.7, 0, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ background: C.night }}>
      <AbsoluteFill
        style={{
          background: C.paper,
          clipPath: `circle(${radius}px at 50% 50%)`,
          justifyContent: "center",
          alignItems: "center",
        }}
      >
        <div style={{ textAlign: "center" }}>
          <div style={fadeUp(frame, 28, 28, 20)}>
            <Overline style={{ textAlign: "center" }}>
              Agentic Publication Protocol
            </Overline>
          </div>
          <div style={{ height: 50 }} />
          <div
            style={{
              fontFamily: SERIF,
              fontWeight: 900,
              fontSize: 116,
              lineHeight: 1.08,
              color: C.ink,
              letterSpacing: "-0.015em",
              ...fadeUp(frame, 38),
            }}
          >
            Publish your paper
          </div>
          <div
            style={{
              fontFamily: SERIF,
              fontWeight: 900,
              fontStyle: "italic",
              fontSize: 116,
              lineHeight: 1.08,
              color: C.accent,
              letterSpacing: "-0.015em",
              ...fadeUp(frame, 48),
            }}
          >
            as an agent.
            <Cursor color={C.accent} width={26} height={84} marginLeft={20} />
          </div>
          <div style={{ height: 70 }} />
          <div
            style={{
              fontFamily: MONO,
              fontWeight: 600,
              fontSize: 36,
              color: C.ink,
              background: C.paperDeep,
              display: "inline-block",
              padding: "20px 36px",
              borderRadius: 10,
              border: `1px solid ${C.line}`,
              ...fadeUp(frame, 80, 30, 24),
            }}
          >
            github.com/LionSR/AgenticPublicationProtocol
          </div>
          <div style={{ height: 56 }} />
          <div
            style={{
              fontFamily: MONO,
              fontSize: 24,
              color: C.inkSoft,
              ...fadeUp(frame, 112, 28, 16),
            }}
          >
            Sirui Lu &amp; Xiao-Liang Qi · 2026
          </div>
        </div>
        <Grain />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
