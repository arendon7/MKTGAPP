-- Post-W99 remote social publish queue.
-- Server-only state. This table is intentionally separate from public lead intake.

create table if not exists public.binario_social_publish_queue (
    tenant_id text not null,
    publication_id text not null,
    body_json jsonb not null,
    body_sha256 text not null,
    scheduled_for timestamptz not null,
    available_at timestamptz not null,
    status text not null default 'PENDING',
    attempts smallint not null default 0,
    lease_worker_id text,
    lease_sha256 text,
    lease_expires_at timestamptz,
    remote_id text,
    last_error text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (tenant_id, publication_id),
    constraint binario_social_tenant_id_shape check (tenant_id ~ '^tenant_[0-9a-f]{24}$'),
    constraint binario_social_publication_id_shape check (publication_id ~ '^[0-9a-f]{32}$'),
    constraint binario_social_body_sha_shape check (body_sha256 ~ '^[0-9a-f]{64}$'),
    constraint binario_social_status check (status in ('PENDING','LEASED','PUBLISHED','FAILED','CANCELLED')),
    constraint binario_social_attempts check (attempts between 0 and 5),
    constraint binario_social_lease_shape check (
        (status = 'LEASED' and lease_worker_id is not null and lease_sha256 ~ '^[0-9a-f]{64}$' and lease_expires_at is not null)
        or
        (status <> 'LEASED' and lease_worker_id is null and lease_sha256 is null and lease_expires_at is null)
    )
);

create index if not exists binario_social_publish_due_idx
    on public.binario_social_publish_queue (tenant_id, available_at, publication_id)
    where status = 'PENDING';

create index if not exists binario_social_publish_lease_idx
    on public.binario_social_publish_queue (tenant_id, lease_expires_at)
    where status = 'LEASED';

alter table public.binario_social_publish_queue enable row level security;
revoke all on table public.binario_social_publish_queue from anon, authenticated;

comment on table public.binario_social_publish_queue is
    'Server-only post-W99 social publication queue. Never stores Meta/API credentials.';
