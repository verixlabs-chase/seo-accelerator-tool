# Execution Plugin Infrastructure

WordPress mutation delivery now includes plugin health gating and mutation safety validation before requests leave the platform. The platform blocks execution when a site plugin is marked unhealthy and records health transitions through provider telemetry state.

Safety controls include:

- protected URL blocking
- max mutations per page
- DOM selector validation
- rollback payload verification
