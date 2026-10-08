// sine_stream.scd: a sine you control from a small window, streamed to the
// ESP32 speaker (tag 4, or firmware/audio_stream) at 16 kHz over Wi-Fi.
//
// The sound is written into a ring buffer on the server (buffer 900, write
// position on control bus 900); audio_stream.py reads it from there and sends
// it to the board in ~speaker. This script starts and stops audio_stream.py itself.
//
// 1. Click inside the parentheses below and press Cmd-Return
//    (or from a terminal: sclang supercollider/sine_stream.scd).
// 2. Closing the window stops the sound and the streamer.

(
~root = (thisProcess.nowExecutingPath ? "/Users/meatmini/Desktop/VIRIDITAS/supercollider/x").dirname.dirname;
~speaker = "uwb-tag4.local";   // or "uwb-speaker.local" for firmware/audio_stream
~bufnum = 900;
~posBus = 900;
s.options.hardwareBufferSize = 128;   // smaller blocks: steadier packets to the board

s.waitForBoot {
	SynthDef(\streamSine, { |freq = 440, amp = 0.2, on = 0, monitor = 0|
		var sig = SinOsc.ar(freq.lag(0.05)) * (amp * on).lag(0.05);
		var phase = Phasor.ar(0, 1, 0, BufFrames.kr(~bufnum));
		BufWr.ar(sig, ~bufnum, phase);
		Out.kr(~posBus, A2K.kr(phase));
		Out.ar(0, sig ! 2 * monitor.lag(0.05));   // also on the laptop's output
	}).add;
	~ring = Buffer.alloc(s, s.sampleRate.asInteger, 1, bufnum: ~bufnum);   // 1 s
	s.sync;

	~synth = Synth(\streamSine);
	~streamer = "cd % && exec python3 -u audio_stream.py --host %".format(~root.shellQuote, ~speaker.shellQuote).unixCmd(postOutput: true);

	{
		var w = Window("Sine → ESP32 speaker", Rect(200, 300, 420, 230)).front;
		var freqSpec = ControlSpec(40, 4000, \exp, 0, 440, "Hz");
		var volSpec = ControlSpec(-60, 0, \lin, 0.5, -14, "dB");
		var onButton, freqSlider, freqBox, volSlider, volBox, monitor, status;
		var setFreq = { |hz|
			hz = freqSpec.constrain(hz);
			~synth.set(\freq, hz);
			freqSlider.value = freqSpec.unmap(hz);
			freqBox.value = hz;
		};
		var setVol = { |db|
			db = volSpec.constrain(db);
			~synth.set(\amp, if(db <= -60) { 0 } { db.dbamp });
			volSlider.value = volSpec.unmap(db);
			volBox.value = db;
		};

		w.view.decorator = FlowLayout(w.bounds, 12@12, 8@10);

		onButton = Button(w, 396@40)
			.states_([["Off — click to play", Color.white, Color.grey(0.4)],
				["Playing — click to stop", Color.white, Color(0.1, 0.55, 0.3)]])
			.font_(Font.default.size_(15))
			.action_({ |b| ~synth.set(\on, b.value) });

		StaticText(w, 70@24).string_("Frequency");
		freqSlider = Slider(w, 230@24).action_({ |sl| setFreq.(freqSpec.map(sl.value)) });
		freqBox = NumberBox(w, 70@24).decimals_(1).action_({ |b| setFreq.(b.value) });
		StaticText(w, 20@24).string_("Hz");

		StaticText(w, 70@24).string_("Volume");
		volSlider = Slider(w, 230@24).action_({ |sl| setVol.(volSpec.map(sl.value)) });
		volBox = NumberBox(w, 70@24).decimals_(1).action_({ |b| setVol.(b.value) });
		StaticText(w, 20@24).string_("dB");

		monitor = CheckBox(w, 396@24, "Also play on this laptop")
			.action_({ |c| ~synth.set(\monitor, c.value.binaryValue) });

		status = StaticText(w, 396@48).string_("Starting the streamer…")
			.font_(Font.monospace.size_(11)).align_(\topLeft);

		setFreq.(440);
		setVol.(-14);

		// audio_stream.py reports itself and the board's stats here.
		OSCdef(\speakerStatus, { |msg|
			var line = msg[1].asString.replace("SPEAKER,", "board: ").replace("STREAM,", "").replace(",", "  ");
			{ if(status.isClosed.not) { status.string = line } }.defer;
		}, '/speaker');

		w.onClose = {
			OSCdef(\speakerStatus).free;
			~synth.free;
			~ring.free;
			if(~streamer.notNil) { "kill %".format(~streamer).unixCmd };
			"Stopped the sine and the streamer.".postln;
		};
	}.defer;
};
)
