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

1. Already HEVC → mark processed (no-op replace), skip
2. Overall bitrate < 6 Mbps → already efficient, skip
3. Drop `fre`/`fra` audio tracks, **only when a non-French audio track
   exists** (guarded by a Check Stream Property branch so French-original
   shows are never left silent; untagged audio counts as "keep")
4. Encode: `hevc_qsv -global_quality 20 -preset slow`, hardware decode,
   audio/subs copied, container mkv (force conform)
5. Replace the original **only if** the new file is 10–90% of the source
   size; otherwise fail the flow visibly and keep the original

## Node worker limits

Internal node (`TdarrInternalNode`): `transcodegpu: 1`, everything else 0.
Set via `POST /api/v2/alter-worker-limit`. Runs 24/7 (no schedule) — the
worker iGPU is otherwise idle and one QSV stream is negligible NAS I/O.

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
