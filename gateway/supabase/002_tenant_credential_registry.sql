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

create or replace function public.binario_gateway_tenant_rotate(p_tenant_id text, p_purpose text)
returns public.binario_gateway_tenants
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
    v_row public.binario_gateway_tenants;
    v_old integer;
begin
    if p_tenant_id !~ '^tenant_[0-9a-f]{24}$' then
        raise exception 'invalid tenant id';
    end if;
    if p_purpose = 'ingress' then
        update public.binario_gateway_tenants
        set ingress_version = ingress_version + 1, updated_at = now()
        where tenant_id = p_tenant_id and status = 'ACTIVE' and ingress_version < 2147483647
        returning ingress_version - 1, * into v_old, v_row;
    elsif p_purpose = 'pull' then
        update public.binario_gateway_tenants
        set pull_version = pull_version + 1, updated_at = now()
        where tenant_id = p_tenant_id and status = 'ACTIVE' and pull_version < 2147483647
        returning pull_version - 1, * into v_old, v_row;
    else
        raise exception 'invalid rotation purpose';
    end if;
    if not found then
        if exists (select 1 from public.binario_gateway_tenants where tenant_id = p_tenant_id and status = 'REVOKED') then
            raise exception 'tenant is revoked';
        elsif exists (select 1 from public.binario_gateway_tenants where tenant_id = p_tenant_id) then
            raise exception 'credential version exhausted';
        else
            raise exception 'tenant is not registered';
        end if;
    end if;
    insert into public.binario_gateway_tenant_audit (tenant_id, action, purpose, from_version, to_version)
    values (
        p_tenant_id,
        case when p_purpose = 'ingress' then 'ROTATE_INGRESS' else 'ROTATE_PULL' end,
        p_purpose,
        v_old,
        v_old + 1
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
revoke all on function public.binario_gateway_tenant_rotate(text, text) from public, anon, authenticated;
revoke all on function public.binario_gateway_tenant_revoke(text) from public, anon, authenticated;
revoke all on function public.binario_gateway_tenant_reactivate(text) from public, anon, authenticated;

grant execute on function public.binario_gateway_tenant_register(text) to service_role;
grant execute on function public.binario_gateway_tenant_rotate(text, text) to service_role;
grant execute on function public.binario_gateway_tenant_revoke(text) to service_role;
grant execute on function public.binario_gateway_tenant_reactivate(text) to service_role;

comment on table public.binario_gateway_tenants is
'BINARIO Marketing Wave 58 tenant credential control registry. Stores status and version counters only; never tenant HMAC secrets.';
comment on table public.binario_gateway_tenant_audit is
'Append-only non-secret audit trail for explicit tenant registration, rotation and revocation actions.';
