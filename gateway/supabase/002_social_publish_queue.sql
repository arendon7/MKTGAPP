-- Post-W99 remote social publish queue.
-- Server-only state. This table is intentionally separate from public lead intake.

create extension if not exists pgcrypto;

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

-- Atomic distributed claim. Every worker receives a raw one-time lease token while
-- only its SHA-256 is stored. SKIP LOCKED prevents two workers claiming the same row.
create or replace function public.binario_claim_social_publish_jobs(
    p_tenant_id text,
    p_worker_id text,
    p_now timestamptz,
    p_limit integer default 10,
    p_lease_seconds integer default 120
)
returns table (
    tenant_id text,
    publication_id text,
    body_json jsonb,
    body_sha256 text,
    attempt smallint,
    lease_token text,
    lease_expires_at timestamptz
)
language plpgsql
security definer
set search_path = public
as $$
declare
    candidate record;
    raw_token text;
    expiry timestamptz;
begin
    if p_tenant_id !~ '^tenant_[0-9a-f]{24}$' then
        raise exception 'invalid tenant id';
    end if;
    if p_worker_id !~ '^worker_[0-9a-f]{16}$' then
        raise exception 'invalid worker id';
    end if;
    if p_limit < 1 or p_limit > 20 then
        raise exception 'invalid claim limit';
    end if;
    if p_lease_seconds < 30 or p_lease_seconds > 900 then
        raise exception 'invalid lease duration';
    end if;

    update public.binario_social_publish_queue q
       set status = case when q.attempts >= 5 then 'FAILED' else 'PENDING' end,
           available_at = p_now,
           lease_worker_id = null,
           lease_sha256 = null,
           lease_expires_at = null,
           last_error = 'worker lease expired before completion',
           updated_at = p_now
     where q.tenant_id = p_tenant_id
       and q.status = 'LEASED'
       and q.lease_expires_at <= p_now;

    for candidate in
        select q.tenant_id, q.publication_id
          from public.binario_social_publish_queue q
         where q.tenant_id = p_tenant_id
           and q.status = 'PENDING'
           and q.available_at <= p_now
           and q.attempts < 5
         order by q.available_at, q.scheduled_for, q.publication_id
         for update skip locked
         limit p_limit
    loop
        raw_token := encode(gen_random_bytes(32), 'hex');
        expiry := p_now + make_interval(secs => p_lease_seconds);

        update public.binario_social_publish_queue q
           set status = 'LEASED',
               attempts = q.attempts + 1,
               lease_worker_id = p_worker_id,
               lease_sha256 = encode(digest(raw_token, 'sha256'), 'hex'),
               lease_expires_at = expiry,
               last_error = null,
               updated_at = p_now
         where q.tenant_id = candidate.tenant_id
           and q.publication_id = candidate.publication_id;

        return query
        select q.tenant_id,
               q.publication_id,
               q.body_json,
               q.body_sha256,
               q.attempts,
               raw_token,
               q.lease_expires_at
          from public.binario_social_publish_queue q
         where q.tenant_id = candidate.tenant_id
           and q.publication_id = candidate.publication_id;
    end loop;
end;
$$;

revoke all on function public.binario_claim_social_publish_jobs(text,text,timestamptz,integer,integer) from public, anon, authenticated;
grant execute on function public.binario_claim_social_publish_jobs(text,text,timestamptz,integer,integer) to service_role;

comment on table public.binario_social_publish_queue is
    'Server-only post-W99 social publication queue. Never stores Meta/API credentials.';
comment on function public.binario_claim_social_publish_jobs(text,text,timestamptz,integer,integer) is
    'Atomic service-role-only worker lease claim for post-W99 social jobs.';
