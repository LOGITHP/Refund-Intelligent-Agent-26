import React from 'react';
import {
  AbsoluteFill,
  Audio,
  interpolate,
  Sequence,
  staticFile,
  useCurrentFrame,
} from 'remotion';
import { SubtitleBar } from '../components/SubtitleBar';
import { SCENES, TOTAL_DURATION_FRAMES, VIDEO_FPS } from '../data/narration';
import { Scene1Intro } from '../scenes/Scene1Intro';
import { Scene2LaptopStory } from '../scenes/Scene2LaptopStory';
import { Scene3MultiParty } from '../scenes/Scene3MultiParty';
import { Scene4SolutionReveal } from '../scenes/Scene4SolutionReveal';
import { Scene5AgentWorkflow } from '../scenes/Scene5AgentWorkflow';
import { Scene6HumanApproval } from '../scenes/Scene6HumanApproval';
import { Scene7ClosingGoal } from '../scenes/Scene7ClosingGoal';

export interface ExplainerVideoProps {
  showSubtitles?: boolean;
  enableAudio?: boolean;
}

export const ExplainerVideo: React.FC<ExplainerVideoProps> = ({
  showSubtitles = true,
  enableAudio = true,
}) => {
  const frame = useCurrentFrame();

  const progressPercent = interpolate(
    frame,
    [0, TOTAL_DURATION_FRAMES - 1],
    [0, 100],
    {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
    },
  );

  return (
    <AbsoluteFill className="bg-[#f8fafc] overflow-hidden">
      {/* Synced AI Narration Track */}
      {enableAudio && <Audio src={staticFile('audio/narration_script.mp3')} />}
      {/* Scenes mounted cleanly via Remotion Sequence */}
      <Sequence
        from={SCENES[0].startFrame}
        durationInFrames={SCENES[0].durationFrames}
        premountFor={VIDEO_FPS}
      >
        <Scene1Intro />
      </Sequence>

      <Sequence
        from={SCENES[1].startFrame}
        durationInFrames={SCENES[1].durationFrames}
        premountFor={VIDEO_FPS}
      >
        <Scene2LaptopStory />
      </Sequence>

      <Sequence
        from={SCENES[2].startFrame}
        durationInFrames={SCENES[2].durationFrames}
        premountFor={VIDEO_FPS}
      >
        <Scene3MultiParty />
      </Sequence>

      <Sequence
        from={SCENES[3].startFrame}
        durationInFrames={SCENES[3].durationFrames}
        premountFor={VIDEO_FPS}
      >
        <Scene4SolutionReveal />
      </Sequence>

      <Sequence
        from={SCENES[4].startFrame}
        durationInFrames={SCENES[4].durationFrames}
        premountFor={VIDEO_FPS}
      >
        <Scene5AgentWorkflow />
      </Sequence>

      <Sequence
        from={SCENES[5].startFrame}
        durationInFrames={SCENES[5].durationFrames}
        premountFor={VIDEO_FPS}
      >
        <Scene6HumanApproval />
      </Sequence>

      <Sequence
        from={SCENES[6].startFrame}
        durationInFrames={SCENES[6].durationFrames}
        premountFor={VIDEO_FPS}
      >
        <Scene7ClosingGoal />
      </Sequence>

      {/* Persistent slim top progress bar */}
      <div
        className="absolute top-0 left-0 right-0 z-50 bg-slate-200/70 pointer-events-none"
        style={{ height: 4 }}
      >
        <div
          className="h-full"
          style={{
            width: `${progressPercent}%`,
            backgroundColor: '#2874f0',
          }}
        />
      </div>

      {/* Global Subtitle Overlay */}
      {showSubtitles && <SubtitleBar />}
    </AbsoluteFill>
  );
};
