# Jordan Live Transcription iOS App

## Summary
An iPhone-first iOS app for Jordan that opens directly into live speech transcription. The app should feel immediate and low-friction: launch it, allow mic access, and see speech transcribed in near real time. The phone should function primarily as a client while a backend server accepts streamed audio and streams recognized words or transcript segments back live. Privacy matters, so the app includes a quick blackout mode triggered by shaking the phone, plus a settings screen with a simple logging toggle.

## Goal
Create a lightweight live transcription app that is fast to open, easy to use in conversation, and simple enough that Jordan does not need to manage modes or workflows.

## Primary User
Jordan.

## Core User Story
As a user, when I open the app, I want it to immediately start showing a live transcript of nearby speech so I can follow conversations without extra taps.

## MVP Requirements

### 1. Immediate live transcription
- When the app opens, it should enter live transcription mode automatically.
- Minimize startup friction: no extra "start" button in the main flow.
- If microphone permission has not been granted yet, request it and begin transcription immediately after approval.
- The iPhone app should capture microphone audio and stream it to a transcription backend.
- The backend should stream recognized words or transcript segments back in near real time.

### 2. iPhone-first UI
- Design primarily for iPhone.
- Main screen should prioritize readability:
  - large transcript text
  - high contrast
  - minimal chrome
  - minimal distractions
- The transcript view should feel like a single-purpose utility, not a dashboard.

### 3. Live transcript display
- Show streaming / incremental transcript updates while speech is happening.
- New text should appear automatically as speech is recognized.
- Transcript should remain visible on screen while the app is active.
- Optional scrollback is nice to have, but not required for MVP.

### 4. Privacy blackout gesture
- Shaking the phone up and down should blank the screen.
- In practice, this should likely be implemented as an in-app blackout/privacy overlay rather than literally turning the display off.
- A second shake, tap, or other simple gesture can restore the transcript view.
- Blackout mode should preserve transcription if technically feasible while the app remains in the foreground.

### 5. Settings screen
A simple settings menu should include at minimum:
- Logging: on/off
- Backend/server endpoint configuration later if needed
- Possibly transcript text size later, but not required for first pass

## Backend Architecture
- The app should act primarily as a client: capture microphone audio, send it to a backend, and render streaming transcript updates.
- The first backend target should be the Linux GPU box (`cameron-ms-7b17`) with 2x RTX 3060 12GB GPUs.
- A second Linux box with 2x 2080 Ti GPUs can be used later as an alternative or fallback host.
- The backend should use the standard NVIDIA Parakeet ecosystem / repo rather than MLX Audio Swift or llama.cpp.
- The backend should expose an API endpoint that accepts a live audio stream and returns streaming transcription results.
- On server startup, the backend should load the transcription model into memory immediately and keep it resident while the server is running, so incoming sessions do not pay model-load latency.
- The backend should warm the model at startup if needed, so first real user audio does not trigger a cold-start delay.
- The iPhone app should be written so the backend endpoint can be swapped or configured later if needed.
- Detailed wire protocol lives in `BACKEND_API.md`.

## Logging Behavior
- Logging toggle controls whether transcripts are persisted locally on the phone.
- If logging is OFF:
  - transcript exists only in the live session UI
  - app should avoid saving transcript history to disk
- If logging is ON:
  - app may persist transcripts locally for later review/export
- Server-side logging should also default to OFF.
- Default behavior should favor privacy.

## Suggested Main Screen Layout
- Full-screen transcript area
- Small subtle status indicator near top or bottom:
  - Connecting
  - Listening
  - Reconnecting
  - Backend unavailable
  - Blackout active
- Optional small settings button in a corner

## Non-Goals for MVP
- Speaker diarization
- Cloud sync
- Accounts
- Export workflows
- Rich transcript search
- Complex navigation
- iPad-first optimization

## Nice-to-Have Features
- Scroll back through prior transcript text with a finger
- Adjustable text size
- Haptic feedback when blackout mode toggles
- Copy current transcript
- Save/export transcript when logging is enabled
- Simple transcript session history
- Multiple backend profiles later

## Technical Notes
- Use a server-friendly Parakeet path, not MLX Audio Swift.
- Need to define the streaming protocol between app and backend.
- Need to decide what audio format the phone sends to the backend.
- Need to verify whether partial hypotheses can stream smoothly to the UI or whether updates arrive in chunks.
- Need to confirm latency and reconnect behavior over the network.
- Need to verify whether the regular NVIDIA Parakeet repo already supports the needed streaming mode directly, or whether we need a thin server wrapper around it.
- If blackout mode is implemented as a full-screen black overlay, keep rendering minimal to reduce distraction and preserve privacy.

## Product Principles
- Open fast
- Start immediately
- Be readable from a glance
- Preserve privacy with one quick gesture
- Keep settings minimal
- Make backend/network complexity invisible to Jordan

## Open Questions
- Which exact Linux box should host production first: the dual 3060 box or the dual 2080 Ti box?
- Does the NVIDIA Parakeet stack give us the needed streaming behavior directly, or do we need custom chunk/session orchestration?
- Should the app show partial text, finalized text, or both?
- Should logging default to OFF for privacy?
- Should blackout be toggled only by shake, or also by a visible button?
- Should restoring from blackout require a tap, another shake, or Face ID / passcode?
- Do we want a lightweight transcript buffer that can be scrolled during the current session, even if logging is off?

## Proposed MVP Definition
Version 1 is successful if Jordan can:
1. open the app,
2. immediately stream microphone audio to the Linux backend,
3. see nearby speech transcribed live,
4. shake to hide the screen when needed,
5. unhide it easily,
6. toggle transcript logging in settings.
