// Speaker test for the MAX98357A I2S amp on a tag/anchor board.
// No UWB or Wi-Fi: flash this, listen, then flash the real firmware back.
//
// Wiring (Makerfabs ESP32 UWB DW3000):
//   BCLK -> IO26 (20-pin header, pin 13)
//   LRC  -> IO25 (20-pin header, pin 12)
//   DIN  -> IO13 (20-pin header, pin 7)
//   Vin  -> 5V   (12-pin header, pin 1)
//   GND  -> GND  (12-pin header, pin 2)
//   SD, GAIN unconnected (amp mixes L+R, 9 dB gain)
//
// Plays an original spooky '80s funk tune on a loop: a punchy E minor riff,
// a creeping chromatic line with a wobble, and a werewolf howl, then a pause.
// Serial monitor at 115200 baud: send + or - to change the volume.
#include <ESP_I2S.h>
#include <math.h>

const int PIN_BCLK = 26, PIN_LRC = 25, PIN_DIN = 13;
const int SAMPLE_RATE = 22050;
const int CHUNK = 256;

I2SClass i2s;
float volume = 0.3f;  // 0..1 of full scale
float phase = 0;      // sine phase, carried across notes so they join without clicks

// Declared here so the Arduino builder adds no prototypes of its own (it can
// insert them inside a function body, which breaks the build).
void readVolume();
void play(float from, float to, int ms, float wobble);
void setup();
void loop();

void readVolume() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '+') volume = min(1.0f, volume + 0.1f);
    if (c == '-') volume = max(0.0f, volume - 0.1f);
    if (c == '+' || c == '-') Serial.printf("SPEAKER,volume=%.1f\n", volume);
  }
}

// Plays a note for ms milliseconds, gliding from `from` to `to` Hz (equal for a
// plain note; 0 is silence). wobble is vibrato depth (0.01 = ±1%) at 6 Hz.
void play(float from, float to, int ms, float wobble) {
  const int frames = (long)SAMPLE_RATE * ms / 1000;
  const int fade = SAMPLE_RATE / 200;  // 5 ms ramps avoid clicks
  const float a = log2f(max(from, 1.0f)), b = log2f(max(to, 1.0f));
  int16_t buf[CHUNK * 2];
  float vib = 0;
  for (int i = 0; i < frames;) {
    readVolume();
    int n = min(CHUNK, frames - i);
    for (int j = 0; j < n; j++, i++) {
      const float t = i / (float)frames;
      const float env = from > 0 ? min(1.0f, min(i, frames - 1 - i) / (float)fade) : 0;
      vib += 2 * PI * 6 / SAMPLE_RATE;
      const float freq = exp2f(a + (b - a) * t + wobble * sinf(vib));
      phase += 2 * PI * freq / SAMPLE_RATE;
      if (phase > 2 * PI) phase -= 2 * PI;
      buf[2 * j] = buf[2 * j + 1] = (int16_t)(sinf(phase) * env * volume * 32767);
    }
    i2s.write((uint8_t *)buf, n * sizeof(int16_t) * 2);
  }
}

const float R = 0;  // rest
const float N_B4 = 494, N_D5 = 587, N_E5 = 659, N_Fs5 = 740, N_G5 = 784, N_A5 = 880, N_As5 = 932, N_B5 = 988, N_E6 = 1319;
const int STEP_MS = 250;  // one sixteenth-ish step at about 120 BPM

// {from Hz, to Hz, steps, wobble, gap}: gap = 1 makes the note short and punchy.
struct Note { float from, to; float steps, wobble; int gap; };
const Note TUNE[] = {
  // Riff, twice: punchy and syncopated.
  {N_E5, N_E5, 1, 0, 1}, {R, R, 1, 0, 0}, {N_E5, N_E5, 1, 0, 1}, {N_D5, N_D5, 1, 0, 1},
  {N_B4, N_B4, 1, 0, 1}, {R, R, 1, 0, 0}, {N_D5, N_D5, 1, 0, 1}, {N_E5, N_E5, 1, 0, 1},
  {N_G5, N_G5, 1, 0, 1}, {N_Fs5, N_Fs5, 1, 0, 1}, {N_E5, N_E5, 1, 0, 1}, {N_D5, N_D5, 1, 0, 1},
  {N_E5, N_E5, 3, 0.004f, 0}, {R, R, 1, 0, 0},
  {N_E5, N_E5, 1, 0, 1}, {R, R, 1, 0, 0}, {N_E5, N_E5, 1, 0, 1}, {N_D5, N_D5, 1, 0, 1},
  {N_B4, N_B4, 1, 0, 1}, {R, R, 1, 0, 0}, {N_D5, N_D5, 1, 0, 1}, {N_E5, N_E5, 1, 0, 1},
  {N_G5, N_G5, 1, 0, 1}, {N_A5, N_A5, 1, 0, 1}, {N_G5, N_G5, 1, 0, 1}, {N_Fs5, N_Fs5, 1, 0, 1},
  {N_E5, N_E5, 3, 0.004f, 0}, {R, R, 1, 0, 0},
  // Something creeping down the hall: slow chromatic steps with a wobble.
  {N_B5, N_B5, 2, 0.012f, 0}, {N_As5, N_As5, 2, 0.012f, 0}, {N_A5, N_A5, 2, 0.012f, 0},
  {N_G5 * 1.0595f, N_G5 * 1.0595f, 2, 0.012f, 0}, {N_G5, N_G5, 4, 0.016f, 0}, {R, R, 2, 0, 0},
  // The howl: swoop up, hold, and fall away.
  {N_B4, N_E6, 4, 0.006f, 0}, {N_E6, N_E6, 3, 0.02f, 0}, {N_E6, N_B4, 5, 0.01f, 0},
  {R, R, 8, 0, 0},
};

void setup() {
  Serial.begin(115200);
  i2s.setPins(PIN_BCLK, PIN_LRC, PIN_DIN);
  if (!i2s.begin(I2S_MODE_STD, SAMPLE_RATE, I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_STEREO)) {
    Serial.println("SPEAKER,error,i2s_begin_failed");
    while (true) delay(1000);
  }
  Serial.println("SPEAKER,ready,spooky funk  (+/- = volume)");
}

void loop() {
  Serial.println("SPEAKER,spooky_funk");
  for (const Note &note : TUNE) {
    const int ms = note.steps * STEP_MS;
    if (note.gap) {
      play(note.from, note.to, ms - 70, note.wobble);
      play(R, R, 70, 0);
    } else {
      play(note.from, note.to, ms, note.wobble);
    }
  }
}
