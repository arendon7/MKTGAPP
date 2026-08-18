-- Wave 58 · Tenant Credential Registry & Rotation
-- Apply only after 001_public_intake_queue.sql in the dedicated gateway project.
-- No HMAC secret is stored here. Versions/status are non-secret control metadata.

create table if not exists public.binario_gateway_tenants (
    tenant_id text primary key check (tenant_id ~ '^tenant_[0-9a-f]{24}$'),
    status text not null default 'ACTIVE' check (status in ('ACTIVE','REVOKED')),
    ingress_version integer not null default 1 check (ingress_version >= 1 and ingress_version <= 2147483647),
    pull_version integer not null default 1 check (pull_version >= 1 and pull_version <= 2147483647),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    revoked_at timestamptz,
    check ((status = 'ACTIVE' and revoked_at is null) or (status = 'REVOKED' and revoked_at is not null))
);

create table if not exists public.binario_gateway_tenant_audit (
    audit_id bigint generated always as identity primary key,
    tenant_id text not null check (tenant_id ~ '^tenant_[0-9a-f]{24}$'),
    action text not null check (action in ('REGISTER','ROTATE_INGRESS','ROTATE_PULL','REVOKE','REACTIVATE')),
    purpose text check (purpose is null or purpose in ('ingress','pull')),
    from_version integer check (from_version is null or from_version >= 1),
    to_version integer check (to_version is null or to_version >= 1),
    actor text not null default 'DESKTOP_ADMIN_HMAC' check (actor = 'DESKTOP_ADMIN_HMAC'),
    occurred_at timestamptz not null default now()
);

create index if not exists binario_gateway_tenant_audit_tenant_time_idx
    on public.binario_gateway_tenant_audit (tenant_id, occurred_at desc, audit_id desc);

alter table public.binario_gateway_tenants enable row level security;
alter table public.binario_gateway_tenant_audit enable row level security;

revoke all on table public.binario_gateway_tenants from anon, authenticated;
revoke all on table public.binario_gateway_tenant_audit from anon, authenticated;
revoke all on sequence public.binario_gateway_tenant_audit_audit_id_seq from anon, authenticated;

grant select, insert, update on table public.binario_gateway_tenants to service_role;
grant select, insert on table public.binario_gateway_tenant_audit to service_role;
grant usage, select on sequence public.binario_gateway_tenant_audit_audit_id_seq to service_role;

comment on table public.binario_gateway_tenants is
'BINARIO Marketing Wave 58 tenant credential control registry. Stores status and version counters only; never tenant HMAC secrets.';
comment on table public.binario_gateway_tenant_audit is
'Append-only non-secret audit trail for explicit tenant registration, rotation and revocation actions.';
