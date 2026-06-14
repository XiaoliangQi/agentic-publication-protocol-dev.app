import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { C, MONO, SERIF } from "../theme";
import { easeOut, Grain, Overline } from "../common";

// Opening title card. Doubles as the share/preview thumbnail, so frame 0
// must already be fully composed — no fade-ins here, only settle motion.
export const HOOK_DURATION = 45;

export const Hook: React.FC = () => {
  const frame = useCurrentFrame();
  const settle = interpolate(frame, [0, 18], [1.035, 1], {
    easing: easeOut,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const stampSettle = interpolate(frame, [0, 10], [1.18, 1], {
    easing: easeOut,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const exit = interpolate(frame, [HOOK_DURATION - 10, HOOK_DURATION], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ background: C.paper }}>
      <div style={{ position: "absolute", left: 150, top: 0, bottom: 0, width: 3, background: C.accent, opacity: 0.55 }} />
      <div style={{ position: "absolute", left: 168, top: 0, bottom: 0, width: 1, background: C.line }} />

      <AbsoluteFill
        style={{
          justifyContent: "center",
          alignItems: "center",
          opacity: exit,
          transform: `scale(${settle})`,
        }}
      >
        <div style={{ textAlign: "center" }}>
          <Overline style={{ textAlign: "center" }}>
            A new format for scientific publication
          </Overline>
          <div style={{ height: 44 }} />
          <div
            style={{
              fontFamily: SERIF,
              fontWeight: 900,
              fontSize: 124,
              lineHeight: 1.05,
              color: C.ink,
              letterSpacing: "-0.015em",
            }}
          >
            Agentic Publication
            <br />
            Protocol
          </div>
          <div style={{ height: 46 }} />
          <div
            style={{
              fontFamily: MONO,
              fontWeight: 600,
              fontSize: 38,
              color: C.accent,
            }}
          >
            Publish the paper. Ship the agent.
          </div>
        </div>
      </AbsoluteFill>

      <div
        style={{
          position: "absolute",
          right: 150,
          top: 110,
          transform: `rotate(-9deg) scale(${stampSettle})`,
          opacity: 0.95 * exit,
          fontFamily: MONO,
          fontWeight: 600,
          fontSize: 64,
          letterSpacing: "0.12em",
          color: C.accent,
          border: `6px double ${C.accent}`,
          padding: "14px 30px",
        }}
      >
        APP
      </div>
      <Grain />
    </AbsoluteFill>
  );
};
