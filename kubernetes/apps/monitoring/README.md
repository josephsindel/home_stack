# monitoring — VictoriaMetrics + VictoriaLogs + Grafana

Production-grade, footprint-conscious observability for the cluster. Chosen over
kube-prometheus-stack for ~4–5× less RAM and ~3–7× less disk at equal retention,
a single operator/philosophy, and NFS-tolerant storage (matters at 3-node HA) —
while staying a Prometheus drop-in (MetricsQL is a PromQL superset; Grafana
dashboards, `ServiceMonitor`/`PrometheusRule`-equivalent CRDs all work).

| Component | Chart | What it is |
|---|---|---|
| `vm-k8s-stack` | `victoria-metrics-k8s-stack` 0.84.0 | VMSingle (TSDB, 30d) + vmagent + vmalert + vmalertmanager + Grafana + kube-state-metrics + node-exporter, via victoria-metrics-operator |
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

Two layers, both as code:

1. **Shipped by the chart:** node-exporter, kubelet, scheduler/controller-manager,
   alertmanager, and the VictoriaMetrics component dashboards.
2. **dotdc cluster/workload overview** (added in `vm-k8s-stack.yaml` under
   `grafana.dashboards`): `k8s-views-global`, `-namespaces`, `-nodes`, `-pods`,
   `k8s-system-api-server`, `k8s-system-coredns` — pulled from GitHub at pod start
   into the **Kubernetes** folder, auto-bound to the `VictoriaMetrics` datasource.

The Grafana pod needs egress to `raw.githubusercontent.com` for layer 2. If that's
blocked, switch to committing the dashboard JSON as ConfigMaps labeled
`grafana_dashboard: "1"` (the sidecar is enabled, `searchNamespace: ALL`) — no
egress required.

To add more: append to `grafana.dashboards.grafana-dashboards-kubernetes` (by
`url:` or `gnetId:`+`revision:`), or drop a labeled ConfigMap.

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

## Alerting — disabled (vmalert evaluates, nothing routes)

Alertmanager is **disabled** (`alertmanager.enabled: false`); vmalert still
evaluates rules (visible in its UI) but has a blackhole notifier
(`vmalert.spec.extraArgs.notifier.blackhole: "true"`), so nothing is delivered.
The `Watchdog` alert fires permanently by design (dead-man's-switch) — harmless
with no receiver.

To wire a real channel:

1. Set `alertmanager.enabled: true` and add `spec.secrets: [monitoring-secrets]`.
2. Remove the vmalert `notifier.blackhole` arg (vmalert auto-targets alertmanager).
3. Put the webhook in `monitoring-secrets` (`DISCORD_WEBHOOK_URL` placeholder is
   there), re-encrypt, and add a `discord`/`ntfy`/`pushover` receiver under
   `alertmanager.config` reading it via `webhook_url_file`
   (`/etc/vm/secrets/monitoring-secrets/DISCORD_WEBHOOK_URL`).
