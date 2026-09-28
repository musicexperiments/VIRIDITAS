#pragma once
#include <Arduino.h>
#include <DW3000.h>
#include <Preferences.h>
#include "range_math.h"

#include <ArduinoOTA.h>
#include <ESPmDNS.h>
#include <WiFi.h>
#if NODE_ID == 1
#include <WebServer.h>
#include <WiFiUdp.h>
#endif

// Node ids: 1 = anchor 1 (Wi-Fi, coordinator), 2 = tag 1, 3..5 = anchors 2..4,
// 6 and up = tags 2, 3, ... To add a tag, raise NODE_COUNT and give the new
// board the next id (tag N is node N + 4).
static const uint8_t NODE_COUNT = 8;
static const uint8_t TAG_NODE = 2;  // Tag 1: the pair kept on /api/distance.
static bool isTag(uint8_t node) { return node == 2 || node >= 6; }
static_assert(NODE_ID >= 1 && NODE_ID <= NODE_COUNT,
              "NODE_ID must be 1..NODE_COUNT (1 anchor 1, 2 tag 1, 3-5 anchors 2-4, 6+ tags 2+)");

// Frame: [0] mode, [1] sender, [2] destination, [3] step, [4..] payload.
// Any two nodes range with asymmetric DS-TWR (poll, response, final, report);
// the initiator computes the distance. Anchor 1 (node 1, on Wi-Fi) schedules
// every pair; for pairs without it, it asks the lower-numbered node to range
// the other and send the result back.
enum Step : uint8_t {
  POLL = 1,           // [4..5] antenna delay (honoured from node 1 only), [6] command
  RESPONSE = 2,
  FINAL = 3,
  REPORT = 4,         // [4..7] Rb, [8..11] Db, [12..13] responder's antenna delay
  RANGE_REQUEST = 5,  // [4] node to range with
  RANGE_RESULT = 6,   // [4] peer, [5] ok, [6..9] raw centimeters (float)
};
enum State : uint8_t { IDLE, WAIT_RESPONSE, WAIT_REPORT, WAIT_FINAL, WAIT_RESULT };
static const uint8_t COMMAND_UPDATE = 1;

static uint8_t state = IDLE, peer = 0;
static uint32_t startedAt = 0;
static uint64_t lastTx = 0, pollTx = 0, responseTx = 0, pollRx = 0;
static uint32_t roundTime = 0, replyTime = 0, responderDelay = 0;

// One value for TX and RX on every board; the anchor pushes it in each poll.
static const uint16_t DEFAULT_ANTENNA_DELAY = 16400;
static Preferences settings;
static uint16_t antennaDelay = DEFAULT_ANTENNA_DELAY;
static int32_t pendingAntennaDelay = -1;

// WIFI_NAME, WIFI_PASSWORD and OTA_PASSWORD live in secrets.h, which git
// ignores; copy secrets.example.h to secrets.h and fill it in. Firmware
// updates run over the local Wi-Fi (no internet). Other boards keep their
// radio off until anchor 1 sends them an update request over UWB.
#include "secrets.h"
// Tag N (node N + 4, N >= 2) is uwb-tagN.
static const char *const HOSTNAMES[] = {"", "uwb-anchor", "uwb-tag", "uwb-anchor2", "uwb-anchor3", "uwb-anchor4"};
static char tagHostname[12];
static const char *const HOSTNAME = NODE_ID <= 5 ? HOSTNAMES[NODE_ID] :
    (snprintf(tagHostname, sizeof(tagHostname), "uwb-tag%d", NODE_ID - 4), tagHostname);

static void startOta() {
  ArduinoOTA.end();
  ArduinoOTA.setHostname(HOSTNAME);
  ArduinoOTA.setPassword(OTA_PASSWORD);
  ArduinoOTA.setMdnsEnabled(false);  // mDNS is managed here alongside HTTP.
  ArduinoOTA.onStart([]() {
    DW3000.forceIdle();
    Serial.println("OTA,start");
  });
  ArduinoOTA.onError([](ota_error_t error) { Serial.printf("OTA,error=%u\n", error); });
  ArduinoOTA.begin();
  MDNS.end();
  if (MDNS.begin(HOSTNAME)) {
    MDNS.enableArduino(3232, true);
    if (NODE_ID == 1) MDNS.addService("http", "tcp", 80);
  }
}

#if NODE_ID != 1
static const uint32_t UPDATE_WINDOW_MS = 10 * 60 * 1000;
static bool updateMode = false;
static bool updateOtaStarted = false;
static uint32_t updateModeAt = 0;

static void enterUpdateMode() {
  DW3000.forceIdle();
  updateMode = true;
  updateModeAt = millis();
  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.setHostname(HOSTNAME);
  WiFi.setSleep(false);
  WiFi.begin(WIFI_NAME, WIFI_PASSWORD);
  Serial.println("OTA,update_mode,waiting_for_wifi");
}

// Ranging is paused; reboot back to normal if no update arrives in the window.
static void serviceUpdateMode() {
  if (WiFi.status() == WL_CONNECTED && !updateOtaStarted) {
    updateOtaStarted = true;
    startOta();
    Serial.printf("OTA,ready,ip=%s\n", WiFi.localIP().toString().c_str());
  }
  ArduinoOTA.handle();
  if (millis() - updateModeAt >= UPDATE_WINDOW_MS) ESP.restart();
}
#endif

#if NODE_ID == 1
static const uint16_t SLOT_MS = 4;  // Minimum gap between exchanges.

struct Pair {
  uint8_t a, b;
  RangeMath::Median5 filter;
  double rawCm = 0, filteredCm = 0;
  uint32_t at = 0, sequence = 0, failed = 0;
  bool reversed = false;  // Relayed pairs alternate which node initiates.
};
// Every pair once; anchor 1 initiates its own pairs, and the two nodes of any
// other pair take turns initiating (a one-sided RF or node fault still gets
// through from the other side). Pairs with a tag (tag-to-anchor and
// tag-to-tag) come first and are ranged every cycle; the fixed anchor-to-anchor
// pairs take one slot per cycle in turn.
static Pair pairs[NODE_COUNT * (NODE_COUNT - 1) / 2];
static uint8_t PAIR_COUNT = 0;
static uint8_t tagPairCount = 0;
static uint8_t cycleSlot = 0, nextAnchorPair = 0, currentPair = 0;
static uint32_t lastSlotAt = 0;
static int32_t nodeDelay[NODE_COUNT + 1];

static void buildPairs() {
  uint8_t count = 0;
  for (int tagPass = 1; tagPass >= 0; --tagPass) {
    for (uint8_t a = 1; a <= NODE_COUNT; ++a)
      for (uint8_t b = a + 1; b <= NODE_COUNT; ++b)
        if ((isTag(a) || isTag(b)) == tagPass) { pairs[count].a = a; pairs[count++].b = b; }
    if (tagPass) tagPairCount = count;
  }
  PAIR_COUNT = count;
  for (int32_t &delay : nodeDelay) delay = -1;
}

static uint8_t nextScheduledPair() {
  if (cycleSlot < tagPairCount) return cycleSlot++;
  cycleSlot = 0;
  const uint8_t pair = tagPairCount + nextAnchorPair;
  nextAnchorPair = (nextAnchorPair + 1) % (PAIR_COUNT - tagPairCount);
  return pair;
}
static uint32_t lastHeard[NODE_COUNT + 1] = {};
static uint8_t updateNode = 0;
static uint32_t updateRequestedAt = 0;

static WebServer webServer(80);
// Low-latency stream: each new range is sent by UDP to whoever subscribed via
// POST /api/stream?port=N, for 15 s after their last subscription.
static WiFiUDP streamUdp;
static IPAddress streamIp;
static uint16_t streamPort = 0;
static uint32_t streamRenewedAt = 0;
static const uint32_t STREAM_LEASE_MS = 15000;
static uint32_t wifiAttemptAt = 0;
static bool wifiWasConnected = false;
static bool wifiRestartPending = false;

static bool pairValid(const Pair &pair) { return pair.at != 0 && millis() - pair.at < 2000; }
static bool nodeOnline(uint8_t node) {
  return node == NODE_ID || (lastHeard[node] != 0 && millis() - lastHeard[node] < 2000);
}

static Pair *findPair(uint8_t a, uint8_t b) {
  for (Pair &pair : pairs)
    if ((pair.a == a && pair.b == b) || (pair.a == b && pair.b == a)) return &pair;
  return nullptr;
}

static void recordRange(uint8_t a, uint8_t b, bool ok, double cm) {
  Pair *pair = findPair(a, b);
  if (!pair) return;
  if (!ok || !isfinite(cm) || cm < 0 || cm > 10000) { ++pair->failed; return; }
  if (!pairValid(*pair)) pair->filter.reset();
  pair->rawCm = cm;
  pair->filteredCm = pair->filter.push(cm);
  pair->at = millis();
  ++pair->sequence;
  // "R,a,b,raw_cm,filtered_cm,sequence"
  if (streamPort && millis() - streamRenewedAt < STREAM_LEASE_MS && WiFi.status() == WL_CONNECTED) {
    char line[64];
    const int length = snprintf(line, sizeof(line), "R,%u,%u,%.2f,%.2f,%lu\n", pair->a, pair->b, pair->rawCm,
                                pair->filteredCm, static_cast<unsigned long>(pair->sequence));
    streamUdp.beginPacket(streamIp, streamPort);
    streamUdp.write(reinterpret_cast<const uint8_t *>(line), length);
    streamUdp.endPacket();
  }
}

static void setAntennaDelay(uint16_t delay);

static void startWebServer() {
  webServer.on("/", HTTP_GET, []() {
    webServer.send(200, "text/plain", "UWB anchor. Open the website on the laptop: python3 web/server.py\n");
  });
  // Anchor-1-to-tag pair (pairs[0]), kept for the calibration page and check_accuracy.py.
  webServer.on("/api/distance", HTTP_GET, []() {
    const Pair &pair = pairs[0];
    const bool valid = pairValid(pair);
    char json[400];
    snprintf(json, sizeof(json),
             "{\"valid\":%s,\"inches\":%.3f,\"centimeters\":%.3f,\"sequence\":%lu,\"raw_cm\":%.4f,\"failed_exchanges\":%lu,"
             "\"antenna_delay\":%u,\"tag_antenna_delay\":%ld}",
             valid ? "true" : "false", pair.filteredCm / 2.54, pair.filteredCm,
             static_cast<unsigned long>(pair.sequence), pair.rawCm,
             static_cast<unsigned long>(pair.failed), antennaDelay, static_cast<long>(nodeDelay[2]));
    webServer.sendHeader("Cache-Control", "no-store");
    webServer.send(200, "application/json", json);
  });
  webServer.on("/api/ranges", HTTP_GET, []() {
    String json = "{\"antenna_delay\":" + String(antennaDelay) + ",\"nodes\":[";
    for (uint8_t node = 1; node <= NODE_COUNT; ++node) {
      if (node > 1) json += ',';
      json += "{\"id\":" + String(node) + ",\"online\":" + (nodeOnline(node) ? "true" : "false") +
              ",\"antenna_delay\":" + String(node == 1 ? antennaDelay : nodeDelay[node]) + '}';
    }
    json += "],\"pairs\":[";
    for (uint8_t i = 0; i < PAIR_COUNT; ++i) {
      const Pair &pair = pairs[i];
      char item[200];
      snprintf(item, sizeof(item),
               "%s{\"a\":%u,\"b\":%u,\"valid\":%s,\"cm\":%.3f,\"raw_cm\":%.3f,\"sequence\":%lu,\"failed\":%lu}",
               i ? "," : "", pair.a, pair.b, pairValid(pair) ? "true" : "false", pair.filteredCm,
               pair.rawCm, static_cast<unsigned long>(pair.sequence), static_cast<unsigned long>(pair.failed));
      json += item;
    }
    json += "]}";
    webServer.sendHeader("Cache-Control", "no-store");
    webServer.send(200, "application/json", json);
  });
  webServer.on("/api/antenna-delay", HTTP_GET, []() {
    char json[80];
    snprintf(json, sizeof(json), "{\"antenna_delay\":%u,\"tag_antenna_delay\":%ld}",
             antennaDelay, static_cast<long>(nodeDelay[TAG_NODE]));
    webServer.sendHeader("Cache-Control", "no-store");
    webServer.send(200, "application/json", json);
  });
  webServer.on("/api/antenna-delay", HTTP_POST, []() {
    const String text = webServer.arg("value");
    char *end = nullptr;
    const unsigned long value = strtoul(text.c_str(), &end, 0);
    if (text.isEmpty() || *end || text[0] == '-' || value > 0xFFFF) {
      webServer.send(400, "text/plain", "value must be an integer from 0 to 65535");
      return;
    }
    setAntennaDelay(value);
    char json[40];
    snprintf(json, sizeof(json), "{\"antenna_delay\":%u}", antennaDelay);
    webServer.send(200, "application/json", json);
  });
  webServer.on("/api/stream", HTTP_POST, []() {
    const long port = webServer.arg("port").toInt();
    if (port < 1 || port > 65535) {
      webServer.send(400, "text/plain", "port must be 1 to 65535");
      return;
    }
    streamIp = webServer.client().remoteIP();
    streamPort = port;
    streamRenewedAt = millis();
    webServer.send(200, "application/json", "{\"streaming\":true}");
  });
  webServer.on("/api/tag-update", HTTP_POST, []() {
    const long node = webServer.hasArg("node") ? webServer.arg("node").toInt() : 2;
    if (node < 2 || node > NODE_COUNT) {
      webServer.send(400, "text/plain", "node must be 2 to NODE_COUNT");
      return;
    }
    updateNode = node;
    updateRequestedAt = millis();
    Serial.printf("OTA,update_requested,node=%ld\n", node);
    webServer.send(200, "application/json", "{\"requested\":true}");
  });
  webServer.onNotFound([]() { webServer.send(404, "text/plain", "Not found"); });
  webServer.begin();
}

static void connectWifi() {
  WiFi.persistent(false);
  WiFi.onEvent([](WiFiEvent_t event, WiFiEventInfo_t info) {
    if (event == ARDUINO_EVENT_WIFI_STA_DISCONNECTED)
      Serial.printf("WIFI,disconnected,reason=%u\n", info.wifi_sta_disconnected.reason);
  });
  WiFi.mode(WIFI_STA);
  WiFi.setHostname(HOSTNAME);
  // Use one retry controller; automatic retries can race a fresh begin().
  WiFi.setAutoReconnect(false);
  WiFi.setSleep(false);
  WiFi.setScanMethod(WIFI_ALL_CHANNEL_SCAN);
  WiFi.setSortMethod(WIFI_CONNECT_AP_BY_SIGNAL);
  const int networks = WiFi.scanNetworks();
  for (int i = 0; i < networks; ++i) {
    if (WiFi.SSID(i) == WIFI_NAME)
      Serial.printf("WIFI,found,channel=%d,rssi=%d,bssid=%s\n",
                    WiFi.channel(i), WiFi.RSSI(i), WiFi.BSSIDstr(i).c_str());
  }
  WiFi.scanDelete();
  WiFi.begin(WIFI_NAME, WIFI_PASSWORD);
  wifiAttemptAt = millis();
  Serial.printf("Connecting to Wi-Fi %s; ranging continues independently\n", WIFI_NAME);
  startWebServer();
}

static void serviceWifi() {
  if (WiFi.status() == WL_CONNECTED) {
    if (!wifiWasConnected) {
      wifiWasConnected = true;
      startOta();
      Serial.printf("WIFI,connected,ip=%s,rssi=%d\n",
                    WiFi.localIP().toString().c_str(), WiFi.RSSI());
    }
    webServer.handleClient();
    ArduinoOTA.handle();
  } else {
    wifiWasConnected = false;
    if (wifiRestartPending && millis() - wifiAttemptAt >= 500) {
      wifiRestartPending = false;
      wifiAttemptAt = millis();
      WiFi.begin(WIFI_NAME, WIFI_PASSWORD);
    } else if (!wifiRestartPending && millis() - wifiAttemptAt >= 15000) {
      wifiAttemptAt = millis();
      Serial.printf("WIFI,retry,status=%d\n", WiFi.status());
      WiFi.disconnect();
      wifiRestartPending = true;
    }
  }
}
#endif

// TX_ANTD (0x01:04) and CIA_CONF RXANTD (0x0E:00); the library sets only TX.
static void applyAntennaDelay(uint16_t delay) {
  DW3000.setTXAntennaDelay(delay);
  DW3000.write(0x0E, 0x00, delay, 2);
}

static void setAntennaDelay(uint16_t delay) {
  if (delay == antennaDelay) return;
  antennaDelay = delay;
  applyAntennaDelay(delay);
  settings.putUShort("antenna_delay", delay);
#if NODE_ID == 1
  // Readings taken with the old delay must not mix into the new medians.
  for (Pair &pair : pairs) pair.at = 0;
#endif
  Serial.printf("ANTENNA_DELAY,set=%u\n", delay);
}

static void listenForUwb() {
  DW3000.forceIdle();
  // Apply between exchanges so every timestamp in one exchange uses the same delay.
  if (pendingAntennaDelay >= 0) {
    setAntennaDelay(pendingAntennaDelay);
    pendingAntennaDelay = -1;
  }
  DW3000.clearSystemStatus();
  DW3000.standardRX();
  state = IDLE;
}

static void rearmReceiver() {
  DW3000.clearSystemStatus();
  DW3000.standardRX();
}

// Read a TX timestamp only after hardware confirms this frame was transmitted.
static bool transmit(uint8_t destination, uint8_t step, const uint8_t *payload = nullptr,
                     uint8_t length = 0) {
  DW3000.forceIdle();
  DW3000.clearSystemStatus();
  DW3000.setMode(1);
  DW3000.write(0x14, 0x01, NODE_ID);
  DW3000.write(0x14, 0x02, destination);
  DW3000.write(0x14, 0x03, step);
  for (uint8_t i = 0; i < length; i += 4) {
    const uint8_t size = min<uint8_t>(4, length - i);
    uint32_t chunk = 0;
    memcpy(&chunk, payload + i, size);
    DW3000.write(0x14, 0x04 + i, chunk, size);
  }
  DW3000.setFrameLength(4 + length);
  DW3000.TXInstantRX();
  const uint32_t start = micros();
  while (DW3000.sentFrameSucc() != 1) {
    if (micros() - start >= 5000) return false;
  }
  lastTx = DW3000.readTXTimestamp();
  return true;
}

static void abortExchange() {
#if NODE_ID == 1
  ++pairs[currentPair].failed;
#endif
  listenForUwb();
}

static void startExchange(uint8_t target, uint8_t command) {
  uint8_t payload[3] = {static_cast<uint8_t>(antennaDelay), static_cast<uint8_t>(antennaDelay >> 8), command};
  if (!transmit(target, POLL, payload, sizeof(payload))) { abortExchange(); return; }
  pollTx = lastTx;
  peer = target;
  state = WAIT_RESPONSE;
  startedAt = millis();
}

// Initiator side: the responder's report completes the four intervals.
static void finishExchange() {
  const uint32_t rb = DW3000.read(0x12, 0x04), db = DW3000.read(0x12, 0x08);
  const uint16_t theirDelay = DW3000.read(0x12, 0x0C) & 0xFFFF;
  const double meters = RangeMath::meters(roundTime, replyTime, rb, db);
  // A responder still on another delay (it switches between exchanges) is skipped.
  const bool ok = theirDelay == antennaDelay && isfinite(meters) && meters >= 0 && meters <= 100;
#if NODE_ID == 1
  nodeDelay[peer] = theirDelay;
  recordRange(NODE_ID, peer, ok, meters * 100);
  if (ok) Serial.printf("RANGE,%u-%u,raw_cm=%.3f\n", NODE_ID, peer, meters * 100);
  listenForUwb();
#else
  // Ranges measured by other nodes are relayed to anchor 1.
  const float cm = meters * 100;
  uint8_t payload[6] = {peer, ok};
  memcpy(payload + 2, &cm, sizeof(cm));
  transmit(1, RANGE_RESULT, payload, sizeof(payload));
  listenForUwb();
#endif
}

static void handleFrame() {
  const uint8_t sender = DW3000.getSenderID(), step = DW3000.ds_getStage();
#if NODE_ID == 1
  if (sender >= 2 && sender <= NODE_COUNT) lastHeard[sender] = millis();
#endif
  if (DW3000.getDestinationID() != NODE_ID || DW3000.ds_isErrorFrame() || sender == NODE_ID) {
    rearmReceiver();
    return;
  }
  const uint64_t rx = DW3000.readRXTimestamp();

  if (step == POLL && state == IDLE) {
    const uint32_t poll = DW3000.read(0x12, 0x04);
    if (sender == 1) {
#if NODE_ID != 1
      if (((poll >> 16) & 0xFF) == COMMAND_UPDATE) { enterUpdateMode(); return; }
#endif
      const uint16_t requested = poll & 0xFFFF;
      if (requested != antennaDelay) pendingAntennaDelay = requested;
    }
    if (!transmit(sender, RESPONSE)) { abortExchange(); return; }
    responseTx = lastTx;
    pollRx = rx;
    peer = sender;
    state = WAIT_FINAL;
    startedAt = millis();
  } else if (step == RESPONSE && state == WAIT_RESPONSE && sender == peer) {
    if (!RangeMath::interval(rx, pollTx, roundTime)) { abortExchange(); return; }
    if (!transmit(peer, FINAL) || !RangeMath::interval(lastTx, rx, replyTime)) {
      abortExchange(); return;
    }
    state = WAIT_REPORT;
    startedAt = millis();
  } else if (step == FINAL && state == WAIT_FINAL && sender == peer) {
    uint32_t rb = 0, db = 0;
    if (!RangeMath::interval(rx, responseTx, rb) || !RangeMath::interval(responseTx, pollRx, db)) {
      abortExchange(); return;
    }
    uint8_t payload[10];
    memcpy(payload, &rb, 4);
    memcpy(payload + 4, &db, 4);
    payload[8] = antennaDelay & 0xFF;
    payload[9] = antennaDelay >> 8;
    transmit(peer, REPORT, payload, sizeof(payload));
    listenForUwb();
  } else if (step == REPORT && state == WAIT_REPORT && sender == peer) {
    finishExchange();
#if NODE_ID != 1
  } else if (step == RANGE_REQUEST && state == IDLE && sender == 1) {
    startExchange(DW3000.read(0x12, 0x04) & 0xFF, 0);
#else
  } else if (step == RANGE_RESULT && state == WAIT_RESULT && sender == peer) {
    const uint32_t word = DW3000.read(0x12, 0x04), cmBits = DW3000.read(0x12, 0x06);
    float cm;
    memcpy(&cm, &cmBits, sizeof(cm));
    recordRange(sender, word & 0xFF, (word >> 8) & 0xFF, cm);
    listenForUwb();
#endif
  } else {
    rearmReceiver();
  }
}

void setup() {
  Serial.begin(115200);
  settings.begin("uwb");
#if NODE_ID == 1
  buildPairs();
#endif
  antennaDelay = settings.getUShort("antenna_delay", DEFAULT_ANTENNA_DELAY);
#if NODE_ID == 1
  connectWifi();
#endif
  DW3000.begin();
  DW3000.hardReset();
  delay(200);
  if (!DW3000.checkSPI()) {
    Serial.println("ERROR,SPI");
    while (true) delay(1000);
  }
  while (!DW3000.checkForIDLE()) delay(10);
  DW3000.softReset();
  delay(200);
  while (!DW3000.checkForIDLE()) delay(10);
  DW3000.init();
  DW3000.setupGPIO();
  DW3000.configureAsTX();
  DW3000.setSenderID(NODE_ID);
  applyAntennaDelay(antennaDelay);
  listenForUwb();
  Serial.printf("Ready: node %u (%s), antenna delay %u\n", NODE_ID, HOSTNAME, antennaDelay);
}

void loop() {
#if NODE_ID != 1
  if (updateMode) { serviceUpdateMode(); return; }
#else
  // Keep HTTP work outside exchanges; then start the next pair's exchange.
  if (state == IDLE) serviceWifi();
  if (state == IDLE && millis() - lastSlotAt >= SLOT_MS) {
    lastSlotAt = millis();
    currentPair = nextScheduledPair();
    Pair &pair = pairs[currentPair];
    if (pair.a == NODE_ID) {
      // Repeat an update request for a few seconds so one missed poll does not lose it.
      const bool update = updateNode == pair.b && millis() - updateRequestedAt < 3000;
      startExchange(pair.b, update ? COMMAND_UPDATE : 0);
    } else {
      pair.reversed = !pair.reversed;
      const uint8_t initiator = pair.reversed ? pair.b : pair.a;
      const uint8_t target = pair.reversed ? pair.a : pair.b;
      if (!transmit(initiator, RANGE_REQUEST, &target, 1)) { abortExchange(); return; }
      peer = initiator;
      state = WAIT_RESULT;
      startedAt = millis();
    }
    return;
  }
#endif
  // A relayed tag-to-tag exchange takes two exchanges' worth of time.
  if (state != IDLE && millis() - startedAt > (state == WAIT_RESULT ? 40u : 20u)) {
    abortExchange();
    return;
  }
  const int status = DW3000.receivedFrameSucc();
  if (!status) return;
  // Other pairs share the channel; a corrupted frame is not fatal, the timeout is.
  if (status != 1) { rearmReceiver(); return; }
  handleFrame();
}
