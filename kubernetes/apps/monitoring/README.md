# monitoring — VictoriaMetrics + VictoriaLogs + Grafana

Production-grade, footprint-conscious observability for the cluster. Chosen over
kube-prometheus-stack for ~4–5× less RAM and ~3–7× less disk at equal retention,
a single operator/philosophy, and NFS-tolerant storage (matters at 3-node HA) —
while staying a Prometheus drop-in (MetricsQL is a PromQL superset; Grafana
dashboards, `ServiceMonitor`/`PrometheusRule`-equivalent CRDs all work).

| Component | Chart | What it is |
|---|---|---|
| `vm-k8s-stack` | `victoria-metrics-k8s-stack` 0.84.0 | VMSingle (TSDB, 30d) + vmagent + vmalert + vmalertmanager + Grafana + kube-state-metrics + node-exporter, via victoria-metrics-operator |
| `blackbox-exporter` | `prometheus-blackbox-exporter` 11.13.0 | HTTP probing for LAN-facing home-stack services, scraped through `VMProbe/home-stack-lan-http` |
| `victoria-logs` | `victoria-logs-single` 0.13.8 | Log backend (30d), PVC-backed, no S3. Service `victorialogs:9428` |
| `alloy` | `alloy` 1.10.0 | Log shipper DaemonSet (Promtail successor), collects via K8s API → VictoriaLogs |

- **Grafana:** http://192.168.86.254/ (Cilium LoadBalancer; pool is `.245–.254`,
  expand the `CiliumLoadBalancerIPPool` if you want more). Admin creds from the
  `monitoring-secrets` SOPS secret.
- **Prometheus/vmui/Alertmanager UIs:** not exposed — reach via
  `kubectl -n monitoring port-forward svc/<svc> <port>` or Headlamp.
- **Storage:** all on `local-path` (node-local). On a single node this is fine;
  metrics/logs history is lost if the node is rebuilt. VictoriaMetrics/Logs both
  tolerate NFS if you later want history to survive node failure at 3-node HA.

## Before first commit — encrypt the secret

`secret-monitoring.sops.yaml` is authored in plaintext. Set a real
`admin-password`, then encrypt in place (run from repo root):

```sh
sops -e -i kubernetes/apps/monitoring/secret-monitoring.sops.yaml
```

`.sops.yaml` already matches `kubernetes/**/*.sops.yaml`. Commit only the
encrypted file. Flux's `apps` Kustomization decrypts it at reconcile.

## Dashboards (provisioned automatically — no manual import)

Dashboard JSON is vendored under `dashboards/` and delivered as labeled
ConfigMaps, so Grafana can provision it without internet egress:

1. **Shipped by the chart:** node-exporter, kubelet, scheduler/controller-manager,
   alertmanager, and the VictoriaMetrics component dashboards.
2. **Kubernetes folder:** dotdc cluster/workload dashboards plus logs explorer.
3. **Synology folder:** SNMP NAS dashboard.
4. **Thor folder:** `thor-ai.json` for Thor host, Jetson, vLLM, and LiteLLM.
   Headroom is not included yet because its proxy metrics are loopback-only on
   Thor (`127.0.0.1:8787`); add a metrics-only bridge before scraping it from
   Kubernetes.
5. **Media folder:** `media-stack.json` for the Kubernetes `media` namespace.
6. **Overview folder:** `home-stack-overview.json` for the whole stack.

To add more: drop JSON into `dashboards/` and add a `configMapGenerator` entry
with label `grafana_dashboard: "1"` and a `grafana_folder` annotation.

## Deferred Thor AI Monitoring

The current Thor scrape target set is intentionally limited to endpoints already
exposed on Thor's Trusted LAN address:

- `192.168.86.11:9100` - node-exporter.
- `192.168.86.11:9102` - Jetson tegrastats exporter.
- `192.168.86.11:11437/metrics` - vLLM Nemotron server.
- `192.168.86.11:4001/metrics/` - LiteLLM metrics.

Headroom currently exposes useful Prometheus metrics at
`127.0.0.1:8787/metrics`, but the Kubernetes monitoring stack cannot scrape
Thor loopback. Later, add Headroom properly by creating a metrics-only bridge
or textfile collector on Thor, adding that target to `vmstaticscrape-thor.yaml`,
and extending `dashboards/thor-ai.json` with request, failure, active request,
token-savings, compression, overhead, latency, and TTFB panels.

## Enabling control-plane scrape (Talos) — later

Scrape of kube-scheduler / kube-controller-manager / etcd is **off** by default
because Talos binds them to localhost; leaving them on fires permanent alerts.
To enable:

1. Patch the control-plane machine config (`talos/cp-patch.yaml`):

   ```yaml
   cluster:
     controllerManager:
       extraArgs:
         bind-address: 0.0.0.0
     scheduler:
       extraArgs:
         bind-address: 0.0.0.0
     etcd:
       extraArgs:
         listen-metrics-urls: http://0.0.0.0:2381   # etcd metrics, no client cert
   ```

   Regenerate + apply (remember `--with-secrets talos/secrets.yaml`), then
   `talosctl apply-config`.

2. Flip the targets on in `vm-k8s-stack.yaml`:
   `kubeControllerManager.enabled: true`, `kubeScheduler.enabled: true`, and for
   etcd `kubeEtcd.enabled: true` with an http endpoint on `:2381`. Commit.

## Alerting

Alertmanager is enabled and mounted with `monitoring-secrets`. Delivered alerts
route to the `discord` receiver, which reads
`/etc/vm/secrets/monitoring-secrets/DISCORD_WEBHOOK_URL` via
`webhook_url_file`; the `Watchdog` dead-man's-switch is intentionally routed to
`blackhole` to avoid permanent noise.

The chart-generated VMAlertmanager name is shortened with
`alertmanager.name: am`. Without that, the operator-generated StatefulSet label
for the default release name exceeds Kubernetes' 63-byte label value limit.

Home-stack service reachability is covered by `blackbox-exporter.yaml`:

- `VMProbe/home-stack-lan-http` probes the LAN HTTP endpoints for Homepage,
  Tdarr, Sonarr, Radarr, Prowlarr, Bazarr, SABnzbd, qBittorrent, and Grafana.
- `VMRule/home-stack-service-alerts` pages on failed LAN probes, unavailable
  media deployments, and media pod restart storms.

Quick checks:

```sh
kubectl -n monitoring get vmalertmanager,vmprobe,vmrule
kubectl -n monitoring exec vmsingle-vm-k8s-stack-victoria-metrics-k8s-stack-d6f77476c54mjd -- \
  wget -qO- 'http://127.0.0.1:8428/api/v1/query?query=probe_success%7Bjob%3D%22home-stack-lan-http%22%7D'
```
