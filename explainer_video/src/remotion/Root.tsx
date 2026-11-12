import React from 'react';
import { Composition } from 'remotion';
import { ExplainerVideo } from '../compositions/ExplainerVideo';
import {
  TOTAL_DURATION_FRAMES,
  VIDEO_FPS,
  VIDEO_HEIGHT,
  VIDEO_WIDTH,
} from '../data/narration';
import '../index.css';

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="ExplainerVideo"
      component={ExplainerVideo}
      durationInFrames={TOTAL_DURATION_FRAMES}
      fps={VIDEO_FPS}
      width={VIDEO_WIDTH}
      height={VIDEO_HEIGHT}
      defaultProps={{
        showSubtitles: true,
        enableAudio: true,
      }}
    />
  );
};
