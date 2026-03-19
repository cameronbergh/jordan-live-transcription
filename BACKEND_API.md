# Backend Streaming API Spec

## Purpose
Define the first-pass backend contract for Jordan's live transcription system.

The iPhone app is the client.
The backend server receives live audio, performs speech recognition, and streams transcript updates back in near real time.

## Current Backend Direction
- **Primary host:** Linux GPU box `cameron-ms-7b17`
- **Primary hardware target:** 2x RTX 3060 12GB
- **Fallback / alternative host:** second Linux box with 2x 2080 Ti
- **Speech stack direction:** regular NVIDIA Parakeet ecosystem / repo
- **Non-goals for now:** MLX Audio Swift backend, llama.cpp / GGUF Parakeet path

## Architecture
- **Client:** iPhone app
- **Server:** transcription backend running on Linux GPU hardware
- **Transport:** WebSocket for bidirectional low-latency streaming
- **Flow:**
  1. client connects
  2. client sends session/config message
  3. client streams audio chunks
  4. server emits partial/final transcript events
  5. client renders transcript live

## Why WebSocket
WebSocket is the simplest good first choice because it:
- supports full-duplex streaming
- is easy to use from Swift on iPhone
- is easy to implement on a server
- avoids the extra complexity of gRPC for MVP

## Connection
**Endpoint:**
`wss://<host>/v1/transcription/stream`

For local development, allow:
`ws://<host>:<port>/v1/transcription/stream`

## Session Model
One WebSocket connection = one transcription session.

The connection should remain open while the app is listening.
If the connection drops, the client should attempt reconnect and show a visible reconnecting state.

## Client → Server Messages
All control messages are JSON.
Audio messages are binary frames.

### 1. session.start
Sent once after connection opens.

```json
{
  "type": "session.start",
  "sessionId": "uuid-or-client-generated-id",
  "audio": {
    "encoding": "pcm_s16le",
    "sampleRate": 16000,
    "channels": 1,
    "chunkMs": 100
  },
  "transcription": {
    "partials": true,
    "language": null
  },
  "client": {
    "platform": "ios",
    "appVersion": "0.1.0"
  }
}
```

### 2. audio.append
For MVP, prefer **binary WebSocket frames** containing raw PCM16 mono audio.

Binary frame payload:
- encoding: signed 16-bit little-endian PCM
- sample rate: 16kHz
- channels: mono
- chunk size target: 50–200ms per frame

If needed for debugging, a JSON/base64 fallback can exist, but binary should be the default.

### 3. session.stop
Sent when the app stops listening.

```json
{
  "type": "session.stop"
}
```

### 4. ping
Optional keepalive.

```json
{
  "type": "ping",
  "timestamp": 1773880000000
}
```

## Server → Client Messages

### 1. session.started
Acknowledges configuration.

```json
{
  "type": "session.started",
  "sessionId": "abc123",
  "server": {
    "engine": "parakeet",
    "host": "cameron-ms-7b17"
  }
}
```

### 2. transcript.partial
Partial / interim text during ongoing speech.

```json
{
  "type": "transcript.partial",
  "segmentId": "seg-12",
  "startMs": 4200,
  "endMs": 6100,
  "text": "I want to make a",
  "isFinal": false
}
```

### 3. transcript.final
Finalized segment.

```json
{
  "type": "transcript.final",
  "segmentId": "seg-12",
  "startMs": 4200,
  "endMs": 6800,
  "text": "I want to make a transcription app.",
  "isFinal": true
}
```

### 4. status
Useful for loading / reconnecting / model warmup states.

```json
{
  "type": "status",
  "state": "warming_model",
  "message": "Loading Parakeet model"
}
```

Suggested states:
- `connecting`
- `ready`
- `warming_model`
- `listening`
- `processing`
- `reconnecting`

### 5. error
Recoverable or fatal error.

```json
{
  "type": "error",
  "code": "model_unavailable",
  "message": "Parakeet model is not loaded",
  "fatal": false
}
```

### 6. pong
Optional keepalive reply.

```json
{
  "type": "pong",
  "timestamp": 1773880000000
}
```

## MVP Transcript Semantics
For MVP, the backend should emit:
- partial transcript updates while speech is active
- final transcript segments when speech is considered complete

Client behavior:
- render partials live
- replace/merge them with final text when the final segment arrives
- maintain a visible transcript history for the current session

## Audio Format Decision
Recommended MVP audio format:
- **PCM16 mono**
- **16kHz**
- **100ms chunks**

Why:
- simple to encode on iPhone
- simple to decode on server
- friendly to ASR/VAD pipelines
- avoids container overhead during streaming

## Backend Responsibilities
The backend should:
- load the ASR model into memory at server startup
- warm the model at startup so the first live session avoids cold-start delay
- keep the model resident in memory while the server is running
- accept incoming WebSocket sessions
- buffer / process audio chunks
- run VAD and ASR
- emit partial + final transcript events
- surface readiness / error states
- support one active client session per connection
- wrap the NVIDIA Parakeet runtime in a clean session-oriented server API

## Client Responsibilities
The iPhone app should:
- capture microphone audio
- convert to PCM16 mono 16kHz
- stream chunks continuously while listening
- render transcript events in real time
- handle reconnects gracefully
- keep blackout mode entirely client-side

## Privacy / Logging
For MVP:
- transcript logging should default to OFF
- server should avoid storing raw audio by default
- server should avoid persisting transcript text unless explicitly enabled later
- if logging is enabled later, it should be opt-in and clearly visible

## Open Choices
Still undecided:
- exact Linux host to prioritize first in practice (3060 box vs 2080 Ti box)
- exact NVIDIA Parakeet serving/runtime approach
- auth model for the API (none on LAN for dev vs token-based)
- whether to support multiple simultaneous clients in v1

## Proposed First Build Order
1. implement WebSocket server skeleton
2. implement session.start / session.stop / status messages
3. implement audio chunk ingestion
4. implement stub transcript stream
5. integrate NVIDIA Parakeet runtime
6. connect iPhone client to WebSocket backend
