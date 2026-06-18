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

- **Grafana:** http://192.168.86.245/ (Cilium LoadBalancer; pool is `.245–.254`,
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

## Dashboards (import after Grafana is up)

The chart ships the VictoriaMetrics + kubernetes-mixin dashboards. Add the
actively-maintained community set by importing these IDs in Grafana
(Dashboards → Import), datasource = VictoriaMetrics:

- **1860** Node Exporter Full
- **21742** kube-state-metrics v2 (object health)
- **dotdc/grafana-dashboards-kubernetes** (k8s-views-global / -nodes / -pods / -namespaces)

To manage dashboards as code later: drop a ConfigMap labeled
`grafana_dashboard: "1"` (the sidecar is already enabled, `searchNamespace: ALL`).

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

## Wiring an alert channel — later

Alertmanager boots with a `blackhole` receiver (no spam). To route alerts:

1. Put the webhook in `monitoring-secrets` (`DISCORD_WEBHOOK_URL` placeholder is
   already there), re-encrypt.
2. Uncomment the `discord` receiver in `vm-k8s-stack.yaml` (it reads the webhook
   from the mounted secret via `webhook_url_file`) and point `route.receiver` at
   it. ntfy/Pushover work the same way (Pushover natively, ntfy via a relay).
