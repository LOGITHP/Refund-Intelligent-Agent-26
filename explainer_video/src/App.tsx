import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Player, type CallbackListener, type PlayerRef } from '@remotion/player';
import {
  Clock,
  Keyboard,
  Maximize2,
  Minimize2,
  PanelRightClose,
  PanelRightOpen,
  Pause,
  Play,
  RotateCcw,
  ShieldCheck,
  SkipBack,
  SkipForward,
  Subtitles,
  Video,
  Volume2,
  VolumeX,
} from 'lucide-react';
import { ExplainerVideo } from './compositions/ExplainerVideo';
import {
  SCENES,
  SUBTITLE_CUES,
  TOTAL_DURATION_FRAMES,
  VIDEO_FPS,
  VIDEO_HEIGHT,
  VIDEO_WIDTH,
  getActiveScene,
  getActiveSubtitleCue,
} from './data/narration';

interface SpeedPreset {
  rate: number;
  label: string;
  description: string;
}

const SPEED_PRESETS: readonly SpeedPreset[] = [
  { rate: 0.9, label: '0.9x (1m 40s)', description: 'Relaxed Narration' },
  { rate: 1.0, label: '1.0x (1m 30s)', description: 'Standard Presentation' },
  { rate: 1.15, label: '1.15x (1m 18s • 1.3m)', description: 'Fast Pitch' },
] as const;

const SEEK_STEP_FRAMES = VIDEO_FPS * 3; // +/- 3 seconds
const HUD_IDLE_HIDE_MS = 2000;

function formatTimestamp(frame: number, fps: number): string {
  const clamped = Math.max(0, Math.min(frame, TOTAL_DURATION_FRAMES));
  const totalSeconds = clamped / fps;
  const mins = Math.floor(totalSeconds / 60);
  const secs = Math.floor(totalSeconds % 60);
  const tenths = Math.floor((totalSeconds * 10 + 1e-6) % 10);
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}.${tenths}`;
}

export default function App() {
  const playerRef = useRef<PlayerRef>(null);
  const stageContainerRef = useRef<HTMLDivElement>(null);
  const activeCueRef = useRef<HTMLButtonElement | null>(null);
  const hudTimerRef = useRef<number | null>(null);

  const [currentFrame, setCurrentFrame] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackRate, setPlaybackRate] = useState<number>(1.0);
  const [showSubtitles, setShowSubtitles] = useState<boolean>(true);
  const [enableAudio, setEnableAudio] = useState<boolean>(true);
  const [showTeleprompter, setShowTeleprompter] = useState<boolean>(true);
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);
  const [isTheaterMode, setIsTheaterMode] = useState<boolean>(false);
  const [hudVisible, setHudVisible] = useState<boolean>(true);

  const isRecordMode = isFullscreen || isTheaterMode;

  const inputProps = useMemo(
    () => ({ showSubtitles, enableAudio }),
    [showSubtitles, enableAudio]
  );

  const activeScene = useMemo(() => getActiveScene(currentFrame), [currentFrame]);
  const activeCue = useMemo(() => getActiveSubtitleCue(currentFrame), [currentFrame]);

  // Real-time frame & playback state synchronization from Remotion Player
  useEffect(() => {
    const player = playerRef.current;
    if (!player) return;

    const handleFrameUpdate: CallbackListener<'frameupdate'> = (e) => {
      setCurrentFrame(e.detail.frame);
    };
    const handlePlay: CallbackListener<'play'> = () => {
      setIsPlaying(true);
    };
    const handlePause: CallbackListener<'pause'> = () => {
      setIsPlaying(false);
    };
    const handleEnded: CallbackListener<'ended'> = () => {
      setIsPlaying(false);
    };

    player.addEventListener('frameupdate', handleFrameUpdate);
    player.addEventListener('play', handlePlay);
    player.addEventListener('pause', handlePause);
    player.addEventListener('ended', handleEnded);

    return () => {
      player.removeEventListener('frameupdate', handleFrameUpdate);
      player.removeEventListener('play', handlePlay);
      player.removeEventListener('pause', handlePause);
      player.removeEventListener('ended', handleEnded);
    };
  }, []);

  // Sync native browser Fullscreen API state
  useEffect(() => {
    const onFullscreenChange = () => {
      const active = Boolean(document.fullscreenElement);
      setIsFullscreen(active);
      if (active) {
        setIsTheaterMode(false);
      }
    };
    document.addEventListener('fullscreenchange', onFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', onFullscreenChange);
  }, []);

  // Auto-hide minimal floating HUD in Record Mode after 2.0s while playing
  const scheduleHudAutoHide = useCallback(() => {
    if (hudTimerRef.current !== null) {
      window.clearTimeout(hudTimerRef.current);
      hudTimerRef.current = null;
    }
    setHudVisible(true);

    if (isRecordMode && isPlaying) {
      hudTimerRef.current = window.setTimeout(() => {
        setHudVisible(false);
      }, HUD_IDLE_HIDE_MS);
    }
  }, [isRecordMode, isPlaying]);

  useEffect(() => {
    scheduleHudAutoHide();
    return () => {
      if (hudTimerRef.current !== null) {
        window.clearTimeout(hudTimerRef.current);
        hudTimerRef.current = null;
      }
    };
  }, [scheduleHudAutoHide]);

  // Auto-scroll active teleprompter cue into view
  useEffect(() => {
    if (!showTeleprompter || isRecordMode) return;
    activeCueRef.current?.scrollIntoView({
      behavior: 'smooth',
      block: 'nearest',
    });
  }, [activeCue?.id, showTeleprompter, isRecordMode]);

  const handleTogglePlay = useCallback(() => {
    const player = playerRef.current;
    if (!player) return;
    if (player.isPlaying()) {
      player.pause();
    } else {
      if (currentFrame >= TOTAL_DURATION_FRAMES - 1) {
        player.seekTo(0);
      }
      player.play();
    }
  }, [currentFrame]);

  const handleRestart = useCallback(() => {
    const player = playerRef.current;
    if (!player) return;
    player.seekTo(0);
    setCurrentFrame(0);
    player.play();
  }, []);

  const handleSeekToFrame = useCallback((targetFrame: number) => {
    const player = playerRef.current;
    if (!player) return;
    const clamped = Math.max(0, Math.min(Math.round(targetFrame), TOTAL_DURATION_FRAMES - 1));
    player.seekTo(clamped);
    setCurrentFrame(clamped);
  }, []);

  const handleSeekRelative = useCallback(
    (deltaFrames: number) => {
      handleSeekToFrame(currentFrame + deltaFrames);
    },
    [currentFrame, handleSeekToFrame]
  );

  const toggleRecordMode = useCallback(async () => {
    const container = stageContainerRef.current;
    if (!container) return;

    if (document.fullscreenElement) {
      try {
        await document.exitFullscreen();
      } catch {
        setIsFullscreen(false);
      }
      setIsTheaterMode(false);
      return;
    }

    if (isTheaterMode) {
      setIsTheaterMode(false);
      return;
    }

    if (typeof container.requestFullscreen === 'function') {
      try {
        await container.requestFullscreen();
        return;
      } catch {
        // Fallback to clean in-window theater fullscreen if Fullscreen API is blocked
        setIsTheaterMode(true);
        return;
      }
    }

    setIsTheaterMode(true);
  }, [isTheaterMode]);

  // Global keyboard shortcuts for effortless screen-recording control
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;

      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      if (tag === 'TEXTAREA' || tag === 'SELECT') return;
      if (tag === 'INPUT' && (target as HTMLInputElement).type !== 'range') return;

      switch (e.code) {
        case 'Space':
          e.preventDefault();
          handleTogglePlay();
          scheduleHudAutoHide();
          break;
        case 'KeyR':
          e.preventDefault();
          handleRestart();
          scheduleHudAutoHide();
          break;
        case 'KeyF':
          e.preventDefault();
          void toggleRecordMode();
          break;
        case 'KeyC':
          e.preventDefault();
          setShowSubtitles((prev) => !prev);
          scheduleHudAutoHide();
          break;
        case 'KeyM':
          e.preventDefault();
          setEnableAudio((prev) => !prev);
          scheduleHudAutoHide();
          break;
        case 'ArrowLeft':
          e.preventDefault();
          handleSeekRelative(-SEEK_STEP_FRAMES);
          scheduleHudAutoHide();
          break;
        case 'ArrowRight':
          e.preventDefault();
          handleSeekRelative(SEEK_STEP_FRAMES);
          scheduleHudAutoHide();
          break;
        case 'Escape':
          if (isTheaterMode && !document.fullscreenElement) {
            e.preventDefault();
            setIsTheaterMode(false);
          }
          break;
        default:
          break;
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [
    handleRestart,
    handleSeekRelative,
    handleTogglePlay,
    isTheaterMode,
    scheduleHudAutoHide,
    toggleRecordMode,
  ]);

  const progressPct = useMemo(
    () => Math.min(100, Math.max(0, (currentFrame / (TOTAL_DURATION_FRAMES - 1)) * 100)),
    [currentFrame]
  );

  const effectiveTotalSeconds = Math.round(TOTAL_DURATION_FRAMES / VIDEO_FPS / playbackRate);

  return (
    <div className="min-h-screen flex flex-col bg-[#f4f6f9] text-[#212121]">
      {/* Clean Daylight Studio Header matching Shipkart Ops */}
      <header className="bg-white text-[#0f233a] border-b border-slate-200 shadow-sm">
        <div className="max-w-[1680px] mx-auto px-4 sm:px-6 py-3 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-9 h-9 rounded-lg bg-[#2874f0] flex items-center justify-center shadow-sm shrink-0">
              <ShieldCheck className="w-5 h-5 text-[#ffe11b]" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-bold tracking-tight text-base sm:text-lg text-[#0f233a] truncate">
                  Agentic Refund Intelligence Studio
                </span>
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-bold uppercase tracking-wider bg-[#ffe11b] text-[#0f233a]">
                  Shipkart Ops
                </span>
              </div>
              <p className="text-xs text-slate-500 truncate">
                1920×1080 Screen-Recordable Explainer Studio • Synced AI Voiceover & Subtitles
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <button
              type="button"
              onClick={() => setEnableAudio((v) => !v)}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors border ${
                enableAudio
                  ? 'bg-[#f0fdf4] border-[#16a34a]/40 text-[#15803d]'
                  : 'bg-[#f8fafc] border-slate-200 text-slate-600 hover:bg-slate-100'
              }`}
              title="Toggle synced narration audio (Shortcut: M)"
            >
              {enableAudio ? <Volume2 className="w-4 h-4" /> : <VolumeX className="w-4 h-4" />}
              <span>Audio {enableAudio ? 'ON' : 'MUTED'}</span>
              <kbd className="ml-0.5 px-1.5 py-0.5 rounded bg-white border border-slate-200 text-[#0f233a] text-[10px] font-mono">M</kbd>
            </button>

            <button
              type="button"
              onClick={() => setShowSubtitles((v) => !v)}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors border ${
                showSubtitles
                  ? 'bg-[#eff6ff] border-[#2874f0]/40 text-[#2874f0]'
                  : 'bg-[#f8fafc] border-slate-200 text-slate-600 hover:bg-slate-100'
              }`}
              title="Toggle burned-in subtitles (Shortcut: C)"
            >
              <Subtitles className="w-4 h-4" />
              <span>Subtitles {showSubtitles ? 'ON' : 'OFF'}</span>
              <kbd className="ml-0.5 px-1.5 py-0.5 rounded bg-white border border-slate-200 text-[#0f233a] text-[10px] font-mono">C</kbd>
            </button>

            <button
              type="button"
              onClick={() => setShowTeleprompter((v) => !v)}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors border ${
                showTeleprompter
                  ? 'bg-slate-100 border-slate-300 text-[#0f233a]'
                  : 'bg-[#f8fafc] border-slate-200 text-slate-600 hover:bg-slate-100'
              }`}
              title="Show or hide side Teleprompter narration script"
            >
              {showTeleprompter ? (
                <PanelRightClose className="w-4 h-4" />
              ) : (
                <PanelRightOpen className="w-4 h-4" />
              )}
              <span>Teleprompter</span>
            </button>

            <button
              type="button"
              onClick={() => void toggleRecordMode()}
              className="inline-flex items-center gap-2 px-4 py-1.5 rounded-lg text-xs sm:text-sm font-bold bg-[#2874f0] hover:bg-[#1e64d8] text-white shadow-sm transition-all"
              title="Enter clean fullscreen stage for screen recording (Shortcut: F)"
            >
              <Video className="w-4 h-4 text-[#ffe11b]" />
              <span>Fullscreen Record Mode (F)</span>
            </button>
          </div>
        </div>
      </header>

      {/* Main Studio Workspace */}
      <main className="flex-1 max-w-[1680px] w-full mx-auto px-4 sm:px-6 py-4 flex flex-col gap-4">
        {/* Scene Quick-Jump Strip */}
        <section
          aria-label="Scene Quick-Jump"
          className="bg-white rounded-xl border border-slate-200/90 shadow-sm px-3 py-2.5 flex items-center justify-between gap-3 flex-wrap"
        >
          <div className="flex items-center gap-1.5 flex-wrap">
            {SCENES.map((scene) => {
              const isActive = activeScene.id === scene.id;
              return (
                <button
                  key={scene.id}
                  type="button"
                  onClick={() => handleSeekToFrame(scene.startFrame)}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                    isActive
                      ? 'bg-[#2874f0] text-white shadow-sm ring-2 ring-[#2874f0]/25'
                      : 'bg-[#f4f6f9] text-[#0f233a] hover:bg-slate-200/80'
                  }`}
                  title={`${scene.title} (${formatTimestamp(scene.startFrame, VIDEO_FPS)})`}
                >
                  {isActive && (
                    <span className="w-2 h-2 rounded-full bg-[#ffe11b] shrink-0" />
                  )}
                  <span>{scene.shortLabel}</span>
                </button>
              );
            })}
          </div>

          <div className="flex items-center gap-2 text-xs text-slate-600">
            <span className="px-2 py-0.5 rounded bg-[#0f233a]/5 text-[#0f233a] font-semibold">
              {activeScene.tag}
            </span>
            <span className="hidden sm:inline font-medium text-slate-700">
              {activeScene.title}
            </span>
          </div>
        </section>

        {/* Stage + Off-Canvas Teleprompter Grid */}
        <div className="flex-1 flex flex-col lg:flex-row gap-4 items-stretch min-h-0">
          {/* Left / Main 16:9 Stage & Transport Controls */}
          <div className="flex-1 flex flex-col gap-3 min-w-0">
            {/* Screen-Recordable Stage Container */}
            <div
              ref={stageContainerRef}
              onMouseMove={isRecordMode ? scheduleHudAutoHide : undefined}
              onMouseEnter={isRecordMode ? scheduleHudAutoHide : undefined}
              className={
                isRecordMode
                  ? `fixed inset-0 z-50 bg-[#050c16] flex items-center justify-center select-none ${
                      !hudVisible && isPlaying ? 'cursor-none' : 'cursor-default'
                    }`
                  : 'relative w-full aspect-video bg-[#07111f] rounded-xl overflow-hidden shadow-xl border border-slate-300/80'
              }
            >
              <div
                className={
                  isRecordMode
                    ? 'w-full h-full flex items-center justify-center'
                    : 'w-full h-full'
                }
              >
                <div
                  className={
                    isRecordMode
                      ? 'w-full max-h-full aspect-video'
                      : 'w-full h-full'
                  }
                >
                  <Player
                    ref={playerRef}
                    component={ExplainerVideo}
                    inputProps={inputProps}
                    durationInFrames={TOTAL_DURATION_FRAMES}
                    compositionWidth={VIDEO_WIDTH}
                    compositionHeight={VIDEO_HEIGHT}
                    fps={VIDEO_FPS}
                    playbackRate={playbackRate}
                    controls={false}
                    clickToPlay={false}
                    style={{ width: '100%', height: '100%' }}
                  />
                </div>
              </div>

              {/* Auto-Hiding Minimal Floating HUD (top-centered so bottom SubtitleBar is NEVER covered) */}
              {isRecordMode && (
                <div
                  className={`fixed top-4 left-1/2 -translate-x-1/2 z-50 transition-all duration-300 ${
                    hudVisible
                      ? 'opacity-100 translate-y-0 pointer-events-auto'
                      : 'opacity-0 -translate-y-3 pointer-events-none'
                  }`}
                >
                  <div className="flex items-center gap-2 sm:gap-3 px-4 py-2.5 rounded-2xl bg-[#0f233a]/90 backdrop-blur-md border border-white/15 shadow-2xl text-white">
                    <button
                      type="button"
                      onClick={handleTogglePlay}
                      className="inline-flex items-center justify-center w-9 h-9 rounded-xl bg-[#2874f0] hover:bg-[#1e64d8] text-white transition-colors"
                      title="Play / Pause (Space)"
                    >
                      {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4 ml-0.5" />}
                    </button>

                    <button
                      type="button"
                      onClick={handleRestart}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-xs font-semibold transition-colors"
                      title="Restart from beginning (R)"
                    >
                      <RotateCcw className="w-3.5 h-3.5" />
                      <span>Restart</span>
                    </button>

                    <div className="flex items-center gap-2 px-2">
                      <span className="text-xs font-mono tabular-nums text-slate-200">
                        {formatTimestamp(currentFrame, VIDEO_FPS)}
                      </span>
                      <input
                        type="range"
                        min={0}
                        max={TOTAL_DURATION_FRAMES - 1}
                        value={currentFrame}
                        onChange={(e) => handleSeekToFrame(Number(e.target.value))}
                        aria-label="Video timeline scrubber"
                        className="w-28 sm:w-44 accent-[#2874f0] cursor-pointer"
                      />
                      <span className="text-xs font-mono tabular-nums text-slate-400">
                        {formatTimestamp(TOTAL_DURATION_FRAMES, VIDEO_FPS)}
                      </span>
                    </div>

                    <button
                      type="button"
                      onClick={() => setEnableAudio((v) => !v)}
                      className={`inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                        enableAudio
                          ? 'bg-emerald-500 text-white'
                          : 'bg-white/10 text-slate-300 hover:bg-white/20'
                      }`}
                      title="Toggle Narration Audio (M)"
                    >
                      {enableAudio ? <Volume2 className="w-3.5 h-3.5" /> : <VolumeX className="w-3.5 h-3.5" />}
                      <span>{enableAudio ? 'Audio' : 'Muted'}</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => setShowSubtitles((v) => !v)}
                      className={`inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                        showSubtitles
                          ? 'bg-[#ffe11b] text-[#0f233a]'
                          : 'bg-white/10 text-slate-300 hover:bg-white/20'
                      }`}
                      title="Toggle Subtitles (C)"
                    >
                      <Subtitles className="w-3.5 h-3.5" />
                      <span>CC</span>
                    </button>

                    <span className="hidden md:inline-block px-2 py-1 rounded-md bg-white/10 text-[11px] font-mono text-slate-200">
                      {playbackRate}x
                    </span>

                    <button
                      type="button"
                      onClick={() => void toggleRecordMode()}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-xs font-semibold transition-colors"
                      title="Exit Record Mode (F)"
                    >
                      <Minimize2 className="w-3.5 h-3.5" />
                      <span>Exit</span>
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Studio Transport, Scrubber & Speed Presets Card */}
            <section className="bg-white rounded-xl border border-slate-200/90 shadow-sm p-4 flex flex-col gap-3">
              {/* Timeline Scrubber */}
              <div className="flex items-center gap-3">
                <span className="text-xs font-mono font-semibold tabular-nums text-[#0f233a] w-14">
                  {formatTimestamp(currentFrame, VIDEO_FPS)}
                </span>

                <div className="relative flex-1 flex items-center">
                  <input
                    type="range"
                    min={0}
                    max={TOTAL_DURATION_FRAMES - 1}
                    value={currentFrame}
                    onChange={(e) => handleSeekToFrame(Number(e.target.value))}
                    aria-label="Seek video timeline"
                    className="w-full h-2 rounded-lg appearance-none cursor-pointer accent-[#2874f0] bg-slate-200"
                    style={{
                      background: `linear-gradient(to right, #2874f0 0%, #2874f0 ${progressPct}%, #e2e8f0 ${progressPct}%, #e2e8f0 100%)`,
                    }}
                  />
                </div>

                <span className="text-xs font-mono tabular-nums text-slate-500 w-14 text-right">
                  {formatTimestamp(TOTAL_DURATION_FRAMES, VIDEO_FPS)}
                </span>
              </div>

              {/* Transport Buttons + Speed Presets */}
              <div className="flex flex-wrap items-center justify-between gap-3">
                {/* Left: Playback Controls */}
                <div className="flex items-center gap-2 flex-wrap">
                  <button
                    type="button"
                    onClick={handleTogglePlay}
                    className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[#2874f0] hover:bg-[#1e64d8] text-white text-sm font-bold shadow-sm transition-colors"
                  >
                    {isPlaying ? (
                      <>
                        <Pause className="w-4 h-4" />
                        <span>Pause</span>
                      </>
                    ) : (
                      <>
                        <Play className="w-4 h-4" />
                        <span>Play</span>
                      </>
                    )}
                    <kbd className="ml-1 px-1.5 py-0.5 rounded bg-black/20 text-[10px] font-mono">
                      Space
                    </kbd>
                  </button>

                  <button
                    type="button"
                    onClick={handleRestart}
                    className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-[#f4f6f9] hover:bg-slate-200 text-[#0f233a] text-xs font-semibold border border-slate-200 transition-colors"
                    title="Restart from Frame 0 and play (R)"
                  >
                    <RotateCcw className="w-3.5 h-3.5" />
                    <span>Restart</span>
                    <kbd className="px-1 py-0.5 rounded bg-white text-[10px] font-mono border border-slate-200">
                      R
                    </kbd>
                  </button>

                  <button
                    type="button"
                    onClick={() => handleSeekRelative(-SEEK_STEP_FRAMES)}
                    className="inline-flex items-center gap-1 px-2.5 py-2 rounded-lg bg-[#f4f6f9] hover:bg-slate-200 text-[#0f233a] text-xs font-semibold border border-slate-200 transition-colors"
                    title="Rewind 3 seconds (Left Arrow)"
                  >
                    <SkipBack className="w-3.5 h-3.5" />
                    <span>-3s</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => handleSeekRelative(SEEK_STEP_FRAMES)}
                    className="inline-flex items-center gap-1 px-2.5 py-2 rounded-lg bg-[#f4f6f9] hover:bg-slate-200 text-[#0f233a] text-xs font-semibold border border-slate-200 transition-colors"
                    title="Forward 3 seconds (Right Arrow)"
                  >
                    <span>+3s</span>
                    <SkipForward className="w-3.5 h-3.5" />
                  </button>

                  <button
                    type="button"
                    onClick={() => void toggleRecordMode()}
                    className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-[#0f233a] hover:bg-[#173354] text-white text-xs font-semibold transition-colors"
                    title="Enter Fullscreen Record Mode (F)"
                  >
                    <Maximize2 className="w-3.5 h-3.5 text-[#ffe11b]" />
                    <span>Record Mode</span>
                  </button>
                </div>

                {/* Right: Speed Presets */}
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="inline-flex items-center gap-1 text-xs font-semibold text-slate-500">
                    <Clock className="w-3.5 h-3.5" />
                    <span>Pace:</span>
                  </span>

                  <div className="flex items-center gap-1.5 flex-wrap">
                    {SPEED_PRESETS.map((preset) => {
                      const active = Math.abs(playbackRate - preset.rate) < 0.001;
                      return (
                        <button
                          key={preset.rate}
                          type="button"
                          onClick={() => setPlaybackRate(preset.rate)}
                          title={`${preset.label} — ${preset.description}`}
                          className={`px-2.5 py-1.5 rounded-lg text-xs font-semibold transition-all border ${
                            active
                              ? 'bg-[#2874f0] text-white border-[#2874f0] shadow-sm'
                              : 'bg-[#f4f6f9] text-[#0f233a] border-slate-200 hover:bg-slate-200/80'
                          }`}
                        >
                          <span>{preset.label}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>

              {/* Compact Shortcuts & Pace Summary Footer */}
              <div className="pt-2 border-t border-slate-100 flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-500">
                <div className="flex items-center gap-3 flex-wrap">
                  <span className="inline-flex items-center gap-1 font-semibold text-slate-600">
                    <Keyboard className="w-3.5 h-3.5" />
                    Shortcuts:
                  </span>
                  <span>
                    <kbd className="px-1.5 py-0.5 rounded bg-slate-100 border border-slate-200 font-mono text-[#0f233a]">
                      F
                    </kbd>{' '}
                    Fullscreen Record
                  </span>
                  <span>
                    <kbd className="px-1.5 py-0.5 rounded bg-slate-100 border border-slate-200 font-mono text-[#0f233a]">
                      Space
                    </kbd>{' '}
                    Play/Pause
                  </span>
                  <span>
                    <kbd className="px-1.5 py-0.5 rounded bg-slate-100 border border-slate-200 font-mono text-[#0f233a]">
                      R
                    </kbd>{' '}
                    Restart
                  </span>
                  <span>
                    <kbd className="px-1.5 py-0.5 rounded bg-slate-100 border border-slate-200 font-mono text-[#0f233a]">
                      C
                    </kbd>{' '}
                    Subtitles
                  </span>
                  <span>
                    <kbd className="px-1.5 py-0.5 rounded bg-slate-100 border border-slate-200 font-mono text-[#0f233a]">
                      ←
                    </kbd>
                    /
                    <kbd className="px-1.5 py-0.5 rounded bg-slate-100 border border-slate-200 font-mono text-[#0f233a]">
                      →
                    </kbd>{' '}
                    ±3s
                  </span>
                </div>

                <div className="font-mono tabular-nums text-slate-600">
                  Frame {currentFrame}/{TOTAL_DURATION_FRAMES} • Effective runtime ~{effectiveTotalSeconds}s ({SPEED_PRESETS.find((p) => Math.abs(p.rate - playbackRate) < 0.001)?.description ?? `${playbackRate}x`})
                </div>
              </div>
            </section>
          </div>

          {/* Right: Toggleable Off-Canvas Teleprompter Panel (hidden in Record Mode) */}
          {showTeleprompter && !isRecordMode && (
            <aside
              aria-label="Narration Teleprompter"
              className="w-full lg:w-[380px] xl:w-[420px] shrink-0 bg-white rounded-xl border border-slate-200/90 shadow-sm flex flex-col max-h-[72vh] lg:max-h-[calc(100vh-180px)]"
            >
              <div className="px-4 py-3 bg-[#f8fafc] text-[#0f233a] border-b border-slate-200 rounded-t-xl flex items-center justify-between gap-2">
                <div>
                  <h2 className="text-sm font-bold flex items-center gap-2">
                    <span>Narration Teleprompter</span>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-[#eff6ff] border border-[#bfdbfe] text-[#2874f0]">
                      {SUBTITLE_CUES.length} Lines
                    </span>
                  </h2>
                  <p className="text-[11px] text-slate-500">
                    Click any line to jump directly to that frame
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setShowTeleprompter(false)}
                  className="p-1.5 rounded-lg bg-white border border-slate-200 hover:bg-slate-100 text-slate-600 transition-colors"
                  title="Close Teleprompter"
                >
                  <PanelRightClose className="w-4 h-4" />
                </button>
              </div>

              <div className="flex-1 overflow-y-auto p-3 space-y-2 bg-[#f4f6f9]/60">
                {SUBTITLE_CUES.map((cue) => {
                  const isCurrent = activeCue?.id === cue.id;
                  const cueScene = SCENES.find((s) => s.id === cue.sceneId);

                  return (
                    <button
                      key={cue.id}
                      ref={isCurrent ? activeCueRef : undefined}
                      type="button"
                      onClick={() => handleSeekToFrame(cue.startFrame)}
                      className={`w-full text-left p-3 rounded-xl border transition-all ${
                        isCurrent
                          ? 'bg-[#e8f0fe] border-[#2874f0] shadow-sm ring-1 ring-[#2874f0]/30'
                          : 'bg-white border-slate-200/80 hover:border-[#2874f0]/50 hover:bg-slate-50'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2 mb-1.5">
                        <div className="flex items-center gap-1.5">
                          <span
                            className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                              isCurrent
                                ? 'bg-[#2874f0] text-white'
                                : 'bg-slate-100 text-[#0f233a]'
                            }`}
                          >
                            #{cue.id}
                          </span>
                          {cueScene && (
                            <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                              {cueScene.shortLabel}
                            </span>
                          )}
                        </div>
                        <span className="text-[11px] font-mono tabular-nums text-slate-500">
                          {formatTimestamp(cue.startFrame, VIDEO_FPS)}
                        </span>
                      </div>

                      <p
                        className={`text-sm leading-relaxed ${
                          isCurrent ? 'font-semibold text-[#0f233a]' : 'text-slate-700'
                        }`}
                      >
                        {cue.text}
                      </p>
                    </button>
                  );
                })}
              </div>
            </aside>
          )}
        </div>
      </main>
    </div>
  );
}
