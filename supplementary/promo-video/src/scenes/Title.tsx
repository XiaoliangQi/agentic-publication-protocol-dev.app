import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { C, MONO, SERIF } from "../theme";
import { easeOut, fadeUp, Grain, Overline } from "../common";

export const TITLE_DURATION = 220;

const TitleLine: React.FC<{ text: string; delay: number }> = ({ text, delay }) => {
  const frame = useCurrentFrame();
  const y = interpolate(frame, [delay, delay + 38], [110, 0], {
    easing: easeOut,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <div style={{ overflow: "hidden" }}>
      <div
        style={{
          fontFamily: SERIF,
          fontWeight: 900,
          fontSize: 172,
          lineHeight: 1.0,
          letterSpacing: "-0.02em",
          color: C.cream,
          transform: `translateY(${y}%)`,
        }}
      >
        {text}
      </div>
    </div>
  );
};

export const Title: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const exit = interpolate(frame, [TITLE_DURATION - 16, TITLE_DURATION], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const stampSpr = spring({
    frame: frame - 52,
    fps,
    config: { damping: 15, stiffness: 200, mass: 0.8 },
  });
  const stampScale = interpolate(stampSpr, [0, 1], [2.4, 1]);
  const stampOpacity = interpolate(frame, [52, 57], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const ruleWidth = interpolate(frame, [80, 116], [0, 560], {
    easing: easeOut,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ background: C.night }}>
      <AbsoluteFill style={{ justifyContent: "center", paddingLeft: 170, opacity: exit }}>
        <div style={fadeUp(frame, 4, 26, 18)}>
          <Overline color={C.amber}>Introducing · v0.1</Overline>
        </div>
        <div style={{ height: 50 }} />
        <TitleLine text="Agentic" delay={10} />
        <TitleLine text="Publication" delay={20} />
        <TitleLine text="Protocol" delay={30} />
        <div style={{ height: 54 }} />
        <div style={{ width: ruleWidth, height: 3, background: C.accent }} />
        <div style={{ height: 40 }} />
        <div
          style={{
            fontFamily: MONO,
            fontSize: 42,
            fontWeight: 500,
            color: C.amber,
            ...fadeUp(frame, 92, 30, 26),
          }}
        >
          Publish the paper. Ship the agent.
        </div>
        <div style={{ height: 34 }} />
        <div
          style={{
            fontFamily: MONO,
            fontSize: 27,
            color: C.creamDim,
            ...fadeUp(frame, 122, 30, 20),
          }}
        >
          Sirui Lu · MPQ Garching&nbsp;&nbsp;—&nbsp;&nbsp;Xiao-Liang Qi · Stanford
        </div>
      </AbsoluteFill>

      <div
        style={{
          position: "absolute",
          right: 220,
          top: 200,
          transform: `rotate(-9deg) scale(${stampScale})`,
          opacity: stampOpacity * exit,
          fontFamily: MONO,
          fontWeight: 600,
          fontSize: 110,
          letterSpacing: "0.1em",
          color: C.accent,
          border: `7px double ${C.accent}`,
          padding: "20px 44px",
        }}
      >
        APP
      </div>
      <Grain opacity={0.05} blend="screen" />
    </AbsoluteFill>
  );
};
