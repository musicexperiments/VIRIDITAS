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
// Plays Happy Birthday on a loop, with a 2 s pause between repeats.
// Serial monitor at 115200 baud: send + or - to change the volume.
#include <ESP_I2S.h>
#include <math.h>

const int PIN_BCLK = 26, PIN_LRC = 25, PIN_DIN = 13;
const int SAMPLE_RATE = 22050;
const int CHUNK = 256;

I2SClass i2s;
float volume = 1.0f;  // 0..1 of full scale

// Plays freq Hz for ms milliseconds. freq = 0 is silence.
void play(float freq, int ms) {
  const int frames = (long)SAMPLE_RATE * ms / 1000;
  const int fade = SAMPLE_RATE / 200;  // 5 ms ramps avoid clicks
  int16_t buf[CHUNK * 2];
  float phase = 0;
  for (int i = 0; i < frames;) {
    int n = min(CHUNK, frames - i);
    for (int j = 0; j < n; j++, i++) {
      float env = min(1.0f, min(i, frames - 1 - i) / (float)fade);
      int16_t s = (int16_t)(sinf(phase) * env * volume * 32767);
      phase += 2 * PI * freq / SAMPLE_RATE;
      if (phase > 2 * PI) phase -= 2 * PI;
      buf[2 * j] = buf[2 * j + 1] = s;  // same sample on L and R
    }
    i2s.write((uint8_t *)buf, n * sizeof(int16_t) * 2);
  }
}

// Happy Birthday in C, 3/4 time: {Hz, beats}.
const float N_G4 = 392, N_A4 = 440, N_B4 = 494, N_C5 = 523, N_D5 = 587, N_E5 = 659, N_F5 = 698, N_G5 = 784;
const float SONG[][2] = {
  {N_G4, .75}, {N_G4, .25}, {N_A4, 1}, {N_G4, 1}, {N_C5, 1}, {N_B4, 2},
  {N_G4, .75}, {N_G4, .25}, {N_A4, 1}, {N_G4, 1}, {N_D5, 1}, {N_C5, 2},
  {N_G4, .75}, {N_G4, .25}, {N_G5, 1}, {N_E5, 1}, {N_C5, 1}, {N_B4, 1}, {N_A4, 2},
  {N_F5, .75}, {N_F5, .25}, {N_E5, 1}, {N_C5, 1}, {N_D5, 1}, {N_C5, 3},
};
const int BEAT_MS = 400, GAP_MS = 40;  // short gap so repeated notes are distinct

void setup() {
  Serial.begin(115200);
  i2s.setPins(PIN_BCLK, PIN_LRC, PIN_DIN);
  if (!i2s.begin(I2S_MODE_STD, SAMPLE_RATE, I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_STEREO)) {
    Serial.println("SPEAKER,error,i2s_begin_failed");
    while (true) delay(1000);
  }
  Serial.println("SPEAKER,ready,happy birthday  (+/- = volume)");
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '+') volume = min(1.0f, volume + 0.1f);
    if (c == '-') volume = max(0.0f, volume - 0.1f);
    if (c == '+' || c == '-') Serial.printf("SPEAKER,volume=%.1f\n", volume);
  }
  Serial.println("SPEAKER,happy_birthday");
  for (auto &note : SONG) {
    play(note[0], note[1] * BEAT_MS - GAP_MS);
    play(0, GAP_MS);
  }
  play(0, 2000);
}
