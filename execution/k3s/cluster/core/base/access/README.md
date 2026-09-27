# Cluster Core Access

Phase 5 uses two client-certificate identities:

- `mokla-platform-operator` observes cluster state and performs bounded pod operations in
  managed namespaces. It cannot read Secrets or modify nodes or CRDs.
- `mokla-cluster-core` reconciles Phase 5 namespace policy objects and runs disposable
  validation in `judge-test`. It cannot read Secrets, modify nodes or CRDs, or create
  workloads in other managed namespaces.

Routine `cluster-core` check and apply use the restricted automation kubeconfig. The
bootstrap administrator is required only to establish or deliberately update RBAC and to
approve replacement client certificates. Generated kubeconfigs are ignored, mode `0600`,
and valid for 30 days in the test environment.

Run the explicit access operation when credentials approach expiry or a reviewed RBAC
change is intended:

```bash
./execution/k3s/cluster/core/scripts/access.sh apply test
```

Review the rendered RBAC diff before invoking this break-glass operation. Ordinary core
reconciliation refuses RBAC drift instead of escalating its own permissions.