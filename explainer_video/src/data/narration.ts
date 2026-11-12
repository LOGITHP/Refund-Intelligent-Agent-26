export const VIDEO_FPS = 30;
export const VIDEO_WIDTH = 1920;
export const VIDEO_HEIGHT = 1080;
export const TOTAL_DURATION_FRAMES = 2700; // 90.0s @ 1.0x (~1m 30s), ~78s @ 1.15x (1.30 min)

export interface SceneSpec {
  id: string;
  index: number;
  title: string;
  shortLabel: string;
  startFrame: number;
  durationFrames: number;
  tag: string;
}

export interface SubtitleCue {
  id: number;
  sceneId: string;
  startFrame: number;
  endFrame: number;
  text: string;
  highlightTerms?: string[];
}

export const SCENES: readonly SceneSpec[] = [
  {
    id: 'intro',
    index: 1,
    title: 'Welcome & Project Introduction',
    shortLabel: '1. Intro',
    startFrame: 0,
    durationFrames: 270,
    tag: 'PRESENTATION',
  },
  {
    id: 'laptop-story',
    index: 2,
    title: 'Real-World Laptop Refund Experience',
    shortLabel: '2. Story',
    startFrame: 270,
    durationFrames: 570,
    tag: 'REAL-WORLD PROBLEM',
  },
  {
    id: 'multi-party',
    index: 3,
    title: 'Core Question & Multi-Party Maze',
    shortLabel: '3. Root Problem',
    startFrame: 840,
    durationFrames: 540,
    tag: 'ECOSYSTEM GAP',
  },
  {
    id: 'solution-reveal',
    index: 4,
    title: 'Our Purpose & Solution Reveal',
    shortLabel: '4. Solution',
    startFrame: 1380,
    durationFrames: 300,
    tag: 'PLATFORM VISION',
  },
  {
    id: 'agent-workflow',
    index: 5,
    title: 'Active Agentic Lifecycle Workflow',
    shortLabel: '5. AI Agents',
    startFrame: 1680,
    durationFrames: 480,
    tag: 'AUTONOMOUS MONITORING',
  },
  {
    id: 'human-approval',
    index: 6,
    title: 'Actionable Resolution & Human Gate',
    shortLabel: '6. Human Gate',
    startFrame: 2160,
    durationFrames: 345,
    tag: 'KEY DIFFERENTIATOR',
  },
  {
    id: 'closing-goal',
    index: 7,
    title: 'Accountable, Transparent, Faster',
    shortLabel: '7. Goal',
    startFrame: 2505,
    durationFrames: 195,
    tag: 'OUR COMMITMENT',
  },
] as const;

export const SUBTITLE_CUES: readonly SubtitleCue[] = [
  {
    id: 1,
    sceneId: 'intro',
    startFrame: 0,
    endFrame: 75,
    text: 'Good morning everyone.',
  },
  {
    id: 2,
    sceneId: 'intro',
    startFrame: 75,
    endFrame: 270,
    text: 'I am LOGITH P, and today I am presenting our project, Agentic Refund Intelligence and Resolution Platform.',
    highlightTerms: ['LOGITH P', 'Agentic Refund Intelligence and Resolution Platform'],
  },
  {
    id: 3,
    sceneId: 'laptop-story',
    startFrame: 270,
    endFrame: 360,
    text: 'Let me start with a real-world experience.',
  },
  {
    id: 4,
    sceneId: 'laptop-story',
    startFrame: 360,
    endFrame: 540,
    text: 'A few years ago, when I ordered a laptop online, I experienced the difficulties associated with the refund process.',
    highlightTerms: ['laptop online', 'refund process'],
  },
  {
    id: 5,
    sceneId: 'laptop-story',
    startFrame: 540,
    endFrame: 675,
    text: 'Getting a refund was not as simple as returning a product.',
  },
  {
    id: 6,
    sceneId: 'laptop-story',
    startFrame: 675,
    endFrame: 840,
    text: 'There were delays, uncertainty, and a lack of clear information about where the money was and when I would receive it.',
    highlightTerms: ['delays, uncertainty', 'where the money was'],
  },
  {
    id: 7,
    sceneId: 'multi-party',
    startFrame: 840,
    endFrame: 1005,
    text: 'This made me think: Why should customers struggle to get their own money back after a valid return?',
    highlightTerms: ['Why should customers struggle'],
  },
  {
    id: 8,
    sceneId: 'multi-party',
    startFrame: 1005,
    endFrame: 1215,
    text: 'The actual problem is that the refund process involves multiple parties, including customers, merchants, payment gateways, banks, and sometimes regulatory authorities.',
    highlightTerms: ['multiple parties', 'customers, merchants, payment gateways, banks', 'regulatory authorities'],
  },
  {
    id: 9,
    sceneId: 'multi-party',
    startFrame: 1215,
    endFrame: 1380,
    text: 'A delay at any stage can leave customers without proper updates or resolution.',
    highlightTerms: ['delay at any stage'],
  },
  {
    id: 10,
    sceneId: 'solution-reveal',
    startFrame: 1380,
    endFrame: 1560,
    text: 'Our purpose is to make this entire process transparent, traceable, and intelligent.',
    highlightTerms: ['transparent, traceable, and intelligent'],
  },
  {
    id: 11,
    sceneId: 'solution-reveal',
    startFrame: 1560,
    endFrame: 1680,
    text: 'Introducing our solution: Agentic Refund Intelligence Platform.',
    highlightTerms: ['Agentic Refund Intelligence Platform'],
  },
  {
    id: 12,
    sceneId: 'agent-workflow',
    startFrame: 1680,
    endFrame: 1860,
    text: 'Instead of simply displaying refund status, our platform uses AI agents to actively monitor the entire refund lifecycle,',
    highlightTerms: ['AI agents', 'actively monitor'],
  },
  {
    id: 13,
    sceneId: 'agent-workflow',
    startFrame: 1860,
    endFrame: 2010,
    text: 'identify the reason for delays, collect supporting evidence, communicate with customers,',
    highlightTerms: ['identify the reason for delays', 'collect supporting evidence', 'communicate with customers'],
  },
  {
    id: 14,
    sceneId: 'agent-workflow',
    startFrame: 2010,
    endFrame: 2160,
    text: 'and escalate unresolved cases to the appropriate authority.',
    highlightTerms: ['escalate unresolved cases'],
  },
  {
    id: 15,
    sceneId: 'human-approval',
    startFrame: 2160,
    endFrame: 2325,
    text: "What makes us different is that we don't just track refunds; we identify why refunds are stuck",
    highlightTerms: ["don't just track refunds", 'why refunds are stuck'],
  },
  {
    id: 16,
    sceneId: 'human-approval',
    startFrame: 2325,
    endFrame: 2505,
    text: 'and take action to move them towards resolution, with human approval wherever required.',
    highlightTerms: ['take action', 'human approval'],
  },
  {
    id: 17,
    sceneId: 'closing-goal',
    startFrame: 2505,
    endFrame: 2700,
    text: 'Our goal is simple: Make every refund accountable, transparent, and faster.',
    highlightTerms: ['accountable, transparent, and faster'],
  },
] as const;

export function getActiveScene(frame: number): SceneSpec {
  for (const scene of SCENES) {
    if (frame >= scene.startFrame && frame < scene.startFrame + scene.durationFrames) {
      return scene;
    }
  }
  return SCENES[SCENES.length - 1];
}

export function getActiveSubtitleCue(frame: number): SubtitleCue | null {
  for (const cue of SUBTITLE_CUES) {
    if (frame >= cue.startFrame && frame < cue.endFrame) {
      return cue;
    }
  }
  return frame >= TOTAL_DURATION_FRAMES ? SUBTITLE_CUES[SUBTITLE_CUES.length - 1] : null;
}

