-- Wave 56 · Public Intake Gateway durable queue
-- Apply to a dedicated Supabase project used only by the public gateway.

create table if not exists public.binario_public_intake_queue (
    tenant_id text not null,
    event_id text not null,
    received_at timestamptz not null,
    expires_at timestamptz not null,
    body_json jsonb,
    body_sha256 text not null check (body_sha256 ~ '^[0-9a-f]{64}$'),
    status text not null default 'PENDING' check (status in ('PENDING','ACKED','EXPIRED')),
    acked_at timestamptz,
    primary key (tenant_id, event_id),
    check (tenant_id ~ '^tenant_[0-9a-f]{24}$'),
    check (event_id ~ '^evt_[0-9a-f]{32}$'),
    check ((status = 'PENDING' and body_json is not null) or (status in ('ACKED','EXPIRED') and body_json is null))
);

create index if not exists binario_public_intake_queue_pending_idx
    on public.binario_public_intake_queue (tenant_id, status, received_at, event_id);

alter table public.binario_public_intake_queue enable row level security;
revoke all on table public.binario_public_intake_queue from anon, authenticated;
grant select, insert, update on table public.binario_public_intake_queue to service_role;

comment on table public.binario_public_intake_queue is
'BINARIO Marketing Wave 56 signed intake queue. Public/anon roles have no table access. Gateway backend secret only.';
comment on column public.binario_public_intake_queue.body_json is
'PII-bearing lead payload. Redacted to NULL on ACK or expiry.';
