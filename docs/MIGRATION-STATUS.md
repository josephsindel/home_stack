# Home-lab → Kubernetes migration status

Migration of home-lab services from Docker (mediaserver/thor/pi/synology) onto the
2-node **Talos** cluster via **Flux GitOps**. This doc reflects a full live-state
validation on **2026-06-19**.

## Live-state validation (2026-06-19)

| Check | Result |
|---|---|
| Flux kustomizations (apps/config/controllers/flux-system) | ✅ all READY |
| HelmReleases (21) | ✅ all READY |
| Pods (all namespaces) | ✅ all Running/Ready |
| LoadBalancer services | ✅ all have IPs (.235–.254 pool) |
| Tailscale ingresses + proxies | ✅ homepage + romm up |
| mediaserver survivors | ✅ all healthy |
| Homepage dashboard endpoints | ✅ 24/24 reachable, 0 red |

## Running in Kubernetes

| Service | Namespace | LAN LB IP | Tailnet | Notes |
|---|---|---|---|---|
| Homepage (dashboard) | homepage | 192.168.86.235 | homepage.tailc89bc2.ts.net | Tailscale **Ingress** (serve), not L4 expose |
| RomM (+ MariaDB) | romm | 192.168.86.236 | romm.tailc89bc2.ts.net | DB on node-local local-path; library on NFS |
| Headlamp (Flux UI) | headlamp | 192.168.86.245 | — | token: `kubectl create token headlamp -n headlamp` |
| SearXNG | searxng | 192.168.86.246 | — | |
| n8n | n8n | 192.168.86.247 | — | local-path PVC |
| Sonarr / Radarr / Prowlarr | media | .248 / .249 / .250 | — | configs on local-path; library on NFS |
| Bazarr / SABnzbd / qBittorrent | media | .251 / .252 / .253 | — | qBit via gluetun VPN sidecar |
| flaresolverr / unpackerr | media | ClusterIP / none | — | |
| Grafana (VictoriaMetrics stack) | monitoring | 192.168.86.254 | — | + VictoriaLogs, Alloy, snmp-exporter |
| Tailscale operator + proxies | tailscale | — | — | exposes services to the tailnet |

Platform: Cilium (LB-IPAM + L2, kube-proxy replacement), cert-manager, csi-driver-nfs,
local-path-provisioner, Flux (flux-operator).

## Staying on their hosts (by design — NOT migration candidates)

| Service | Host | Why it stays |
|---|---|---|
| Plex | mediaserver | Native (non-Docker) install; HW transcode |
| Home Assistant | mediaserver | `NetworkMode=host` + D-Bus for mDNS/Zeroconf/Matter discovery + Bluetooth |
| Project NOMAD (+ Kiwix/CyberChef/Flatnotes/Kolibri) | mediaserver | Orchestrates its modules via the Docker socket; Talos has no Docker |
| Healthchecks | mediaserver | Out of migration scope |
| traefik | mediaserver | Still fronts Plex/NOMAD/DSM/WUD tailnet routes |
| glances, wud | each host | Host-monitoring agents (report the host they run on) |
| Full AI stack (Ollama, Open WebUI, LiteLLM, Langfuse, ComfyUI, piper, openedai-speech, …) | thor | GPU/Tailscale-coupled → **own migration track**, see below |
| DAKboard, Pi-hole | livingroom-pi | |

## Decommissioned (migrated → old copies removed)

Stopped + removed on mediaserver (`profiles: ["disabled"]`, config kept for revert):
sonarr, radarr, prowlarr, bazarr, sabnzbd, qbittorrent, gluetun, unpackerr,
flaresolverr, homepage, romm, romm-db.

## Ditched (no longer wanted)

- **Jellyfin** — redundant with Plex; also would have needed the Talos i915 ext + node reboots.
- **unifi-edge-exporter** — Edge IO dashboard widget dropped.

## Milestones

| | Status |
|---|---|
| M0 Prep & reconcile | ✅ |
| M1 Platform (Flux/SOPS/Cilium/cert-manager/CSI) | ✅ |
| M1b SearXNG pilot | ✅ |
| M2 Easy wave (flaresolverr, unpackerr, n8n, Homepage) | ✅ |
| M3 *arr media stack on NFS | ✅ |
| M4 Hard knots (gluetun ✅; Jellyfin descoped; Langfuse/LiteLLM → thor track) | ✅ |
| **M5 DNS HA + decommission** | 🟡 decommission ✅, **DNS HA pending** |
| Thor migration track | 🔮 future, separate effort |

## What remains

1. **DNS HA (M5)** — Pi-hole is a single point of failure on the living-room Pi.
   Plan: stand up a second resolver in-cluster behind a LoadBalancer VIP and hand
   out two DNS servers via UniFi DHCP.
2. **Thor migration track** — decide per-service whether to move thor's AI/TTS
   stack into the cluster (most is GPU/Tailscale-coupled and likely stays).
3. **Optional cleanup** — dead traefik routes remain on mediaserver for the
   migrated/ditched services (sonarr/romm/jellyfin/etc.); harmless, cosmetic.
4. **Optional** — RomM's deep `ngc` (Legend of Zelda Collection) read-only ROM
   mount was not replicated (only `N3DS → 3ds`); re-add if that platform is needed.

## Key architecture notes / gotchas

- **Tailnet exposure:** use a Tailscale **Ingress** (`ingressClassName: tailscale`),
  NOT the `tailscale.com/expose` L4 annotation — the latter DNATs to the Service
  ClusterIP, which Cilium kube-proxy-replacement only translates at the socket
  level, so DNAT-forwarded tailnet packets are dropped (ping works, TCP times out).
- **Dashboard link convention:** `href` = browser-side (Tailscale/`.ts.net` OK);
  `widget`/`siteMonitor` = fetched by the pod (no Tailscale) → k8s DNS for
  in-cluster, LAN IPs for host services (.10 ms / .11 thor / .12 nas / .13 pi).
- **Databases** use node-local `local-path` storage — NFS corrupts MySQL/MariaDB/Redis.
- **bjw-s app-template** prefixes the release name to non-primary service keys
  (key `db` → service `romm-db`).
- **Secrets** are SOPS+age (cluster key + joe-mac key); the repo is public, so no
  plaintext keys — dashboard API keys are injected via `{{HOMEPAGE_VAR_*}}` env.
