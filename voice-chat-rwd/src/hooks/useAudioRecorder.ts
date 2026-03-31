import { useState, useRef, useCallback } from 'react';

const TIMESLICE_MS = 250;

export function useAudioRecorder() {
  const [isRecording, setIsRecording] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const mimeTypeRef = useRef<string | null>(null);
  const recordingStartedAtRef = useRef<number>(0);

  const resolveMimeType = () => {
    if (typeof MediaRecorder === 'undefined' || !MediaRecorder.isTypeSupported) return null;
    const candidates = [
      'audio/webm;codecs=opus',
      'audio/webm',
      'audio/ogg;codecs=opus',
      'audio/ogg',
      'audio/mp4',
      'audio/mpeg'
    ];
    return candidates.find((type) => MediaRecorder.isTypeSupported(type)) || null;
  };

  const startRecording = useCallback(async (): Promise<boolean> => {
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error("此瀏覽器不支援麥克風錄音");
      }
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const resolvedMimeType = resolveMimeType();
      mediaRecorderRef.current = resolvedMimeType
        ? new MediaRecorder(stream, { mimeType: resolvedMimeType })
        : new MediaRecorder(stream);
      mimeTypeRef.current = resolvedMimeType || mediaRecorderRef.current.mimeType || null;
      chunksRef.current = [];

      mediaRecorderRef.current.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recordingStartedAtRef.current = Date.now();
      mediaRecorderRef.current.start(TIMESLICE_MS);
      setIsRecording(true);
      return true;
    } catch (err) {
      console.error("Error accessing microphone:", err);
      return false;
    }
  }, []);

  const stopRecording = useCallback((): Promise<{ blob: Blob | null; durationMs: number }> => {
    return new Promise((resolve) => {
      const durationMs = Date.now() - recordingStartedAtRef.current;
      if (!mediaRecorderRef.current || mediaRecorderRef.current.state === 'inactive') {
        resolve({ blob: null, durationMs });
        return;
      }

      mediaRecorderRef.current.onstop = () => {
        const blobType = mimeTypeRef.current || 'audio/webm';
        const blob = new Blob(chunksRef.current, { type: blobType });
        chunksRef.current = [];
        setIsRecording(false);
        streamRef.current = null;
        mimeTypeRef.current = null;
        resolve({ blob: blob.size > 0 ? blob : null, durationMs });
      };

      mediaRecorderRef.current.stop();
      mediaRecorderRef.current.stream.getTracks().forEach(track => track.stop());
    });
  }, []);

  const getStream = useCallback(() => streamRef.current, []);

  return { isRecording, startRecording, stopRecording, getStream };
}
