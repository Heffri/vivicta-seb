# ElevenLabs UI Orb

The fragment shader in `src/components/ask/orb-shader.ts` is adapted from the
[ElevenLabs UI Orb](https://github.com/elevenlabs/ui/blob/23c31bd3088814215a8b5d0bfb56b327cad1a578/apps/www/registry/elevenlabs-ui/ui/orb.tsx),
commit `23c31bd3088814215a8b5d0bfb56b327cad1a578` (MIT).
Copyright (c) 2025 Eleven Labs Inc.

The complete license is included in `public/licenses/elevenlabs-ui.txt` and ships
with the frontend. Our renderer uses a local procedural texture, lazy-loads
Three.js, pauses when hidden, respects reduced motion, and provides a static
fallback when WebGL is unavailable. It does not contact ElevenLabs or use audio.
