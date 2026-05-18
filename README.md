# home_stack

Bare-metal Kubernetes homelab. Minisforum MS-01 nodes netboot Talos Linux from a PXE server running on a Synology NAS — no USB, no installer media, every node reprovisionable from the network.

This repo is the source of truth for provisioning and cluster config. It is kept deliberately honest: the commit history is the build log, including the parts that went wrong. The write-up of those parts is the blog series below.

📝 **[Building a Bare-Metal Kubernetes Homelab — Part 0](https://joesindel.com/posts/bare-metal-kubernetes-homelab-part-0/)**

## Architecture

- **Provisioning (L0):** Synology DSM Container Manager project — `dnsmasq` (proxyDHCP + TFTP, host-net, coexists with the existing router's DHCP) + `nginx` (HTTP boot assets). Firmware → iPXE chainload → Talos `metal` kernel/initramfs over HTTP.
- **OS:** Talos Linux v1.13.2 — immutable, API-driven, no SSH. Pinned via a content-addressed Image Factory schematic (`intel-ucode`).
- **Cluster:** single control-plane node today (`home-control-1`), scaling to 3 for HA etcd. Cilium CNI with `kubeProxyReplacement=true` via Talos KubePrism; kube-proxy disabled. Control-plane VIP for the API endpoint.
- **GitOps (planned):** Flux owns `infrastructure/`, Argo CD owns `apps/`, one owner per resource. SOPS-age for secrets.
- **Layering rule:** L0 provisioning / L1 cluster / L2 workloads — nothing lower depends on anything higher. The PXE host is never a cluster node.

## Layout

| path | what |
|---|---|
| `pxe/` | the PXE server — `compose.yaml`, `dnsmasq/` (Dockerfile + conf), `http/ipxe/boot.ipxe` |
| `schematic.yaml` | Talos Image Factory schematic (hashes to a deterministic ID) |
| `talos/cp-patch.yaml` | control-plane machine-config patch — the reproducible source |
| `cilium/install.sh` | Cilium Helm install with Talos-correct values |

Secrets (`talos/secrets.yaml`, `controlplane.yaml`, `worker.yaml`, `talosconfig`, `kubeconfig`) are gitignored. Configs regenerate deterministically from `cp-patch.yaml` + a persistent `secrets.yaml`.

## Hard-won lessons

- **iPXE scripts need `#!ipxe` at byte 0.** A copy-paste that prepended two spaces silently broke script detection — iPXE fetched it, then did nothing.
- **The Talos kernel cmdline must come from the Image Factory `cmdline-<platform>` asset.** Hand-rolling it fails the KSPP `systemRequirements` check (`slab_nomerge`, `pti=on`, …).
- **`talosctl gen config --force` rotates the CA every run.** Regenerating *after* applying orphans the node's trust (`x509: certificate signed by unknown authority`). Fix: a persistent `secrets.yaml` and always `--with-secrets`.
- **Linux interface names are not stable across boots on this hardware** (`enp88s0` → `enp87s0`). Bind networking by MAC via `deviceSelector.hardwareAddr`, never by interface name. Getting it wrong cascaded: static IP on the wrong NIC → live NIC DHCP-only → no NTP → wrong clock → TLS "expired certificate" → locked-out node.

## Status

Single-node cluster up: Talos v1.13.2, Kubernetes v1.36.0, Cilium 1.18.0, etcd bootstrapped. Next: rebuild-loop validation, GitOps bootstrap, nodes 2 & 3 for HA.
