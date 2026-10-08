// Network speaker only (no UWB): plays audio streamed by audio_stream.py on the
// MAX98357A amp; see ../audio_stream.h for the wiring and how the stream works.
// Joins the Wi-Fi in secrets.h as uwb-speaker.local. A tag can do the same while
// ranging: define AUDIO_STREAM in its sketch (as firmware/tag4 does).
#include <ArduinoOTA.h>
#include <WiFi.h>
#include "../audio_stream.h"
#include "../secrets.h"

const char HOSTNAME[] = "uwb-speaker";

void setup() {
  Serial.begin(115200);
  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.setHostname(HOSTNAME);
  WiFi.setSleep(false);  // power save adds 100 ms+ gaps
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_NAME, WIFI_PASSWORD);
  Serial.printf("SPEAKER,joining,%s\n", WIFI_NAME);
  while (WiFi.status() != WL_CONNECTED) delay(100);

  ArduinoOTA.setHostname(HOSTNAME);
  ArduinoOTA.setPassword(OTA_PASSWORD);
  ArduinoOTA.begin();  // also starts mDNS as uwb-speaker.local

  AudioStream::begin();
  Serial.printf("SPEAKER,ready,ip=%s,port=%d,host=%s.local\n", WiFi.localIP().toString().c_str(),
                AudioStream::PORT, HOSTNAME);
}

void loop() {
  ArduinoOTA.handle();
  delay(20);
}
