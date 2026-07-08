# Tdarr runtime configuration (H.265 re-encode project)

Tdarr runs in-cluster (`kubernetes/apps/media/tdarr.yaml`, UI at
http://192.168.86.237:8265) with all state on PVCs (`tdarr-server`,
`tdarr-configs`, `tdarr-cache`, `tdarr-logs`, local-path on `home-worker-1`).
The settings below live in Tdarr's own DB (SQLite on the `tdarr-server` PVC),
NOT in Flux-applied manifests — this doc + the exported flow JSON are the
restore reference. Configured 2026-07-03 via the `/api/v2/cruddb` API.

## Library "TV" (`w4d2bQTdS`)

- Source: `/mnt/nas/content/tv` (NFS `media` PVC mounted at `/mnt/nas/content`)
- Transcode cache: `/temp` (the `tdarr-cache` PVC — REQUIRED, was unset)
- Decision maker: **Flows** (`settingsFlows: true`, `settingsPlugin: false`),
  `flowId: tvHevcQsvCq20`; classic plugin stack + HandBrake preset disabled
- Scanner: folder watching + hourly scheduled scan, ~8.1k files known

## Flow `tvHevcQsvCq20` — "TV HEVC QSV CQ20"

Export: [`tdarr-flow-tvHevcQsvCq20.json`](tdarr-flow-tvHevcQsvCq20.json).
Restore by inserting the JSON into `FlowsJSONDB` via `/api/v2/cruddb`
(mode `insert`) or by rebuilding in the UI.

Logic:

1. Start an FFmpeg command for every TV file and ensure an English AAC stereo
   compatibility stream exists. If no English audio stream is tagged, Tdarr
   falls back to an undefined-language stream. Existing AAC stereo streams are
   left untouched.
2. Prefer AAC stereo as the default audio stream while preserving surround
   tracks as secondary audio. This is implemented by a custom flow function that
   reorders audio streams and writes FFmpeg disposition flags.
3. Already HEVC → skip video encoding, but run a compatibility remux when AAC
   stereo was added. The remux path must land within 95-125% of the source size
   or the flow fails visibly and keeps the original.
4. Overall bitrate < 6 Mbps → skip video encoding, but use the same AAC
   compatibility remux path when needed.
5. Drop `fre`/`fra` audio tracks, **only when a non-French audio track
   exists** (guarded by a Check Stream Property branch so French-original
   shows are never left silent; untagged audio counts as "keep")
6. Encode: `hevc_qsv -global_quality 20 -preset slow`, hardware decode,
   container mkv (force conform), copy existing streams except intentional
   audio changes from the flow
7. Replace the original **only if** the new file is 10–90% of the source
   size; otherwise fail the flow visibly and keep the original

This AAC compatibility step was added after a Plex Fire TV/Android direct-play
failure on `Star Trek: Lower Decks` S01E03 where the server could read the file
but the client stuck at media time 0 on an EAC3-only MKV. The goal is to keep
video unchanged unless the HEVC branch is already selected, while making direct
play less brittle on clients that handle AAC stereo more consistently.

## Node worker limits

Internal node (`TdarrInternalNode`): `transcodegpu: 2`, everything else 0.
Set via `POST /api/v2/alter-worker-limit`. Runs 24/7 (no schedule) — the
worker iGPU is otherwise idle and the QSV streams are bounded to protect NAS
I/O.

## Tdarr Pro key

Stored in `SettingsGlobalJSONDB.tdarrKey` (server PVC → survives restarts).
Key value lives in Joe's purchase email / keys.env — NOT in this public repo.
Verify Pro state: `POST /api/v2/auth-status` with `{"data":{"saU":true}}` → `true`.

## Useful API snippets

```bash
# read library / flow / global settings
curl -s -X POST http://192.168.86.237:8265/api/v2/cruddb \
  -H 'Content-Type: application/json' \
  -d '{"data":{"collection":"FlowsJSONDB","mode":"getById","docID":"tvHevcQsvCq20","obj":{}}}'

# live worker status
curl -s http://192.168.86.237:8265/api/v2/get-nodes
```
