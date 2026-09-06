# Post-W99 Cloud Social Worker Deploy Contract

## Purpose

Package the already-tested one-shot cloud social worker so an external private scheduler can execute it while the operator Mac is offline. This increment defines the runtime contract only. It does **not** provision a hosting provider, Supabase project, Meta credential, schedule, release, physical UAT candidate, or W100 authority.

## Runtime shape

The container is intentionally not a web service:

- Python 3.12 slim runtime.
- No third-party Python dependencies.
- No `EXPOSE` instruction.
- No HTTP server or public execution endpoint.
- Runs as UID/GID `10001` rather than root.
- Executes exactly one worker iteration and exits.
- Reuses `binario_marketing.cloud_social_worker`; there is no second Meta implementation.
- Includes only `src/`, `gateway/`, and the deploy runner required for execution.

Build from the repository root:

```sh
docker build -f deploy/cloud-social-worker/Dockerfile -t binario-cloud-social-worker .
```

The image entrypoint is:

```text
./scripts/run_cloud_social_worker_once.sh
```

which finally executes:

```text
python -m binario_marketing.cloud_social_worker
```

## Required secret/configuration inputs

The runner accepts only two explicit authority modes:

- `BINARIO_SOCIAL_WORKER_ENABLED=0`: configuration smoke. The Python worker returns `DISABLED` before resolving Meta credentials or claiming database work.
- `BINARIO_SOCIAL_WORKER_ENABLED=1`: real one-shot execution authority.

Both modes fail closed unless these inputs are present:

- `BINARIO_SOCIAL_WORKER_TENANTS` contains the explicit tenant allowlist.
- `SUPABASE_URL` is present and uses HTTPS.
- One of `SUPABASE_SECRET_KEY` or `SUPABASE_SERVICE_ROLE_KEY` is present.
- `META_ACCESS_TOKEN` is present for the headless deployment contract.

Optional bounded worker variables remain owned by the worker implementation:

- `BINARIO_SOCIAL_WORKER_LIMIT`
- `BINARIO_SOCIAL_WORKER_LEASE_SECONDS`
- `META_GRAPH_API_VERSION`

The wrapper checks only presence, explicit authority mode and the HTTPS requirement. It never echoes credential values. The Python worker performs the canonical tenant, numeric, Meta and lease validation.

### Safe preflight

Before enabling publication authority, launch the exact production image once with `BINARIO_SOCIAL_WORKER_ENABLED=0` and the intended environment bindings. A successful run exits `0` with a secret-free `DISABLED` result and `claimed=0`. This verifies the container entrypoint and static deployment configuration without touching Meta or claiming a queued publication.

Only after that preflight should the scheduled service switch to `BINARIO_SOCIAL_WORKER_ENABLED=1`.

## Scheduler contract

A compatible scheduler should:

1. Start this container on a recurring private schedule.
2. Inject secrets through the hosting provider's secret/environment mechanism.
3. Set `BINARIO_SOCIAL_WORKER_ENABLED=1` only after the disabled preflight succeeds.
4. Allow the process to exit after each invocation.
5. Treat a non-zero process exit as an operational signal requiring inspection.
6. Never wrap this process in a public HTTP endpoint merely to trigger it.
7. Avoid overlapping invocations when possible; the Supabase atomic lease protocol remains the authoritative concurrency boundary if overlap occurs.

A 1–5 minute cadence is operationally reasonable for social scheduling, but this repository deliberately does not codify provider-specific cron syntax until the actual hosting target is selected and connected.

## Authority and duplicate protection

The deploy contract does not change publication authority rules:

- Desktop hands a publication off as `DELEGATED` before remote enqueue.
- The local scheduler cannot publish `DELEGATED` rows.
- Cloud worker claims only already-approved jobs from explicit tenant allowlists.
- Provider side effects are checkpointed before Meta calls.
- A crash after provider start is terminal/ambiguous and never automatically republishes.
- Completion/failure remains lease-bound through Supabase RPCs.

## Provisioning boundary

No connected Supabase project has yet been identified as the canonical MERCADEO APP backend. Therefore this increment must not apply the queue migrations to any existing unrelated project.

Likewise, the repository retains exactly the three canonical workflows:

- `ci.yml`
- `full-mac-app.yml`
- `persistent-release.yml`

External scheduling belongs to the deployment platform, not to a fourth GitHub Actions workflow.

## Future activation sequence

Once a hosting target and the correct Supabase project are explicitly identified:

1. Apply the existing social queue migrations to that Supabase project.
2. Configure the gateway/service-role secret only in server-side hosting.
3. Configure `META_ACCESS_TOKEN` in the private worker service.
4. Configure the explicit tenant allowlist.
5. Build this Dockerfile from the post-W99 development branch/revision.
6. Run the exact image with `BINARIO_SOCIAL_WORKER_ENABLED=0` and confirm the secret-free `DISABLED`/`claimed=0` result.
7. Set `BINARIO_SOCIAL_WORKER_ENABLED=1` and exercise one non-production/test publication path.
8. Add a private recurring schedule only after the one-shot execution is verified.

This remains post-W99 development work and has no authority over the frozen `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53` candidate.
