# DOM Safety Model

The plugin only accepts structured mutation actions. It does not accept arbitrary HTML patches.

Safety controls:

- action allowlist
- protected URL blocking
- selector validation
- duplicate anchor prevention
- no editing inside existing anchors, scripts, or styles
- rollback snapshots for content mutations
