import "./index.css";
import React from "react";
import { Composition } from "remotion";
import { Main, TOTAL_DURATION } from "./Main";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="AppPromo"
        component={Main}
        durationInFrames={TOTAL_DURATION}
        fps={30}
        width={1920}
        height={1080}
      />
    </>
  );
};
