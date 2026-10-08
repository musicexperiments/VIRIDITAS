#pragma once
// Network speaker: plays 16 kHz mono audio streamed over UDP from audio_stream.py
// on a MAX98357A I2S amp. Used by firmware/audio_stream (speaker only) and by any
// board that defines AUDIO_STREAM before including ranging.h (UWB plus speaker).
//
// Wiring (Makerfabs ESP32 UWB DW3000; clear of the DW3000's pins):
//   BCLK -> IO26 (20-pin header, pin 13)
//   LRC  -> IO25 (20-pin header, pin 12)
//   DIN  -> IO13 (20-pin header, pin 7)
//   Vin  -> 5V   (12-pin header, pin 1)
//   GND  -> GND  (12-pin header, pin 2)
//   SD, GAIN unconnected (amp mixes L+R, 9 dB gain)
//
// Listens on UDP 4220. Each packet holds 10 ms of audio plus a copy of the
// previous 10 ms, so one lost packet loses nothing. A jitter buffer of about
// 60 ms rides out Wi-Fi bursts; a gap fades to silence instead of clicking; and
// a sample is dropped or repeated now and then to follow the sender's clock.
// Once a second the board sends its stats back to the sender (and to Serial).
// Both tasks run on core 0 with Wi-Fi, leaving core 1 to the caller (ranging).
#include <Arduino.h>
#include <WiFi.h>
#include <driver/i2s_std.h>
#include <lwip/sockets.h>

namespace AudioStream {

const int PIN_BCLK = 26, PIN_LRC = 25, PIN_DIN = 13;
const int PORT = 4220;
const int SAMPLE_RATE = 16000;
const int FRAME = 160;          // samples per packet: 10 ms
const int SLOTS = 64;           // jitter buffer capacity: 640 ms
const int TARGET = 6;           // frames buffered before playing: 60 ms
const int GIVE_UP = 30;         // frames missing in a row before rebuffering: 300 ms
const int RAMP = 32;            // samples to fade in or out: 2 ms
// Frames still queued after taking one: TARGET - 1 when the two clocks agree.
const float CENTER = TARGET - 1;

// Packet: "VAU1", stream id, sequence (little-endian uint32), then this frame and
// the previous one as int16 samples.
struct __attribute__((packed)) Packet {
  char magic[4];
  uint32_t stream, seq;
  int16_t cur[FRAME], prev[FRAME];
};

struct Slot {
  uint32_t seq;
  bool full;
  int16_t pcm[FRAME];
};

static Slot slots[SLOTS];
static portMUX_TYPE lock = portMUX_INITIALIZER_UNLOCKED;
// Guarded by lock.
static bool playing = false, restart = true;
static uint32_t stream = 0, newest = 0, playSeq = 0;

// Stats, written by one task each and read for the report.
static volatile uint32_t received = 0, late = 0, recovered = 0, concealed = 0, dropped = 0, repeated = 0, rebuffers = 0;
static volatile float fillAvg = CENTER;

static i2s_chan_handle_t tx;
static int sock = -1;

static void store(uint32_t seq, const int16_t *pcm, bool isCopy) {
  portENTER_CRITICAL(&lock);
  if (playing && (int32_t)(seq - playSeq) < 0) {
    if (!isCopy) late++;
  } else if (!playing || (int32_t)(seq - playSeq) < SLOTS) {
    Slot &s = slots[seq % SLOTS];
    if (!s.full || s.seq != seq) {
      s.seq = seq;
      s.full = true;
      memcpy(s.pcm, pcm, sizeof(s.pcm));
      if (isCopy) recovered++;
    }
    if ((int32_t)(seq - newest) > 0) newest = seq;
  }
  portEXIT_CRITICAL(&lock);
}

static void receiveTask(void *) {
  static Packet p;
  sockaddr_in from;
  socklen_t fromLen;
  sockaddr_in sender = {};
  uint32_t lastReport = millis();
  while (true) {
    fromLen = sizeof(from);
    int n = recvfrom(sock, &p, sizeof(p), 0, (sockaddr *)&from, &fromLen);
    if (n == sizeof(p) && memcmp(p.magic, "VAU1", 4) == 0) {
      sender = from;
      received++;
      portENTER_CRITICAL(&lock);
      // A new sender run, or a jump far from where we are: start over.
      if (p.stream != stream || (playing && abs((int32_t)(p.seq - playSeq)) > 1000)) {
        stream = p.stream;
        restart = true;
      }
      if (restart) {
        for (Slot &s : slots) s.full = false;
        playing = false;
        newest = p.seq;
        restart = false;
      }
      portEXIT_CRITICAL(&lock);
      store(p.seq, p.cur, false);
      if (p.seq > 0) store(p.seq - 1, p.prev, true);
    }
    if (millis() - lastReport >= 1000) {
      lastReport = millis();
      if (!sender.sin_port) continue;  // nothing streamed yet: stay quiet
      char line[160];
      int len = snprintf(line, sizeof(line),
          "SPEAKER,fill=%.1f,received=%u,recovered=%u,concealed=%u,late=%u,drift=+%u/-%u,rebuffers=%u,rssi=%d",
          fillAvg, received, recovered, concealed, late, repeated, dropped, rebuffers, WiFi.RSSI());
      Serial.println(line);
      sendto(sock, line, len, 0, (sockaddr *)&sender, sizeof(sender));
    }
  }
}

// Fills out[] with the next frame and returns how many samples it holds (FRAME,
// or one fewer or more to follow the sender's clock), or 0 to play silence.
static int nextFrame(int16_t *out, bool &got) {
  got = false;
  portENTER_CRITICAL(&lock);
  if (!playing) {
    // Wait for TARGET frames, then start TARGET behind the newest.
    uint32_t start = newest - (TARGET - 1);
    bool ready = true;
    for (int i = 0; i < TARGET && ready; i++) {
      const Slot &s = slots[(start + i) % SLOTS];
      ready = s.full && s.seq == start + i;
    }
    if (ready) {
      playing = true;
      playSeq = start;
      fillAvg = CENTER;
    }
  }
  if (!playing) {
    portEXIT_CRITICAL(&lock);
    return 0;
  }
  Slot &s = slots[playSeq % SLOTS];
  if (s.full && s.seq == playSeq) {
    memcpy(out, s.pcm, sizeof(s.pcm));
    s.full = false;
    got = true;
  }
  const int fill = (int32_t)(newest - playSeq);
  playSeq++;
  portEXIT_CRITICAL(&lock);

  // About 5 s of smoothing: Wi-Fi jitter averages out, clock drift does not.
  fillAvg += (fill - fillAvg) * 0.002f;
  if (!got) return FRAME;
  if (fillAvg > CENTER + 1) {
    dropped++;
    return FRAME - 1;  // play the frame without its last sample
  }
  if (fillAvg < CENTER - 1) {
    repeated++;
    out[FRAME] = out[FRAME - 1];
    return FRAME + 1;
  }
  return FRAME;
}

static void playTask(void *) {
  static int16_t frame[FRAME + 1];
  static int16_t stereo[(FRAME + 1) * 2];
  float gain = 0;       // fades in after a gap, out into one
  int16_t last = 0;     // last sample played, faded out over a gap
  int missing = 0;
  while (true) {
    bool got;
    int n = nextFrame(frame, got);
    if (n == 0) {
      // Not playing yet: feed silence at the real rate so the wait is paced.
      n = FRAME;
      memset(frame, 0, sizeof(frame));
      got = false;
      missing = 0;
    } else if (!got) {
      concealed++;
      if (++missing >= GIVE_UP) {
        portENTER_CRITICAL(&lock);
        playing = false;
        portEXIT_CRITICAL(&lock);
        rebuffers++;
        missing = 0;
      }
    } else {
      missing = 0;
    }
    for (int i = 0; i < n; i++) {
      float v;
      if (got) {
        gain = min(1.0f, gain + 1.0f / RAMP);
        v = frame[i] * gain;
        last = frame[i];
      } else {
        gain = max(0.0f, gain - 1.0f / RAMP);
        v = last * gain;
      }
      stereo[2 * i] = stereo[2 * i + 1] = (int16_t)v;
    }
    size_t written;
    i2s_channel_write(tx, stereo, n * 2 * sizeof(int16_t), &written, portMAX_DELAY);
  }
}

static void startI2s() {
  i2s_chan_config_t chan = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
  chan.dma_desc_num = 4;
  chan.dma_frame_num = FRAME;  // 40 ms of DMA, plays silence if it runs dry
  chan.auto_clear = true;
  ESP_ERROR_CHECK(i2s_new_channel(&chan, &tx, NULL));
  i2s_std_config_t std = {
    .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(SAMPLE_RATE),
    .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_STEREO),
    .gpio_cfg = {
      .mclk = I2S_GPIO_UNUSED,
      .bclk = (gpio_num_t)PIN_BCLK,
      .ws = (gpio_num_t)PIN_LRC,
      .dout = (gpio_num_t)PIN_DIN,
      .din = I2S_GPIO_UNUSED,
      .invert_flags = {false, false, false},
    },
  };
  ESP_ERROR_CHECK(i2s_channel_init_std_mode(tx, &std));
  ESP_ERROR_CHECK(i2s_channel_enable(tx));
}

// Call once Wi-Fi has been started (it need not be connected yet).
static void begin() {
  startI2s();
  sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
  sockaddr_in addr = {};
  addr.sin_family = AF_INET;
  addr.sin_port = htons(PORT);
  addr.sin_addr.s_addr = htonl(INADDR_ANY);
  bind(sock, (sockaddr *)&addr, sizeof(addr));
  timeval timeout = {0, 100000};  // wake up to report even with no audio
  setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
  int rcvbuf = 16 * 1024;
  setsockopt(sock, SOL_SOCKET, SO_RCVBUF, &rcvbuf, sizeof(rcvbuf));
  xTaskCreatePinnedToCore(receiveTask, "audio_rx", 4096, NULL, 5, NULL, 0);
  xTaskCreatePinnedToCore(playTask, "audio_play", 4096, NULL, 10, NULL, 0);
}

}  // namespace AudioStream
