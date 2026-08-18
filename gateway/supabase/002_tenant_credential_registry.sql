-- Wave 58 · Tenant Credential Registry & Rotation
-- Apply only after 001_public_intake_queue.sql in the dedicated gateway project.
-- No HMAC secret is stored here. Versions/status/nonces are non-secret control metadata.

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
    request_nonce text check (request_nonce is null or request_nonce ~ '^[0-9a-f]{32}$'),
    actor text not null default 'DESKTOP_ADMIN_HMAC' check (actor = 'DESKTOP_ADMIN_HMAC'),
    occurred_at timestamptz not null default now(),
    check (
        (action in ('ROTATE_INGRESS','ROTATE_PULL') and request_nonce is not null)
        or
        (action not in ('ROTATE_INGRESS','ROTATE_PULL') and request_nonce is null)
    )
);

create index if not exists binario_gateway_tenant_audit_tenant_time_idx
    on public.binario_gateway_tenant_audit (tenant_id, occurred_at desc, audit_id desc);
create unique index if not exists binario_gateway_tenant_audit_rotation_nonce_uq
    on public.binario_gateway_tenant_audit (tenant_id, request_nonce)
    where request_nonce is not null;

alter table public.binario_gateway_tenants enable row level security;
alter table public.binario_gateway_tenant_audit enable row level security;

revoke all on table public.binario_gateway_tenants from anon, authenticated;
revoke all on table public.binario_gateway_tenant_audit from anon, authenticated;
revoke all on sequence public.binario_gateway_tenant_audit_audit_id_seq from anon, authenticated;

grant select, insert, update on table public.binario_gateway_tenants to service_role;
grant select, insert on table public.binario_gateway_tenant_audit to service_role;
grant usage, select on sequence public.binario_gateway_tenant_audit_audit_id_seq to service_role;

create or replace function public.binario_gateway_tenant_register(p_tenant_id text)
returns public.binario_gateway_tenants
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
    v_row public.binario_gateway_tenants;
    v_inserted integer := 0;
begin
    if p_tenant_id !~ '^tenant_[0-9a-f]{24}$' then
        raise exception 'invalid tenant id';
    end if;
    insert into public.binario_gateway_tenants (tenant_id)
    values (p_tenant_id)
    on conflict (tenant_id) do nothing;
    get diagnostics v_inserted = row_count;
    if v_inserted = 1 then
        insert into public.binario_gateway_tenant_audit (tenant_id, action)
        values (p_tenant_id, 'REGISTER');
    end if;
    select * into strict v_row from public.binario_gateway_tenants where tenant_id = p_tenant_id;
    return v_row;
end;
$$;

-- Remove the pre-replay-hardening draft overload if this migration is retried on a development database.
drop function if exists public.binario_gateway_tenant_rotate(text, text);

create or replace function public.binario_gateway_tenant_rotate(
    p_tenant_id text,
    p_purpose text,
    p_request_nonce text
)
returns public.binario_gateway_tenants
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
    v_row public.binario_gateway_tenants;
    v_old integer;
    v_existing_purpose text;
begin
    if p_tenant_id !~ '^tenant_[0-9a-f]{24}$' then
        raise exception 'invalid tenant id';
    end if;
    if p_purpose not in ('ingress','pull') then
        raise exception 'invalid rotation purpose';
    end if;
    if p_request_nonce !~ '^[0-9a-f]{32}$' then
        raise exception 'invalid admin request nonce';
    end if;

    -- Lock this tenant before checking nonce history. Concurrent exact replays serialize here.
    select * into v_row
    from public.binario_gateway_tenants
    where tenant_id = p_tenant_id
    for update;
    if not found then
        raise exception 'tenant is not registered';
    end if;

    select purpose into v_existing_purpose
    from public.binario_gateway_tenant_audit
    where tenant_id = p_tenant_id and request_nonce = p_request_nonce
    limit 1;
    if found then
        if v_existing_purpose <> p_purpose then
            raise exception 'admin nonce was already used for another rotation purpose';
        end if;
        return v_row;
    end if;

    if v_row.status = 'REVOKED' then
        raise exception 'tenant is revoked';
    end if;

    if p_purpose = 'ingress' then
        if v_row.ingress_version >= 2147483647 then
            raise exception 'credential version exhausted';
        end if;
        v_old := v_row.ingress_version;
        update public.binario_gateway_tenants
        set ingress_version = ingress_version + 1, updated_at = now()
        where tenant_id = p_tenant_id
        returning * into v_row;
    else
        if v_row.pull_version >= 2147483647 then
            raise exception 'credential version exhausted';
        end if;
        v_old := v_row.pull_version;
        update public.binario_gateway_tenants
        set pull_version = pull_version + 1, updated_at = now()
        where tenant_id = p_tenant_id
        returning * into v_row;
    end if;

    insert into public.binario_gateway_tenant_audit (
        tenant_id, action, purpose, from_version, to_version, request_nonce
    ) values (
        p_tenant_id,
        case when p_purpose = 'ingress' then 'ROTATE_INGRESS' else 'ROTATE_PULL' end,
        p_purpose,
        v_old,
        v_old + 1,
        p_request_nonce
    );
    return v_row;
end;
$$;

create or replace function public.binario_gateway_tenant_revoke(p_tenant_id text)
returns public.binario_gateway_tenants
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
    v_row public.binario_gateway_tenants;
begin
    update public.binario_gateway_tenants
    set status = 'REVOKED', updated_at = now(), revoked_at = now()
    where tenant_id = p_tenant_id and status = 'ACTIVE'
    returning * into v_row;
    if found then
        insert into public.binario_gateway_tenant_audit (tenant_id, action) values (p_tenant_id, 'REVOKE');
        return v_row;
    end if;
    select * into v_row from public.binario_gateway_tenants where tenant_id = p_tenant_id;
    if not found then raise exception 'tenant is not registered'; end if;
    return v_row;
end;
$$;

create or replace function public.binario_gateway_tenant_reactivate(p_tenant_id text)
returns public.binario_gateway_tenants
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
    v_row public.binario_gateway_tenants;
begin
    update public.binario_gateway_tenants
    set status = 'ACTIVE',
        ingress_version = ingress_version + 1,
        pull_version = pull_version + 1,
        updated_at = now(),
        revoked_at = null
    where tenant_id = p_tenant_id
      and status = 'REVOKED'
      and ingress_version < 2147483647
      and pull_version < 2147483647
    returning * into v_row;
    if found then
        insert into public.binario_gateway_tenant_audit (tenant_id, action) values (p_tenant_id, 'REACTIVATE');
        return v_row;
    end if;
    select * into v_row from public.binario_gateway_tenants where tenant_id = p_tenant_id;
    if not found then raise exception 'tenant is not registered'; end if;
    if v_row.status = 'ACTIVE' then return v_row; end if;
    raise exception 'credential version exhausted';
end;
$$;

revoke all on function public.binario_gateway_tenant_register(text) from public, anon, authenticated;
revoke all on function public.binario_gateway_tenant_rotate(text, text, text) from public, anon, authenticated;
revoke all on function public.binario_gateway_tenant_revoke(text) from public, anon, authenticated;
revoke all on function public.binario_gateway_tenant_reactivate(text) from public, anon, authenticated;

grant execute on function public.binario_gateway_tenant_register(text) to service_role;
grant execute on function public.binario_gateway_tenant_rotate(text, text, text) to service_role;
grant execute on function public.binario_gateway_tenant_revoke(text) to service_role;
grant execute on function public.binario_gateway_tenant_reactivate(text) to service_role;

comment on table public.binario_gateway_tenants is
'BINARIO Marketing Wave 58 tenant credential control registry. Stores status and version counters only; never tenant HMAC secrets.';
comment on table public.binario_gateway_tenant_audit is
'Append-only non-secret audit trail for explicit tenant registration, replay-safe rotation and revocation actions.';
