// Four Tags FX
// All four XY players at once, in one window, each on its own VIRIDITAS tag's speaker:
//   Tag 1: kalimba       Echo (left / right)       + PitShift (up / down)            from kalimba-echo.scd
//   Tag 2: waveguideFlute SinOscFB (left / right)  + speed / grains (down / up)      from waveguideFlute-feedback.scd
//   Tag 3: apadMH        Greyhole (left / right)   + grains (up) / stutter (down)    from uwb-tag3-greyhole-grains.scd, apadMH-stutter.scd
//   Tag 4: vintageSine   Squiz (left / right)      + LFPulse (down / up)             from uwb-tag4-squiz-lfpulse.scd
// To start: click anywhere inside the big parentheses below and press Cmd-Return.
//
// Needs sc3-plugins (Greyhole is in DEINDUGens, Squiz in MCLDUGens): https://github.com/supercollider/sc3-plugins
// Copies of those two are in plugins/ here; on a Mac without sc3-plugins, copy
// them into ~/Library/Application Support/SuperCollider/Extensions (not if
// sc3-plugins is already there: two copies of a class won't compile).
// The four synths (SynthDefs/) and their patterns (pbind-demos/) come from
// SCLOrkSynths (SCLOrkSynths-LICENSE).
//
// The effects are the same as in each tag's own player (see those files for
// what every axis does); here each tag plays on its own private bus, so one
// tag's effects never touch another tag's sound:
//   tag's demo -> its effects (in order) -> a mixer (volume, laptop, ring buffer)
// - One pad with four numbered, coloured dots, one per tag. The pad is the
//   VIRIDITAS room: its proportions come from layout.json (the same anchor
//   layout uwb.py uses), Anchor 1 top-left, then clockwise. Each dot follows
//   its tag: /tagN from uwb.py (or osc_bridge.py) on port 9100 + N - 1, with
//   x, y from -1 to 1 across the anchors. A tag with no position ("N/A") is
//   dropped: its dot disappears from the pad and its sound is muted until it
//   reports again (meanwhile its effects hold for 3 s, then glide to the dry
//   middle, so it comes back dry after a long drop).
//   You can drag a dot to override its tag while you hold it.
//   The middle of the pad is dry and each effect grows towards the edge on
//   its side:
//     1 kalimba: echo to the right, PitShift downwards
//     2 flute:   SinOscFB to the right; above the middle slower, below grains
//     3 apad:    Greyhole to the right; above the middle grains, below stutter
//     4 sine:    Squiz to the left, LFPulse upwards
// - Each dot has its own random quarter, dot N in quarter N (1 top left,
//   2 top right, 3 bottom left, 4 bottom right; for 1 and 4 that's the quarter
//   their effects leave dry). There its effects wander to a new random setting
//   every 0.4-1.2 s, each tag on its own timing. How far they wander grows from
//   nothing on the quarter's edges to fully random in the corner, so crossing
//   into it never jumps.
//   The list beside the pad says what each dot's axes do and shows its settings.
//   Stacked dots: the top one is grabbed.
// - "Simulate people" (off by default) is for testing without anyone walking:
//   every dot whose tag has no UWB position glides smoothly to random places
//   as if someone were walking with it. Tags that are live still follow UWB.
// - Space or the Play button starts and stops all four together.
// - f: full screen: just the room, stretched edge to edge over the whole
//   screen, with the dots (no rows or buttons); f again goes back.
// - "C major" (off by default) moves every note to the nearest note of C major,
//   so the four tags fit together. The kalimba's PitShift still shifts after it.
// - "Play on this computer" (off by default) mixes all four on the laptop too.
// - Streaming works like four-tags-player.scd: ring buffers 900-903, write
//   positions on control buses 900-903, each read by its own audio_stream.py.
//   The single players use buffer 900 too, so don't stream from them at the same time.
// - VIRIDITAS's startUwb.sh starts this file (SOUND=1) and hands it the same
//   settings it gives uwb.py, as environment variables: VIRIDITAS_DIR (where
//   layout.json and audio_stream.py are), UWB_SC_PORT (the base port, 9100) and
//   FOUR_TAGS_STANDALONE=1 (stream to all four tags at once; closing the window
//   quits). Run from the IDE, the defaults below are used instead.
// - media/viriditas_day.wav loops forever on this computer's output from the
//   moment the window opens (not on the tags, and not affected by Play / Stop
//   or "Play on this computer"); closing the window stops it.
// - Mixer window (opens beside it; m closes / reopens it): a level meter for
//   the soundscape (viriditas_day.wav) and for each tag (what goes to its
//   speaker), with a volume fader under each. A dropped tag reads silent.

(
// this folder (VIRIDITAS/supercollider): the SynthDefs and pbind-demos it loads are here
var dir = thisProcess.nowExecutingPath !? { |p| p.dirname } ? "/Users/meatmini/Desktop/VIRIDITAS/supercollider";
var uwbPort = ("UWB_SC_PORT".getenv ? "9100").asInteger;   // /tag1 here, /tag2 on the next port, ...
~viriditas = "VIRIDITAS_DIR".getenv ? ~viriditas ? dir.dirname;
if("FOUR_TAGS_STANDALONE".getenv == "1") { ~fourTagsFXStandalone = true; ~fourTagsFXStreamOnStart = true };
s.options.memSize = 2 ** 18;   // Greyhole, Squiz and the echoes use long delay lines
s.options.hardwareBufferSize = 128;   // smaller blocks: steadier packets to the board

s.waitForBoot {
	var voices, kalimba, flute, apad, sine;
	var win, font, playButton, laptop = 0, sources, fxs, mixers;
	var cMajor = false, snap, snapAll, toCMajor;
	var playVoice, stopVoice, play, stop, startStream, stopStream;
	var pitShift;
	var pad, pos, order, drag, toPix, fromPix, setDot, applyDot, randomizers, padSize = 440, dotR = 13;
	var simulate = false, motion, padW, padH, room, tagXY, tagHeard, holdS = 3;
	var toPixIn, drawPad, full, fullView, toggleFull, refreshPads, keys;
	var winW, winH, colW = 470, rowStep = 110, contentH, bottomY;
	var dayBuf, daySynth, dayAmp = 1;
	var mixWin, meters, makeMixer, volSpec = ControlSpec(0, 2, \amp);

	[
		"SynthDefs/percussion/kalimba.scd", "pbind-demos/kalimba-demo.scd",
		"SynthDefs/winds/waveguideFlute.scd", "pbind-demos/waveguideFlute-demo.scd",
		"SynthDefs/pads/apadMH.scd", "pbind-demos/apadMH-demo.scd",
		"SynthDefs/misc/vintageSine.scd", "pbind-demos/vintageSine-demo.scd"
	].do { |f| (dir +/+ f).load };

	// ---------- tag 1: kalimba -> PitShift -> echo ----------

	// bitgraves' PitShift.ar as a function; shift is the pitch ratio (1 = none, 2 = octave up)
	pitShift = { |in, shift, mul = 1|
		var delayLength = 5024 / s.sampleRate;
		var halfLength = delayLength / 2;
		var sweep = Sweep.ar(Impulse.kr(0), 1.0 - shift);
		var env = EnvGen.ar(Env.triangle(delayLength), Impulse.ar(delayLength.reciprocal));
		var lines = DelayL.ar(in,
			maxdelaytime: delayLength,
			delaytime: Wrap.ar([sweep, sweep + halfLength], 0, delayLength),
			mul: [env, 1.0 - env] * mul
		);
		lines.sum
	};

	SynthDef(\ftPitShift, { |bus, amount = 0, ratioHi = 2|
		var dry = In.ar(bus, 2), a = amount.lag(0.15);
		var wet = dry.collect { |ch| pitShift.(ch, a.linexp(0, 1, 1, ratioHi)) };
		ReplaceOut.ar(bus, Limiter.ar(XFade2.ar(dry, wet, a.linlin(0, 1, -1, 1)), 0.95));
	}).add;

	SynthDef(\ftEcho, { |bus, amount = 0, width = 0.3, modFreq = 0.15, modAmount = 0.04|
		var dry = In.ar(bus, 2), a = amount.lag(0.15);
		var time = a.linexp(0, 1, 0.12, 0.45);
		var feedback = a.linlin(0, 1, 0.15, 0.85);
		var decay = a.linlin(0, 1, 0.4, 2);
		var lowcut = a.linexp(0, 1, 5000, 2500);
		var localIn = LocalIn.ar(2);
		var wet = 2.collect { |ch|
			var randScale = Rand(0.95, 1.0);
			var delayVal = (time * randScale * if(ch.even) { 1 + width } { 1 }).lag3(0.3);
			var phase = ch.linlin(0, 1, -8pi, 8pi);
			var mod = LFTri.kr(Rand(0.99, 1.0) * modFreq * randScale, phase)
			.linlin(-1, 1, (1 - modAmount) * delayVal, delayVal);
			var fb = (feedback * localIn[ch]).tanh;
			fb = DelayL.ar(fb, 0.2, Rand(0.1, 0.2));
			fb = LPF.ar(fb, Rand(0.99, 1.0) * lowcut);
			LeakDC.ar(AllpassC.ar(dry[ch] + fb, 2, mod, decay.lag3(0.3)))
		};
		LocalOut.ar(wet);
		ReplaceOut.ar(bus, Limiter.ar(XFade2.ar(dry, wet, a.linlin(0, 1, -1, 0.3)), 0.95));
	}).add;

	// ---------- tag 2: flute + SinOscFB voices -> mix -> grains ----------

	SynthDef(\ftFluteFBVoice, { |fbOut = 0, amountBus = 0, freq = 440, amp = 0.2, sustain = 0.2|
		var a = In.kr(amountBus).lag(0.15);
		var env = EnvGen.kr(Env.linen(0.06, sustain, 0.12), doneAction: 2);
		var vib = SinOsc.kr(5, 0, EnvGen.kr(Env([0, 0, 0.004], [0.15, 0.3])), 1);
		var sig = SinOscFB.ar(freq * vib, a.linlin(0, 1, 0, 1.5));
		sig = LPF.ar(sig, a.linexp(0, 1, 8000, 3000));
		Out.ar(fbOut, (sig * env * amp * 0.6) ! 2);
	}).add;

	SynthDef(\ftFluteFB, { |bus, amount = 0, fbIn = 0|
		var dry = In.ar(bus, 2), a = amount.lag(0.15);
		var wet = In.ar(fbIn, 2);
		ReplaceOut.ar(bus, Limiter.ar(XFade2.ar(dry, wet, a.linlin(0, 1, -1, 0.7)), 0.95));
	}).add;

	SynthDef(\ftFluteGrains, { |bus, amount = 0, buf = 0|
		var dry = In.ar(bus, 2), a = amount.lag(0.15);
		var frames = BufFrames.kr(buf);
		var writePos = Phasor.ar(0, 1, 0, frames);
		var density = a.linexp(0, 1, 6, 30);
		var durLo = 0.02, durHi = a.linexp(0, 1, 0.08, 0.5);
		var trig, dur, back, pos, wet, overlap;
		BufWr.ar(dry.sum * 0.5, buf, writePos);
		trig = Dust.ar(density);
		dur = TExpRand.ar(durLo, durHi, trig);
		back = TRand.ar(dur + 0.02, dur + a.linlin(0, 1, 0.1, 1.5), trig);
		pos = ((writePos - (back * SampleRate.ir)) / frames).wrap(0, 1);
		wet = GrainBuf.ar(2, trig, dur, buf, TRand.ar(0.99, 1.01, trig), pos, 2, TRand.ar(-0.8, 0.8, trig));
		overlap = density * (durHi - durLo) / (durHi / durLo).log;
		wet = wet * overlap.sqrt.reciprocal.clip(0.5, 3);
		ReplaceOut.ar(bus, Limiter.ar(XFade2.ar(dry, wet, a * 2 - 1), 0.95));
	}).add;

	// ---------- tag 3: apadMH -> stutter -> grains -> Greyhole ----------

	SynthDef(\ftApadGrains, { |bus, amount = 0, centerFreq = 500, octaves = 2, rqMin = 0.2, grainLo = 2, grainHi = 16, makeup = 6|
		var dry = In.ar(bus, 2), a = amount.lag(0.15);
		var grainFreq, gate, grainEnv, filterFreq, grains, delayed, wet;
		grainFreq = grainLo * ((grainHi / grainLo) ** a);
		gate = Impulse.kr(grainFreq);
		grainEnv = EnvGen.kr(Env.sine(1), gate, timeScale: 0.9 / grainFreq);
		filterFreq = centerFreq * (2 ** (LFNoise0.kr(grainFreq * 2) * octaves * (0.3 + (0.7 * a))));
		grains = BPF.ar(dry.sum * 0.5, filterFreq.clip(60, 12000), 1.2 - ((1.2 - rqMin) * a)) * grainEnv;
		delayed = DelayC.ar(grains, 0.5 / grainLo, 0.5 / grainFreq);
		wet = [grains, delayed] * (makeup + (8 * a)).dbamp;
		ReplaceOut.ar(bus, Limiter.ar(XFade2.ar(dry, wet, a * 2 - 1), 0.95));
	}).add;

	SynthDef(\ftApadGreyhole, { |bus, amount = 0, makeup = 0, glide = 1|
		var dry = In.ar(bus, 2), a = amount.lag(glide), wet;
		var moving, base, metal, metalAmt;
		moving = (Slope.kr(amount.lag(0.1)).abs * 4).clip(0, 1).lagud(0.1, 1.5);
		wet = Greyhole.ar(dry,
			delayTime: a.linexp(0, 1, 0.1, 2),
			damp: a.linlin(0, 1, 0.4, 0.15),
			size: a.linexp(0, 1, 0.5, 4),
			diff: a.linlin(0, 1, 0.5, 0.9),
			feedback: a.linlin(0, 1, 0.3, 0.95),
			modDepth: a.linexp(0, 1, 0.05, 0.6) + (moving * 0.6),
			modFreq: a.linexp(0, 1, 0.5, 2)
		);
		base = a.linexp(0, 1, 300, 1500);
		metal = wet.collect { |ch, i|
			Mix(CombC.ar(ch, 0.02, (base * [1, 2.76, 5.40, 8.93] * [1, 1.004][i]).reciprocal,
				a.linlin(0, 1, 0.6, 2.5) + (moving * 1.5), [0.5, 0.35, 0.25, 0.18]))
		} * (0.25 + (moving * 0.25));
		metal = metal + (metal * SinOsc.ar(base * 1.41) * a * 0.6);
		metalAmt = ((a * 0.6) + (moving * 0.8)).clip(0, 1);
		wet = XFade2.ar(wet, metal, metalAmt * 2 - 1) * (makeup - (6 * a)).dbamp;
		ReplaceOut.ar(bus, Limiter.ar(XFade2.ar(dry, wet, a.linlin(0, 1, -1, 0.6)), 0.95));
	}).add;

	// from apadMH-stutter.scd: a 95 BPM pulsing low-pass and a ghost high-pass from the pad's own loudness
	SynthDef(\ftApadStutter, { |bus, amount = 0, bpm = 95, lpMin = 120, hpMax = 1480, ghostGain = 3.5, fall = 0.2, openFrac = 0.25, makeup = 8|
		var dry = In.ar(bus, 2), sig = dry, a = amount.lag(0.15), beat = 60 / bpm;
		var wob, rate, pulse, lpFreq, env, ghost, hpFreq;
		wob = LFTri.kr(3 / beat, 2).lag(beat * 0.08);
		rate = 0.01 * (4000 ** (0.23 + (0.77 * (0.48 + (0.2 * a * (wob + 1)) + (0.2 * (1 - a))))));
		pulse = ((LFTri.kr(rate) * 0.5 + 0.5 - (1 - openFrac)) / openFrac).max(0).lag(0.01);
		lpFreq = 20000 * ((lpMin / 20000) ** (1 - pulse));
		env = Amplitude.kr(sig.sum * 0.5, 0.001, fall);
		ghost = (DelayN.kr(env, 1, beat / 4) * ghostGain).clip(0, 1);
		hpFreq = 100 * ((hpMax / 100) ** ghost);
		sig = LPF.ar(sig, lpFreq.clip(20, 20000));
		sig = HPF.ar(sig, hpFreq.clip(20, 20000));
		sig = sig * makeup.dbamp;
		ReplaceOut.ar(bus, Limiter.ar(XFade2.ar(dry, sig, a * 2 - 1), 0.95));
	}).add;

	// ---------- tag 4: vintageSine -> Squiz -> LFPulse ----------

	SynthDef(\ftSineSquiz, { |bus, amount = 0, ratioHi = 24, chunkHi = 6, makeup = 9|
		var dry = In.ar(bus, 2), a = amount.lag(0.15), wet;
		wet = Squiz.ar(dry,
			pitchratio: a.linexp(0, 1, 1, ratioHi),
			zcperchunk: a.linlin(0, 1, 1, chunkHi).round,
			memlen: 0.1
		) * (makeup * a).dbamp;
		ReplaceOut.ar(bus, Limiter.ar(XFade2.ar(dry, LeakDC.ar(wet), a.linlin(0, 1, -1, 0.8)), 0.95));
	}).add;

	SynthDef(\ftSinePulse, { |bus, amount = 0, squiz = 0, rateLo = 2, rateHi = 3|
		var dry = In.ar(bus, 2), a = amount.lag(0.15);
		var width = a.linlin(0, 1, 0.5, 0.25);
		var gate = LFPulse.ar(a.linexp(0, 1, rateLo, rateHi), 0, width).lag(0.002);
		var wet = dry * gate * width.reciprocal.sqrt;
		var depth = a * (1 - (0.7 * squiz.lag(0.15)));
		ReplaceOut.ar(bus, Limiter.ar(XFade2.ar(dry, wet, depth * 2 - 1), 0.95));
	}).add;

	// ---------- one per tag: volume, then to the laptop and into the tag's ring buffer ----------

	SynthDef(\ftMixer, { |in, bufnum = 900, posBus = 900, vol = 0.8, laptop = 1, id = 0|
		var sig = In.ar(in, 2) * vol.lag(0.1);
		var mono = Limiter.ar(sig.sum * 0.7, 0.9);
		var phase = Phasor.ar(0, 1, 0, BufFrames.kr(bufnum));
		SendPeakRMS.kr(mono, 20, 3, '/ftLevel', id);   // the mixer window's meter for this tag
		BufWr.ar(mono, bufnum, phase);
		Out.kr(posBus, A2K.kr(phase));
		Out.ar(0, sig * laptop.lag(0.05));
	}).add;

	// ---------- the day recording, looped forever on the laptop ----------

	SynthDef(\ftDayLoop, { |buf, amp = 1|
		var sig = PlayBuf.ar(2, buf, BufRateScale.kr(buf), loop: 1) * amp.lag(0.1);   // the file is 44.1 kHz, the server may not be
		SendPeakRMS.kr(sig, 20, 3, '/ftLevel', 4);   // the mixer window's soundscape meter
		Out.ar(0, sig);
	}).add;

	// ---------- the four tags ----------
	// each: what to call it, which board, volume (locked; 1 = 100%), where its dot starts,
	// a colour and a summary of its axes, how to start its effects, what the dot does, and its readout

	kalimba = (
		tag: "Tag 1", title: "Kalimba  ·  Echo + PitShift", host: "uwb-tag.local", vol: 0.9, color: Color(1, 0.65, 0.3), axes: "→ right: Echo     ↓ below middle: PitShift (up to an octave up)     ↖ top left: random",
		xDir: 1, yDir: -1, randQuad: [-1, 1],
		makeFx: { |v|
			v.pitFx = Synth.tail(v.fxGroup, \ftPitShift, [bus: v.bus]);
			v.echoFx = Synth.tail(v.fxGroup, \ftEcho, [bus: v.bus]);   // kalimba -> PitShift -> echo
		},
		setXY: { |v, x, y| v.echoFx.set(\amount, x); v.pitFx.set(\amount, y) },
		readout: { |v, x, y|
			[
				"Echo: %  ·  %\\%".format(
					case { x < 0.02 } { "Dry" } { x < 0.35 } { "Slapback" } { x < 0.7 } { "Echoes" } { "Canyon" },
					(x * 100).round.asInteger),
				if(y < 0.02) { "Pitch: no shift" } {
					"Pitch: +% semitones  ·  %\\%".format(y.linexp(0, 1, 1, 2).ratiomidi.round(0.1), (y * 100).round.asInteger)
				}
			]
		},
		demo: { |v| Pdef(\kalimba) }
	);

	flute = (
		tag: "Tag 2", title: "Flute  ·  SinOscFB + speed / grains", host: "uwb-tag2.local", vol: 0.9, color: Color(0.4, 0.85, 1), axes: "→ right: SinOscFB     ↑ above: slower   ↓ below: grains     ↗ top right: random", splitY: true,
		xDir: 1, randQuad: [1, 1],
		// up / down: middle = normal; top half slows to half speed, bottom half adds grains
		slowAmt: { |v, y| (y - 0.5).max(0) * 2 },
		grainAmt: { |v, y| (0.5 - y).max(0) * 2 },
		makeFx: { |v|
			v.fbBus = Bus.audio(s, 2);
			v.amountBus = Bus.control(s, 1).set(0);
			v.grainBuf = Buffer.alloc(s, s.sampleRate.asInteger * 2, 1);
			v.tempoClock = TempoClock(1);
			s.sync;
			v.fbFx = Synth.tail(v.fxGroup, \ftFluteFB, [bus: v.bus, fbIn: v.fbBus]);
			v.grainsFx = Synth.tail(v.fxGroup, \ftFluteGrains, [bus: v.bus, buf: v.grainBuf]);   // flute + SinOscFB -> grains
		},
		setXY: { |v, x, y|
			v.fbFx.set(\amount, x);
			v.amountBus.set(x);
			v.tempoClock.tempo = 2 ** v.slowAmt(y).neg;
			v.grainsFx.set(\amount, v.grainAmt(y));
		},
		readout: { |v, x, y|
			var g = v.grainAmt(y);
			[
				"%  ·  feedback %  ·  %\\%".format(
					case { x < 0.02 } { "Flute" } { x < 0.35 } { "Sine" } { x < 0.7 } { "Buzz" } { "Rasp" },
					(x * 1.5).round(0.01), (x * 100).round.asInteger),
				case
				{ y > 0.51 } { "Speed: %x".format((2 ** v.slowAmt(y).neg).round(0.01)) }
				{ y < 0.49 } {
					"Grains: %  ·  %\\%".format(
						case { g < 0.35 } { "A few grains" } { g < 0.7 } { "Grains" } { "Cloud" },
						(g * 100).round.asInteger)
				}
				{ "Normal speed, no grains" }
			]
		},
		// every note plays both the flute and a SinOscFB voice
		demo: { |v|
			Ppar([
				Pdef(\waveguideFlute),
				Pbindf(Pdef(\waveguideFlute), \instrument, \ftFluteFBVoice, \fbOut, v.fbBus, \amountBus, v.amountBus)
			])
		},
		freeExtra: { |v| v.fbBus.free; v.amountBus.free; v.grainBuf.free; v.tempoClock.stop }
	);

	apad = (
		tag: "Tag 3", title: "apadMH  ·  Greyhole + grains / stutter", host: "uwb-tag3.local", vol: 1.5, color: Color(0.8, 0.6, 1),
		axes: "→ right: Greyhole     ↑ above: grains   ↓ below: stutter     ↙ bottom left: random", splitY: true,
		xDir: 1, randQuad: [-1, -1],
		// up / down is split at the middle like the flute's: above = grains, below = stutter
		grainAmt: { |v, y| (y - 0.5).max(0) * 2 },
		stutterAmt: { |v, y| (0.5 - y).max(0) * 2 },
		makeFx: { |v|
			v.stutterFx = Synth.tail(v.fxGroup, \ftApadStutter, [bus: v.bus]);
			v.grainFx = Synth.tail(v.fxGroup, \ftApadGrains, [bus: v.bus]);
			v.greyholeFx = Synth.tail(v.fxGroup, \ftApadGreyhole, [bus: v.bus]);   // pad -> stutter -> grains -> Greyhole
		},
		setXY: { |v, x, y|
			v.greyholeFx.set(\amount, x);
			v.grainFx.set(\amount, v.grainAmt(y));
			v.stutterFx.set(\amount, v.stutterAmt(y));
		},
		readout: { |v, x, y|
			var g = v.grainAmt(y), st = v.stutterAmt(y);
			[
				"Greyhole: %  ·  %\\%".format(
					case { x < 0.02 } { "Dry" } { x < 0.3 } { "Slapback" } { x < 0.6 } { "Echoes" } { x < 0.85 } { "Cloud" } { "Black hole" },
					(x * 100).round.asInteger),
				case
				{ g > 0.02 } {
					"Grains: %  ·  %\\%".format(
						case { g < 0.35 } { "Slow grains" } { g < 0.7 } { "Grains" } { g < 0.98 } { "Fast grains" } { "Full scatter" },
						(g * 100).round.asInteger)
				}
				{ st > 0.02 } {
					"Stutter: %  ·  %\\%".format(
						case { st < 0.35 } { "Light pulse" } { st < 0.7 } { "Pulsing" } { st < 0.98 } { "Stutter" } { "Full patch" },
						(st * 100).round.asInteger)
				}
				{ "No grains, no stutter" }
			]
		},
		demo: { |v| Pdef(\apadMH) }
	);

	sine = (
		tag: "Tag 4", title: "vintageSine  ·  Squiz + LFPulse", host: "uwb-tag4.local", vol: 0.9, color: Color(0.55, 0.9, 0.5), axes: "← left: Squiz     ↑ above middle: LFPulse     ↘ bottom right: random",
		xDir: -1, yDir: 1, randQuad: [1, -1],
		makeFx: { |v|
			v.squizFx = Synth.tail(v.fxGroup, \ftSineSquiz, [bus: v.bus]);
			v.pulseFx = Synth.tail(v.fxGroup, \ftSinePulse, [bus: v.bus]);   // vintageSine -> Squiz -> LFPulse
		},
		setXY: { |v, x, y| v.squizFx.set(\amount, x); v.pulseFx.set(\amount, y, \squiz, x) },
		readout: { |v, x, y|
			[
				"Squiz: %  ·  %\\%".format(
					case { x < 0.02 } { "Dry" } { x < 0.3 } { "Squeezed" } { x < 0.6 } { "Chirping" } { x < 0.85 } { "Crushed" } { "Shattered" },
					(x * 100).round.asInteger),
				if(y < 0.02) { "LFPulse: off" } {
					"LFPulse: % pulses a second  ·  %\\%".format(y.linexp(0, 1, 2, 3).round(0.1), (y * 100).round.asInteger)
				}
			]
		},
		demo: { |v| Pdef(\vintageSine) }
	);

	voices = [kalimba, flute, apad, sine];
	voices.do { |v, i|
		v.buf = 900 + i;
		v.statusPort = 57200 + i;
		v.bus = Bus.audio(s, 2);
		v.ring = Buffer.alloc(s, s.sampleRate.asInteger, 1, bufnum: v.buf);   // 1 s
	};
	s.sync;

	// demo -> its effects -> its mixer, for every tag
	sources = Group.head(s);
	fxs = Group.after(sources);
	mixers = Group.after(fxs);
	voices.do { |v, i|
		v.fxGroup = Group.tail(fxs);
		v.makeFx;
		v.mixer = Synth(\ftMixer, [in: v.bus, bufnum: v.buf, posBus: v.buf, vol: 0, laptop: laptop, id: i], mixers);   // silent until its tag reports
		v[\hidden] = true;   // matches vol 0, so the first position (even before the first frame) turns it up
	};
	dayBuf = Buffer.read(s, dir +/+ "media/viriditas_day.wav");
	s.sync;
	daySynth = Synth.after(mixers, \ftDayLoop, [buf: dayBuf]);

	// nearest C major note below or on a MIDI note: C# -> C, Eb -> D, F# -> F, Ab -> G, Bb -> A
	snap = { |midi|
		var m = midi.round.asInteger;
		m - #[0, 1, 0, 1, 0, 0, 1, 0, 1, 0, 1, 0][m % 12]
	};
	snapAll = { |x| if(x.isSequenceableCollection) { x.collect(snapAll) } { snap.(x) } };
	toCMajor = { |ev|
		if(cMajor and: { ev.isRest.not }) {
			try {
				var freq = ev.use { ~freq.value };
				if(freq.notNil) { ev[\freq] = snapAll.(freq.cpsmidi).midicps };
			};
		};
		ev
	};

	stopVoice = { |v|
		v[\player] !? { v[\player].stop; v[\player] = nil };
		v[\group] !? { |g| s.makeBundle(s.latency, { g.free }); v[\group] = nil };
	};

	playVoice = { |v|
		stopVoice.(v);
		v[\group] = Group.head(sources);
		// the demo repeated forever; the short rest keeps a broken or empty demo from hanging
		v[\player] = Pn(Pseq([v.demo, Pbind(\type, \rest, \dur, Pn(0.5, 1))]), inf).collect(toCMajor)
		.play(v.tempoClock ? TempoClock.default, protoEvent: Event.default.copy.put(\group, v[\group]).put(\out, v.bus), quant: 0);
	};

	stop = {
		voices.do(stopVoice);
		playButton.value = 0;
	};

	play = {
		voices.do(playVoice);
		playButton.value = 1;
	};

	// audio_stream.py reports to its own port, so each panel shows its own board
	startStream = { |v|
		v.statusText.string = "Starting the streamer…";
		v.streamer = "cd % && exec python3 -u audio_stream.py --host % --scsynth 127.0.0.1:% --sclang % --buf % --bus %"
		.format(~viriditas.shellQuote, v.host.shellQuote, s.addr.port, v.statusPort, v.buf, v.buf)
		.unixCmd(postOutput: true);
	};

	stopStream = { |v|
		v.streamer !? { "kill %".format(v.streamer).unixCmd; v.streamer = nil };
		v.statusText.string = "Not streaming";
	};

	// --- window ---

	font = { |size = 14, bold = false| Font("Helvetica", size, bold) };

	// the pad is the room: A1 -> A2 across, A2 -> A3 down, from layout.json's
	// anchor positions (cm), fitted into padSize x padSize. No layout: a square.
	room = try {
		var anchors = File.readAllString(~viriditas +/+ "layout.json").parseJSON["anchors"];
		var p = ["1", "3", "4"].collect { |k| anchors[k].collect(_.asFloat) };
		[(p[1] - p[0]).squared.sum.sqrt, (p[2] - p[1]).squared.sum.sqrt]
	};
	if(room.isNil or: { room.includes(0) }) { "Four Tags FX: no layout.json, using a square pad".warn; room = [1, 1] };
	padW = (padSize * room[0] / room.maxItem).round;
	padH = (padSize * room[1] / room.maxItem).round;

	// the window: the pad (as wide as the room needs), the tags' rows beside it,
	// the checkboxes below
	contentH = max(padH, 4 * rowStep - 6);
	winW = 16 + padW + 14 + colW + 12;
	bottomY = 44 + contentH + 10;
	winH = bottomY + 34;
	win = Window("Four Tags FX", Rect(20, 20, winW, winH), resizable: false);
	win.background = Color.gray(0.13);

	StaticText(win, Rect(16, 6, 140, 28))
	.string_("Four Tags FX").font_(font.(18, true)).stringColor_(Color.white);
	StaticText(win, Rect(150, 11, winW - 260, 20))
	.string_("dots follow the UWB tags (/tagN, port %+) · drag to override · space play/stop · f full screen".format(uwbPort))
	.font_(font.(11)).stringColor_(Color.gray(0.65));

	playButton = Button(win, Rect(winW - 96, 8, 84, 26))
	.canFocus_(false)
	.font_(font.(13, true))
	.states_([["Play", Color.black, Color(0.6, 0.9, 0.6)], ["Stop", Color.white, Color(0.85, 0.35, 0.3)]])
	.action_({ |b| if(b.value == 1) { play.() } { stop.() } });

	// --- one pad, four dots: each dot moves its own tag's two effects ---

	// every dot starts in the dry middle until its tag reports
	pos = voices.collect { [0.5, 0.5] };
	order = (0..3);   // drawing order: the last one is on top and gets grabbed first

	// pad coordinates <-> 0..1 (the dots stay fully inside the pad)
	// on a w x h view, with dots of radius r kept fully inside
	toPixIn = { |xy, w, h, r| Point(r + (xy[0] * (w - (2 * r))), r + ((1 - xy[1]) * (h - (2 * r)))) };
	toPix = { |xy| toPixIn.(xy, padW, padH, dotR) };
	fromPix = { |x, y| [(x - dotR) / (padW - (2 * dotR)), 1 - ((y - dotR) / (padH - (2 * dotR)))].clip(0, 1) };

	// the middle of the pad is dry: each effect starts at the middle and is full
	// at the edge on its side (xDir / yDir: 1 = right / up, -1 = left / down).
	// The flute's and the apad's up / down are split at the middle instead.
	// Each tag has its own random quarter (randQuad: which side of the middle in
	// x and y), dot N in quarter N: 1 top left, 2 top right, 3 bottom left,
	// 4 bottom right. The deeper into its corner, the further the tag's effects
	// wander from where the dot is towards a random setting (0 on the quarter's
	// edges, fully random in the corner)
	applyDot = { |i|
		var v = voices[i], xy = pos[i], target = v[\randTarget] ? [0, 0];
		var dx = xy[0] - 0.5, dy = xy[1] - 0.5;
		var x = (dx * v.xDir).max(0) * 2;
		var y = if(v[\splitY] == true) { xy[1] } { (dy * v.yDir).max(0) * 2 };
		var r = min(dx * v.randQuad[0], dy * v.randQuad[1]).max(0) * 2;
		v[\randDepth] = r;
		x = x + (r * (target[0] - x));
		y = y + (r * (target[1] - y));
		v.setXY(x, y);
		v[\showFn].(x, y);
	};

	setDot = { |i, xy|
		pos[i] = xy;
		applyDot.(i);
		refreshPads.();
	};

	// each tag picks a new random setting every 0.4-1.2 s, on its own timing
	randomizers = voices.collect { |v, i|
		v[\randTarget] = [1.0.rand, 1.0.rand];
		Routine {
			loop {
				rrand(0.4, 1.2).wait;
				v[\randTarget] = [1.0.rand, 1.0.rand];
				if((v[\randDepth] ? 0) > 0) { applyDot.(i) };
			}
		}.play(AppClock)
	};

	// the room's outline, centred down the side of the rows
	// the room on a w x h view: grid, random quarters, anchors and the dots
	// (radius r); big scales the lines and labels. Used by the pad and by the
	// full-screen view.
	drawPad = { |w, h, r, big = 1|
		Pen.strokeColor = Color.gray(0.3);
		Pen.width = big;
		[0.25, 0.5, 0.75].do { |f|
			Pen.line(Point(w * f, 0), Point(w * f, h));
			Pen.line(Point(0, h * f), Point(w, h * f));
		};
		Pen.stroke;
		Pen.strokeColor = Color.gray(0.5);
		Pen.width = 2 * big;
		Pen.line(Point(w / 2, 0), Point(w / 2, h));
		Pen.line(Point(0, h / 2), Point(w, h / 2));
		Pen.stroke;
		voices.do { |v, i|
			var q = Rect(if(v.randQuad[0] < 0) { 0 } { w / 2 }, if(v.randQuad[1] > 0) { 0 } { h / 2 }, w / 2, h / 2);
			Pen.stringCenteredIn("% random".format(i + 1), q, font.(16 * big, true), v.color.copy.alpha_(0.3));
		};
		// the anchors in their corners, Anchor 1 top-left, then clockwise
		[["A1", 4, 3], ["A2", w - (22 * big), 3], ["A3", w - (22 * big), h - (17 * big)], ["A4", 4, h - (17 * big)]].do { |a|
			Pen.stringAtPoint(a[0], Point(a[1], a[2]), font.(11 * big, true), Color.gray(0.75));
		};
		// a tag that has dropped out isn't shown
		order.reject { |i| voices[i][\hidden] == true }.do { |i|
			var dot = Rect.aboutPoint(toPixIn.(pos[i], w, h, r), r, r);
			Pen.fillColor = voices[i].color;
			Pen.addOval(dot);
			Pen.fill;
			Pen.strokeColor = Color.black.alpha_(0.6);
			Pen.width = 2 * big;
			Pen.addOval(dot);
			Pen.stroke;
			Pen.stringCenteredIn((i + 1).asString, dot, font.(12 * big, true), Color.black);
		};
	};

	pad = UserView(win, Rect(16, 44 + ((contentH - padH) / 2), padW, padH))
	.background_(Color.gray(0.2))
	.drawFunc_({ drawPad.(padW, padH, dotR) })
	.mouseDownAction_({ |u, x, y|
		// the topmost dot under the mouse
		drag = order.reverse.detect { |i| voices[i][\hidden] != true and: { (toPix.(pos[i]) - Point(x, y)).rho <= (dotR + 4) } };
		drag !? { order.remove(drag); order = order.add(drag); setDot.(drag, fromPix.(x, y)) };
	})
	.mouseMoveAction_({ |u, x, y| drag !? { setDot.(drag, fromPix.(x, y)) } })
	.mouseUpAction_({ drag = nil });
	refreshPads = { pad.refresh; fullView !? { fullView.refresh } };   // and the full-screen view (f)

	// --- one row per tag beside the pad: its effects, readout and stream button ---

	voices.do { |v, i|
		var px = 16 + padW + 14, py = 44 + (i * rowStep), w = colW;
		var line1, line2;

		UserView(win, Rect(px, py, w, rowStep - 6)).background_(Color.gray(0.17));
		UserView(win, Rect(px + 8, py + 5, 18, 18)).drawFunc_({
			Pen.fillColor = v.color;
			Pen.addOval(Rect(1, 1, 16, 16));
			Pen.fill;
			Pen.stringCenteredIn((i + 1).asString, Rect(1, 1, 16, 16), font.(10, true), Color.black);
		});
		StaticText(win, Rect(px + 32, py + 3, w - 190, 22))
		.string_(v.tag ++ "  ·  " ++ v.title).font_(font.(13, true)).stringColor_(Color.white);
		v.uwbText = StaticText(win, Rect(px + w - 158, py + 4, 150, 20))
		.align_(\right).font_(font.(11, true));
		StaticText(win, Rect(px + 10, py + 24, w - 20, 16))
		.string_(v.axes).font_(font.(10)).stringColor_(Color.gray(0.65));
		line1 = StaticText(win, Rect(px + 10, py + 40, w - 20, 18))
		.font_(font.(12, true)).stringColor_(Color(1, 0.8, 0.4));
		line2 = StaticText(win, Rect(px + 10, py + 57, w - 20, 18))
		.font_(font.(11, true)).stringColor_(Color(0.6, 0.85, 1));

		v[\showFn] = { |x, y|
			var lines = v.readout(x, y);
			line1.string = lines[0];
			line2.string = lines[1];
		};

		v.streamButton = Button(win, Rect(px + 10, py + 78, 160, 20))
		.canFocus_(false)
		.states_([
			["Stream to " ++ v.host.split($.).first],
			["Streaming. Click to stop", Color.white, Color(0.1, 0.55, 0.3)]
		])
		.action_({ |b| if(b.value == 1) { startStream.(v) } { stopStream.(v) } });
		v.statusText = StaticText(win, Rect(px + 178, py + 76, w - 186, 26))
		.string_("Not streaming")
		.font_(Font.monospace.size_(8)).stringColor_(Color.gray(0.6));

		thisProcess.openUDPPort(v.statusPort);
		OSCdef(("fourTagsFXStatus" ++ i).asSymbol, { |msg|
			var line = msg[1].asString.replace("SPEAKER,", "board: ").replace("STREAM,", "").replace(",", "  ");
			{ if(v.statusText.isClosed.not and: { v.streamer.notNil }) { v.statusText.string = line } }.defer;
		}, '/speaker', recvPort: v.statusPort);
	};

	voices.do { |v, i| setDot.(i, pos[i]) };

	// --- UWB: each tag's position from uwb.py / osc_bridge.py ---
	// /tagN arrives on uwbPort + N - 1 as a JSON string; x and y run -1 to 1
	// across the anchors (A1 (-1, 1) top-left, A3 (1, -1) bottom-right), the
	// same corners as the pad, and are "N/A" while the tag has no position.
	tagXY = nil ! 4;
	tagHeard = -inf ! 4;   // when each tag last had a position
	voices.do { |v, i|
		if(thisProcess.openUDPPort(uwbPort + i).not) { "Four Tags FX: can't listen on port %".format(uwbPort + i).warn };
		OSCdef(("fourTagsFXUwb" ++ i).asSymbol, { |msg|
			var data = try { msg[1].asString.parseJSON }, x, y;
			if(data.isKindOf(Dictionary)) { x = data["x"]; y = data["y"] };
			if(x.notNil and: { y.notNil } and: { x != "N/A" } and: { y != "N/A" }) {
				tagXY[i] = [x.asFloat + 1 / 2, y.asFloat + 1 / 2].clip(0, 1);
				tagHeard[i] = Main.elapsedTime;
			};
		}, ("/tag" ++ (i + 1)).asSymbol, recvPort: uwbPort + i);
	};

	// Every frame, each dot either
	// - follows its tag (live: a position in the last 0.6 s; the bridge sends
	//   at least twice a second), with a light glide over its updates,
	// - is simulated, if "Simulate people" is on and its tag isn't live: it
	//   heads for a random waypoint through two glides (a goal that eases
	//   towards the waypoint, and the dot easing after the goal), so it speeds
	//   up and slows down smoothly instead of jumping,
	// - holds where it is for holdS after its tag's last position,
	// - or glides back to the middle, where its effects are dry.
	// A dot being dragged is left alone.
	motion = Routine {
		var dt = 1/30;
		var way = voices.collect { [1.0.rand, 1.0.rand] }, goal = pos.collect(_.copy);
		var shown = nil ! 4;
		loop {
			var now = Main.elapsedTime, moved = false;
			voices.do { |v, i|
				var age = now - tagHeard[i], to, rate, state;
				case
				{ drag == i } { state = \dragged }
				{ age < 0.6 } { state = \live; to = tagXY[i]; rate = 12 }
				{ simulate } {
					state = \simulated;
					if(((way[i] - goal[i]).abs.sum < 0.15) or: { 0.003.coin }) { way[i] = [1.0.rand, 1.0.rand] };
					goal[i] = goal[i] + ((way[i] - goal[i]) * 0.35 * dt);
					to = goal[i]; rate = 1.2;
				}
				{ age < holdS } { state = \held }
				{ state = \lost; to = [0.5, 0.5]; rate = 1.5 };
				if(state != \simulated) { goal[i] = pos[i].copy };
				// a tag that has dropped out (holding, or gone dry) is taken off the pad
				// and silenced (on its speaker and the laptop); it's back when it reports
				if(((state == \held) or: { state == \lost }) != (v[\hidden] == true)) {
					v[\hidden] = (state == \held) or: { state == \lost };
					v.mixer.set(\vol, if(v[\hidden]) { 0 } { v.vol });
					moved = true;
				};
				if(to.notNil and: { (to - pos[i]).abs.sum > 0.0005 }) {
					pos[i] = pos[i] + ((to - pos[i]) * min(1, rate * dt));
					applyDot.(i);
					moved = true;
				};
				if(state != shown[i]) {
					shown[i] = state;
					v.uwbText.string = (live: "UWB live", held: "dropped · holding", lost: "dropped · dry",
						simulated: "no UWB · simulated", dragged: "dragging")[state];
					v.uwbText.stringColor = (live: Color(0.45, 0.9, 0.5), held: Color(1, 0.8, 0.3),
						lost: Color(0.95, 0.45, 0.4), simulated: Color(0.6, 0.85, 1), dragged: Color.white)[state];
				};
			};
			if(moved) { refreshPads.() };
			dt.wait;
		}
	}.play(AppClock);

	CheckBox(win, Rect(16, bottomY, 22, 22))
	.canFocus_(false)
	.value_(laptop == 1)
	.action_({ |c| laptop = c.value.binaryValue; voices.do { |v| v.mixer.set(\laptop, laptop) } });
	StaticText(win, Rect(40, bottomY, 150, 22)).string_("Play on this computer").font_(font.(12)).stringColor_(Color.gray(0.8));

	CheckBox(win, Rect(196, bottomY, 22, 22))
	.canFocus_(false)
	.value_(cMajor)
	.action_({ |c| cMajor = c.value });
	StaticText(win, Rect(220, bottomY, 70, 22)).string_("C major").font_(font.(12)).stringColor_(Color.gray(0.8));

	CheckBox(win, Rect(296, bottomY, 22, 22))
	.canFocus_(false)
	.value_(simulate)
	.action_({ |c| simulate = c.value });
	StaticText(win, Rect(320, bottomY, 130, 22)).string_("Simulate people").font_(font.(12)).stringColor_(Color.gray(0.8));

	Button(win, Rect(winW - 142, bottomY - 1, 130, 24))
	.canFocus_(false)
	.states_([["Stream all four"]])
	.action_({ voices.do { |v| if(v.streamButton.value == 0) { v.streamButton.valueAction = 1 } } });

	// full screen (f): only the room, stretched edge to edge over the whole
	// screen, with its dots; f again (or space for play/stop) works there too
	toggleFull = {
		if(full.notNil) { full.close } {
			full = Window("Four Tags FX", Window.screenBounds, resizable: false, border: false);
			full.background = Color.gray(0.2);
			fullView = UserView(full, full.view.bounds).resize_(5).canFocus_(true)
			.drawFunc_({ |u| drawPad.(u.bounds.width, u.bounds.height, dotR * 3, 3) });
			full.view.keyDownAction = keys;
			fullView.keyDownAction = keys;
			full.onClose = { full = nil; fullView = nil };
			full.front;
			full.fullScreen;
			fullView.focus;
		};
	};

	// --- mixer window: a meter and a volume fader for the soundscape and each tag ---
	// meters 0-3 are the tags (what goes to their speakers), 4 the soundscape;
	// they read -60 to 0 dB (RMS bar, peak line)
	meters = nil ! 5;
	OSCdef(\fourTagsFXLevel, { |msg|
		var id = msg[2].asInteger, vals = msg[3..];
		var peak = vals[0, 2..].maxItem, rms = vals[1, 3..].maxItem;
		{
			meters[id] !? { |m|
				if(m[0].isClosed.not) {
					m[0].value = rms.ampdb.linlin(-60, 0, 0, 1);
					m[0].peakLevel = peak.ampdb.linlin(-60, 0, 0, 1);
					m[1].string = if(peak < 0.001) { "-inf" } { peak.ampdb.round(0.1).asString };
				}
			}
		}.defer;
	}, '/ftLevel', s.addr);

	makeMixer = {
		var stripW = 92, h = 400;
		var strips = voices.collect { |v, i| [v.tag, v.color, v.vol, { |a|
			v.vol = a;
			if(v[\hidden] != true) { v.mixer.set(\vol, a) };   // a dropped tag stays silent until it's back
		}, i] } ++ [["Soundscape", Color.gray(0.85), dayAmp, { |a| dayAmp = a; daySynth.set(\amp, a) }, 4]];
		mixWin = Window("Mixer", Rect(20 + winW + 10, 20, 12 + (stripW * strips.size), h), resizable: false);
		mixWin.background = Color.gray(0.13);
		strips.do { |st, k|
			var x = 6 + (k * stripW), meter, peakText, fader, volText;
			var showVol = { |a| volText.string = if(a < 0.001) { "-inf dB" } { "% dB".format(a.ampdb.round(0.1)) } };
			UserView(mixWin, Rect(x, 6, stripW - 6, h - 12)).background_(Color.gray(0.17));
			StaticText(mixWin, Rect(x, 10, stripW - 6, 20)).align_(\center)
			.string_(st[0]).font_(font.(12, true)).stringColor_(st[1]);
			meter = LevelIndicator(mixWin, Rect(x + ((stripW - 6 - 24) / 2), 34, 24, 200))
			.drawsPeak_(true).warning_(0.9).critical_(0.95)   // yellow from -6 dB, red from -3 dB
			.numTicks_(13).numMajorTicks_(4);
			peakText = StaticText(mixWin, Rect(x, 238, stripW - 6, 16)).align_(\center)
			.string_("-inf").font_(Font.monospace.size_(10)).stringColor_(Color.gray(0.75));
			fader = Slider(mixWin, Rect(x + ((stripW - 6 - 22) / 2), 262, 22, 100))
			.canFocus_(false)
			.value_(volSpec.unmap(st[2]))
			.action_({ |sl| var a = volSpec.map(sl.value); st[3].(a); showVol.(a) });
			volText = StaticText(mixWin, Rect(x, 366, stripW - 6, 16)).align_(\center)
			.font_(font.(11, true)).stringColor_(Color(1, 0.8, 0.4));
			showVol.(st[2]);
			meters[st[4]] = [meter, peakText];
		};
		mixWin.view.keyDownAction = keys;
		mixWin.onClose = { mixWin = nil; meters = nil ! 5 };
		mixWin.front;
	};

	keys = { |view, char|
		case
		{ char == $  } { playButton.valueAction = 1 - playButton.value; true }
		{ (char == $f) or: { char == $F } } { toggleFull.(); true }
		{ (char == $m) or: { char == $M } } { if(mixWin.notNil) { mixWin.close } { makeMixer.() }; true }
		{ nil }
	};
	win.view.keyDownAction = keys;

	win.onClose = {
		full !? { full.close };
		mixWin !? { mixWin.close };
		OSCdef(\fourTagsFXLevel).free;
		randomizers.do(_.stop);
		motion.stop;
		stop.();
		voices.do { |v, i|
			stopStream.(v);
			v.fxGroup.free;
			v.mixer.free;
			v.ring.free;
			v.bus.free;
			v.freeExtra;
			OSCdef(("fourTagsFXStatus" ++ i).asSymbol).free;
			OSCdef(("fourTagsFXUwb" ++ i).asSymbol).free;
		};
		daySynth.free;
		dayBuf.free;
		mixers.free;
		fxs.free;
		sources.free;
		if(~fourTagsFXStandalone == true) { s.quit; AppClock.sched(0.5, { 0.exit }) };
	};

	win.front;
	makeMixer.();
	if(~fourTagsFXStreamOnStart == true) { voices.do { |v| v.streamButton.valueAction = 1 } };
	playButton.valueAction = 1;
};
)
