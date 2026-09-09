"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, type ReaderApi } from "./client";

/**
 * Playback: one audio element, a queue of sentences, and the ability to stop
 * immediately.
 *
 * Three things here are decisions rather than mechanics.
 *
 * **Audio is fetched, not linked.** `<audio src=…>` cannot send the identity
 * header and cannot read `X-Reader-Real-Model`, so every clip arrives through
 * `fetch` as a blob. That also means a played clip can be kept and replayed
 * without asking a GPU to make it twice.
 *
 * **Pause must be instant, and it is.** Stopping is a property of the audio
 * element, not of the network. A clip still downloading is superseded by a
 * token check, never awaited.
 *
 * **Nothing plays until a person asks.** There is no autoplay on mount, on
 * page change, or on resume — resume restores the position and waits. A page
 * that starts talking on load talks over the screen reader announcing it.
 */

export type PlayerStatus = "idle" | "loading" | "playing" | "paused";

export interface PlayableSegment {
  segment_id: string;
  display_text: string;
}

/** Enough clips to cover a reader skipping back a few sentences. */
const MAX_CACHED_CLIPS = 8;

export const MIN_RATE = 0.5;
export const MAX_RATE = 2;

interface Clip {
  url: string;
  realModel: boolean;
}

export interface PlayerOptions {
  api: ReaderApi;
  documentId: string;
  segments: PlayableSegment[];
  /** Called when the reader's position changes in a way worth persisting. */
  onPosition?: (segmentId: string, offsetSeconds: number) => void;
  onError?: (error: ApiError) => void;
}

export interface Player {
  status: PlayerStatus;
  currentId: string | null;
  /** Null until something has been played. False means a placeholder tone. */
  realModel: boolean | null;
  rate: number;
  setRate: (rate: number) => void;
  /** Play a specific sentence. Always a response to a person acting. */
  playAt: (index: number) => void;
  /** Play if paused or idle, pause if playing. */
  toggle: () => void;
  stop: () => void;
  next: () => void;
  previous: () => void;
  /** Jump to a saved position. Used by resume, which is always a button press. */
  cue: (segmentId: string, offsetSeconds: number, andPlay?: boolean) => void;
}

export function usePlayer(options: PlayerOptions): Player {
  const { api, documentId, segments, onPosition, onError } = options;

  const [status, setStatus] = useState<PlayerStatus>("idle");
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [realModel, setRealModel] = useState<boolean | null>(null);
  const [rate, setRateState] = useState(1);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const clipsRef = useRef(new Map<string, Clip>());
  const requestRef = useRef(0);
  const seekRef = useRef<number | null>(null);
  const rateRef = useRef(rate);
  const indexRef = useRef(-1);

  // Handlers read these through refs so the audio element's listeners can be
  // attached once instead of being torn down whenever a page loads. They are
  // written in an effect, not during render: a ref written while rendering is
  // a value React is free to throw away and re-derive.
  const segmentsRef = useRef(segments);
  const onPositionRef = useRef(onPosition);
  const onErrorRef = useRef(onError);
  useEffect(() => {
    segmentsRef.current = segments;
    onPositionRef.current = onPosition;
    onErrorRef.current = onError;
  });

  const ensureAudio = useCallback((): HTMLAudioElement => {
    if (audioRef.current) return audioRef.current;
    const audio = new Audio();
    audio.preload = "auto";
    audioRef.current = audio;
    return audio;
  }, []);

  const clipFor = useCallback(
    async (segmentId: string): Promise<Clip> => {
      const cached = clipsRef.current.get(segmentId);
      if (cached) return cached;
      const { blob, realModel: isReal } = await api.getAudio(documentId, segmentId);
      const clip: Clip = { url: URL.createObjectURL(blob), realModel: isReal };
      clipsRef.current.set(segmentId, clip);
      for (const [key, value] of clipsRef.current) {
        if (clipsRef.current.size <= MAX_CACHED_CLIPS) break;
        if (key === segmentId) continue;
        URL.revokeObjectURL(value.url);
        clipsRef.current.delete(key);
      }
      return clip;
    },
    [api, documentId],
  );

  const reportError = useCallback((error: unknown) => {
    const apiError = error instanceof ApiError ? error : new ApiError("server", 0, String(error));
    onErrorRef.current?.(apiError);
  }, []);

  const load = useCallback(
    async (index: number, { andPlay }: { andPlay: boolean }) => {
      const segment = segmentsRef.current[index];
      if (!segment) return;
      const token = ++requestRef.current;
      setStatus("loading");
      try {
        const clip = await clipFor(segment.segment_id);
        if (token !== requestRef.current) return; // the reader moved on
        const audio = ensureAudio();
        audio.src = clip.url;
        audio.playbackRate = rateRef.current;
        // Speed without pitch shift. Browsers default to this, but the reader
        // hearing a chipmunk is bad enough to be worth stating.
        audio.preservesPitch = true;
        indexRef.current = index;
        setCurrentId(segment.segment_id);
        setRealModel(clip.realModel);
        if (!andPlay) {
          setStatus("paused");
          return;
        }
        await audio.play();
        if (token !== requestRef.current) return;
        setStatus("playing");
      } catch (error) {
        if (token !== requestRef.current) return;
        setStatus("paused");
        reportError(error);
      }
    },
    [clipFor, ensureAudio, reportError],
  );

  const playAt = useCallback(
    (index: number) => {
      seekRef.current = null;
      void load(index, { andPlay: true });
    },
    [load],
  );

  const cue = useCallback(
    (segmentId: string, offsetSeconds: number, andPlay = false) => {
      const index = segmentsRef.current.findIndex((s) => s.segment_id === segmentId);
      if (index < 0) return;
      seekRef.current = offsetSeconds;
      void load(index, { andPlay });
    },
    [load],
  );

  const stop = useCallback(() => {
    requestRef.current += 1; // supersede anything still downloading
    const audio = audioRef.current;
    if (audio) {
      const segment = segmentsRef.current[indexRef.current];
      if (segment) onPositionRef.current?.(segment.segment_id, audio.currentTime);
      audio.pause();
      audio.currentTime = 0;
    }
    // Stopped means nothing is current: no sentence stays marked as the one
    // being read, because none is.
    seekRef.current = null;
    indexRef.current = -1;
    setCurrentId(null);
    setStatus("idle");
  }, []);

  const toggle = useCallback(() => {
    const audio = audioRef.current;
    if (status === "playing" && audio) {
      audio.pause();
      setStatus("paused");
      const segment = segmentsRef.current[indexRef.current];
      if (segment) onPositionRef.current?.(segment.segment_id, audio.currentTime);
      return;
    }
    if (audio && currentId && status === "paused") {
      audio.playbackRate = rateRef.current;
      void audio
        .play()
        .then(() => setStatus("playing"))
        .catch(reportError);
      return;
    }
    playAt(indexRef.current >= 0 ? indexRef.current : 0);
  }, [status, currentId, playAt, reportError]);

  const next = useCallback(() => playAt(indexRef.current + 1), [playAt]);
  const previous = useCallback(() => playAt(Math.max(0, indexRef.current - 1)), [playAt]);

  const setRate = useCallback((value: number) => {
    const clamped = Math.min(MAX_RATE, Math.max(MIN_RATE, value));
    rateRef.current = clamped;
    setRateState(clamped);
    if (audioRef.current) audioRef.current.playbackRate = clamped;
  }, []);

  // One set of listeners for the life of the component.
  useEffect(() => {
    const audio = ensureAudio();

    const onLoadedData = () => {
      if (seekRef.current !== null) {
        audio.currentTime = seekRef.current;
        seekRef.current = null;
      }
    };

    const onEnded = () => {
      const finished = segmentsRef.current[indexRef.current];
      const following = indexRef.current + 1;
      if (following < segmentsRef.current.length) {
        // Continuing is not announced: the reader is listening to the book,
        // and a screen reader naming every sentence talks over it.
        playAt(following);
        return;
      }
      setStatus("idle");
      if (finished) onPositionRef.current?.(finished.segment_id, 0);
    };

    audio.addEventListener("loadeddata", onLoadedData);
    audio.addEventListener("ended", onEnded);
    return () => {
      audio.removeEventListener("loadeddata", onLoadedData);
      audio.removeEventListener("ended", onEnded);
    };
  }, [ensureAudio, playAt]);

  // Warm the next sentence while this one plays, so the gap between sentences
  // is not a fresh synthesis. The API deduplicates this against playback, so
  // asking early cannot make the same clip twice.
  useEffect(() => {
    if (status !== "playing") return;
    const upcoming = segments[indexRef.current + 1];
    if (!upcoming || clipsRef.current.has(upcoming.segment_id)) return;
    let cancelled = false;
    void clipFor(upcoming.segment_id).catch(() => {
      // A prefetch failure is not the reader's problem; it becomes one only if
      // they reach that sentence, and then it is reported by playback.
      if (cancelled) return;
    });
    return () => {
      cancelled = true;
    };
  }, [status, currentId, segments, clipFor]);

  // Leaving the page is a pause, and where they were is worth keeping.
  useEffect(() => {
    const clips = clipsRef.current;
    return () => {
      const audio = audioRef.current;
      if (audio) {
        const segment = segmentsRef.current[indexRef.current];
        if (segment && audio.currentTime > 0) {
          onPositionRef.current?.(segment.segment_id, audio.currentTime);
        }
        audio.pause();
        audio.removeAttribute("src");
      }
      for (const clip of clips.values()) URL.revokeObjectURL(clip.url);
      clips.clear();
    };
  }, []);

  return {
    status,
    currentId,
    realModel,
    rate,
    setRate,
    playAt,
    toggle,
    stop,
    next,
    previous,
    cue,
  };
}
