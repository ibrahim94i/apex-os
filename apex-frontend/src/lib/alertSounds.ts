export type AlertSoundType = "alert" | "warning" | "critical";

let audioCtx: AudioContext | null = null;

function getCtx(): AudioContext {
  if (!audioCtx) {
    audioCtx = new AudioContext();
  }
  return audioCtx;
}

function tone(
  ctx: AudioContext,
  freq: number,
  start: number,
  duration: number,
  gain = 0.15,
  type: OscillatorType = "sine"
) {
  const osc = ctx.createOscillator();
  const g = ctx.createGain();
  osc.type = type;
  osc.frequency.value = freq;
  g.gain.setValueAtTime(gain, start);
  g.gain.exponentialRampToValueAtTime(0.001, start + duration);
  osc.connect(g);
  g.connect(ctx.destination);
  osc.start(start);
  osc.stop(start + duration);
}

export async function playAlertSound(kind: AlertSoundType): Promise<void> {
  try {
    const ctx = getCtx();
    if (ctx.state === "suspended") {
      await ctx.resume();
    }
    const now = ctx.currentTime;
    if (kind === "critical") {
      tone(ctx, 880, now, 0.25, 0.2, "square");
      tone(ctx, 660, now + 0.28, 0.25, 0.2, "square");
      tone(ctx, 440, now + 0.56, 0.35, 0.18, "square");
    } else if (kind === "warning") {
      tone(ctx, 520, now, 0.2, 0.16);
      tone(ctx, 520, now + 0.28, 0.2, 0.16);
      tone(ctx, 520, now + 0.56, 0.2, 0.16);
    } else {
      tone(ctx, 740, now, 0.15, 0.12);
      tone(ctx, 988, now + 0.18, 0.2, 0.12);
    }
  } catch {
    /* audio unavailable */
  }
}
