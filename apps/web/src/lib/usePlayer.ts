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
 *
 * **The next sentences are made while this one plays.** Generating a sentence
 * takes about as long as hearing it, so asking for one at a time leaves a gap
 * before almost every sentence. From the moment play is pressed, the player
 * keeps the next `AHEAD` sentences coming, in reading order, with at most
 * `IN_FLIGHT` requests out at once (the first sentence counted among them).
 * It stops asking when the reader pauses or stops; whatever is already being
 * made still lands in the cache, so nothing is made twice. It never asks for a
 * whole page: a reader who stops after two sentences should not cost a GPU
 * thirty.
 */

export type PlayerStatus = "idle" | "loading" | "playing" | "paused";

export interface PlayableSegment {
  segment_id: string;
  display_text: string;
}

/** Sentences made ahead of the one playing. */
export const AHEAD = 4;
/** Audio requests out at once, the sentence being started included. */
export const IN_FLIGHT = 3;
/** Enough clips for the sentences ahead and a reader skipping back a few. */
const MAX_CACHED_CLIPS = 12;

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
  /** Called when a sentence has played to its end. */
  onHeard?: (segmentId: string) => void;
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
  const { api, documentId, segments, onPosition, onHeard, onError } = options;

  const [status, setStatus] = useState<PlayerStatus>("idle");
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [realModel, setRealModel] = useState<boolean | null>(null);
  const [rate, setRateState] = useState(1);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const clipsRef = useRef(new Map<string, Clip>());
  // One request per sentence, however many callers want it at once.
  const pendingRef = useRef(new Map<string, Promise<Clip>>());
  // The sentence being started or played, and whether the reader asked to hear
  // it: the window ahead follows the reader's intent, not the audio element,
  // so it starts with the first sentence rather than after it.
  const targetRef = useRef(-1);
  const wantRef = useRef(false);
  const disposedRef = useRef(false);
  // Each finished request tops the window up again, through the latest
  // version of fillAhead rather than the one that started it.
  const fillAheadRef = useRef<() => void>(() => {});
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
  const onHeardRef = useRef(onHeard);
  const onErrorRef = useRef(onError);
  useEffect(() => {
    segmentsRef.current = segments;
    onPositionRef.current = onPosition;
    onHeardRef.current = onHeard;
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
    (segmentId: string): Promise<Clip> => {
      const cached = clipsRef.current.get(segmentId);
      if (cached) return Promise.resolve(cached);
      const pending = pendingRef.current.get(segmentId);
      if (pending) return pending;
      const request = api
        .getAudio(documentId, segmentId)
        .then(({ blob, realModel: isReal }) => {
          const clip: Clip = { url: URL.createObjectURL(blob), realModel: isReal };
          if (disposedRef.current) {
            URL.revokeObjectURL(clip.url);
            return clip;
          }
          clipsRef.current.set(segmentId, clip);
          evict(clipsRef.current, segmentId, keptIds(segmentsRef.current, targetRef.current));
          return clip;
        })
        .finally(() => pendingRef.current.delete(segmentId));
      pendingRef.current.set(segmentId, request);
      return request;
    },
    [api, documentId],
  );

  // Keep the sentences ahead coming: in reading order, never more than
  // IN_FLIGHT requests out, and only while the reader wants to listen.
  const fillAhead = useCallback(() => {
    if (!wantRef.current || disposedRef.current) return;
    const list = segmentsRef.current;
    const from = targetRef.current;
    if (from < 0) return;
    for (let index = from + 1; index <= from + AHEAD && index < list.length; index += 1) {
      if (pendingRef.current.size >= IN_FLIGHT) return;
      const id = list[index]!.segment_id;
      if (clipsRef.current.has(id) || pendingRef.current.has(id)) continue;
      // A failure here is not the reader's problem; it becomes one only if
      // they reach that sentence, and then playback reports it.
      void clipFor(id)
        .catch(() => undefined)
        .then(() => fillAheadRef.current());
    }
  }, [clipFor]);
  useEffect(() => {
    fillAheadRef.current = fillAhead;
  });

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
      targetRef.current = index;
      wantRef.current = andPlay;
      try {
        const request = clipFor(segment.segment_id);
        // The sentences after it are asked for alongside it, not after it.
        fillAhead();
        const clip = await request;
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
    [clipFor, ensureAudio, reportError, fillAhead],
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
    wantRef.current = false; // and ask for nothing more ahead
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
      wantRef.current = false;
      setStatus("paused");
      const segment = segmentsRef.current[indexRef.current];
      if (segment) onPositionRef.current?.(segment.segment_id, audio.currentTime);
      return;
    }
    if (audio && currentId && status === "paused") {
      audio.playbackRate = rateRef.current;
      wantRef.current = true;
      fillAhead();
      void audio
        .play()
        .then(() => setStatus("playing"))
        .catch(reportError);
      return;
    }
    playAt(indexRef.current >= 0 ? indexRef.current : 0);
  }, [status, currentId, playAt, reportError, fillAhead]);

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
      if (finished) onHeardRef.current?.(finished.segment_id);
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

  // A new sentence, or a new page of sentences: top the window up.
  useEffect(() => {
    if (status === "playing") fillAhead();
  }, [status, currentId, segments, fillAhead]);

  // Leaving the page is a pause, and where they were is worth keeping.
  useEffect(() => {
    const clips = clipsRef.current;
    disposedRef.current = false;
    return () => {
      disposedRef.current = true;
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

/** The sentences worth keeping: the one playing, a few behind, and the window ahead. */
function keptIds(segments: PlayableSegment[], target: number): Set<string> {
  const kept = new Set<string>();
  for (let index = Math.max(0, target - 3); index <= target + AHEAD; index += 1) {
    const segment = segments[index];
    if (segment) kept.add(segment.segment_id);
  }
  return kept;
}

/** Drop the oldest clips beyond the limit, never one that is still wanted. */
function evict(clips: Map<string, Clip>, just: string, kept: Set<string>): void {
  for (const [key, value] of clips) {
    if (clips.size <= MAX_CACHED_CLIPS) return;
    if (key === just || kept.has(key)) continue;
    URL.revokeObjectURL(value.url);
    clips.delete(key);
  }
}
