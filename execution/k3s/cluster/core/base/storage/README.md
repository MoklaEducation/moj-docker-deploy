# Local-Path Storage Contract

Phase 5 retains the k3s-managed `local-path` StorageClass and does not take ownership of
that object. Namespace `ResourceQuota` objects constrain claim count and requested
storage for the class.

The class is node-local, has no replication, and currently uses `Delete` reclaim policy.
Deleting a claim can therefore delete its backing data. Phase 5 smoke tests use only
disposable claims and verify provisioning, pod-recreation persistence, reclaim behavior,
and cleanup.