// sine.scd: Tag 1's X position sets the pitch of a sine on the Clarett's outputs 1-4.
// X runs along the Anchor 1 to Anchor 2 side: ~lowHz on the Anchor 1 side,
// rising in even musical steps to ~highHz on the Anchor 2 side. Y is ignored.
//
// 1. Run osc_bridge.py (or simulate.py) so /tag1 arrives on port 9100.
// 2. Click inside the parentheses below and press Cmd-Return.
// 3. Cmd-. (period) stops the sound.

(
~port = 9100;      // /tag1 is on 9100, /tag2 on 9101, ... (9000+ is left for Unreal)
~lowHz = 220;      // Anchor 1 side
~highHz = 1440;    // Anchor 2 side
~volume = 0.05;    // about -26 dB: quiet

// The bridge sends every value as a number or "N/A"; parseJSON gives numbers as strings.
~num = { |v| if(v.isNil or: { v == "N/A" }) { nil } { v.asFloat } };

s.options.device = "Clarett+ 8Pre";
s.options.numOutputBusChannels = 4;

s.waitForBoot {
	SynthDef(\tagSine, { |freq = 220, amp = 0|
		var sig = SinOsc.ar(freq.lag(0.05)) * amp.lag(0.2);   // glide the pitch, fade in/out
		Out.ar(0, sig ! 4);
	}).add;
	s.sync;

	~synth = Synth(\tagSine, [\freq, ~lowHz]);
	~heard = 0;
	thisProcess.openUDPPort(~port);

	OSCdef(\tag1, { |msg|
		var x = ~num.(msg[1].asString.parseJSON["x"]);
		if(x.notNil) {
			~synth.set(\freq, x.clip(-1, 1).linexp(-1, 1, ~lowHz, ~highHz), \amp, ~volume);
			~heard = Main.elapsedTime;
		} {
			~synth.set(\amp, 0);   // tag offline
		};
	}, '/tag1', recvPort: ~port);

	// Fade out if the bridge stops sending.
	Routine {
		loop {
			if(Main.elapsedTime - ~heard > 1) { ~synth.set(\amp, 0) };
			0.25.wait;
		}
	}.play;

	"Listening for /tag1 on port %".format(~port).postln;
};
)
