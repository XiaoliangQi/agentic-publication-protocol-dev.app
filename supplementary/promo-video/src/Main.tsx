import React from "react";
import { AbsoluteFill, Sequence, staticFile } from "remotion";
import { Audio } from "@remotion/media";
import { C } from "./theme";
import { Hook, HOOK_DURATION } from "./scenes/Hook";
import { ColdOpen, COLD_OPEN_DURATION } from "./scenes/ColdOpen";
import { Problems, PROBLEMS_DURATION } from "./scenes/Problems";
import { Flip, FLIP_DURATION } from "./scenes/Flip";
import { Title, TITLE_DURATION } from "./scenes/Title";
import { Repo, REPO_DURATION } from "./scenes/Repo";
import { Workflow, WORKFLOW_DURATION } from "./scenes/Workflow";
import { Results, RESULTS_DURATION } from "./scenes/Results";
import { Network, NETWORK_DURATION } from "./scenes/Network";
import { Outro, OUTRO_DURATION } from "./scenes/Outro";

const SCENES: Array<[React.FC, number]> = [
  [Hook, HOOK_DURATION],
  [ColdOpen, COLD_OPEN_DURATION],
  [Problems, PROBLEMS_DURATION],
  [Flip, FLIP_DURATION],
  [Title, TITLE_DURATION],
  [Repo, REPO_DURATION],
  [Workflow, WORKFLOW_DURATION],
  [Results, RESULTS_DURATION],
  [Network, NETWORK_DURATION],
  [Outro, OUTRO_DURATION],
];

export const TOTAL_DURATION = SCENES.reduce((sum, [, d]) => sum + d, 0);

export const Main: React.FC = () => {
  let from = 0;
  return (
    <AbsoluteFill style={{ background: C.night }}>
      <Audio src={staticFile("music.wav")} volume={0.85} />
      {SCENES.map(([Scene, duration], i) => {
        const start = from;
        from += duration;
        return (
          <Sequence key={i} from={start} durationInFrames={duration}>
            <Scene />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
