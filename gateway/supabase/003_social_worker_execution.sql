-- Post-W99 cloud social worker execution hardening.
-- Extends the secret-free queue with an explicit provider-effect checkpoint so an
-- expired worker lease can never blindly retry after a remote side effect may have begun.

alter table public.binario_social_publish_queue
    add column if not exists provider_started_at timestamptz,
    add column if not exists provider_outcome_ambiguous boolean not null default false;

alter table public.binario_social_publish_queue
    drop constraint if exists binario_social_provider_checkpoint_shape;
alter table public.binario_social_publish_queue
    add constraint binario_social_provider_checkpoint_shape check (
        (provider_started_at is null)
        or
        (status = 'LEASED' and lease_worker_id is not null and lease_sha256 is not null and lease_expires_at is not null)
    );

-- Replace the claim RPC so expired leases are recovered only when no provider effect
-- had started. p_now remains in the signature for wire compatibility with the v1 adapter,
-- but lease validity is decided exclusively by PostgreSQL clock_timestamp().
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
    v_now timestamptz := clock_timestamp();
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
       set status = case
               when q.provider_started_at is not null then 'FAILED'
               when q.attempts >= 5 then 'FAILED'
               else 'PENDING'
           end,
           available_at = v_now,
           lease_worker_id = null,
           lease_sha256 = null,
           lease_expires_at = null,
           provider_outcome_ambiguous = (q.provider_started_at is not null),
           provider_started_at = null,
           last_error = case
               when q.provider_started_at is not null then
                   'worker lease expired after provider effect began; manual reconciliation required'
               else
                   'worker lease expired before provider effect began'
           end,
           updated_at = v_now
     where q.tenant_id = p_tenant_id
       and q.status = 'LEASED'
       and q.lease_expires_at <= v_now;

    for candidate in
        select q.tenant_id, q.publication_id
          from public.binario_social_publish_queue q
         where q.tenant_id = p_tenant_id
           and q.status = 'PENDING'
           and q.available_at <= v_now
           and q.attempts < 5
           and q.provider_outcome_ambiguous = false
         order by q.available_at, q.scheduled_for, q.publication_id
         for update skip locked
         limit p_limit
    loop
        raw_token := encode(gen_random_bytes(32), 'hex');
        expiry := v_now + make_interval(secs => p_lease_seconds);

        update public.binario_social_publish_queue q
           set status = 'LEASED',
               attempts = q.attempts + 1,
               lease_worker_id = p_worker_id,
               lease_sha256 = encode(digest(raw_token, 'sha256'), 'hex'),
               lease_expires_at = expiry,
               provider_started_at = null,
               provider_outcome_ambiguous = false,
               last_error = null,
               updated_at = v_now
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

-- This checkpoint must be committed before the first Meta request. Once it exists,
-- no automatic retry is allowed if the worker disappears. p_now is compatibility-only;
-- the database clock owns lease validation.
create or replace function public.binario_begin_social_provider_effect(
    p_tenant_id text,
    p_publication_id text,
    p_lease_token text,
    p_now timestamptz
)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
    changed integer;
    v_now timestamptz := clock_timestamp();
begin
    if p_lease_token !~ '^[0-9a-f]{64}$' then
        raise exception 'invalid lease token';
    end if;

    update public.binario_social_publish_queue q
       set provider_started_at = v_now,
           updated_at = v_now
     where q.tenant_id = p_tenant_id
       and q.publication_id = p_publication_id
       and q.status = 'LEASED'
       and q.provider_started_at is null
       and q.lease_expires_at > v_now
       and q.lease_sha256 = encode(digest(p_lease_token, 'sha256'), 'hex');
    get diagnostics changed = row_count;
    if changed <> 1 then
        raise exception 'provider effect checkpoint rejected';
    end if;
    return true;
end;
$$;

create or replace function public.binario_complete_social_publish_job(
    p_tenant_id text,
    p_publication_id text,
    p_lease_token text,
    p_remote_id text,
    p_now timestamptz
)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
    changed integer;
    v_now timestamptz := clock_timestamp();
begin
    if p_lease_token !~ '^[0-9a-f]{64}$' then
        raise exception 'invalid lease token';
    end if;
    if length(trim(coalesce(p_remote_id, ''))) < 1 or length(p_remote_id) > 256 then
        raise exception 'invalid remote id';
    end if;

    update public.binario_social_publish_queue q
       set status = 'PUBLISHED',
           remote_id = trim(p_remote_id),
           last_error = null,
           provider_started_at = null,
           provider_outcome_ambiguous = false,
           lease_worker_id = null,
           lease_sha256 = null,
           lease_expires_at = null,
           updated_at = v_now
     where q.tenant_id = p_tenant_id
       and q.publication_id = p_publication_id
       and q.status = 'LEASED'
       and q.provider_started_at is not null
       and q.lease_expires_at > v_now
       and q.lease_sha256 = encode(digest(p_lease_token, 'sha256'), 'hex');
    get diagnostics changed = row_count;
    if changed <> 1 then
        raise exception 'social publish completion rejected';
    end if;
    return true;
end;
$$;

-- Failures before provider_started_at may be retried with bounded backoff. Failures
-- after provider_started_at are always terminal and marked ambiguous to prevent duplicates.
create or replace function public.binario_fail_social_publish_job(
    p_tenant_id text,
    p_publication_id text,
    p_lease_token text,
    p_error text,
    p_retryable boolean,
    p_now timestamptz
)
returns table (status text, attempts smallint, available_at timestamptz, provider_outcome_ambiguous boolean)
language plpgsql
security definer
set search_path = public
as $$
declare
    current_row public.binario_social_publish_queue%rowtype;
    retry_allowed boolean;
    backoff_seconds integer;
    v_now timestamptz := clock_timestamp();
begin
    if p_lease_token !~ '^[0-9a-f]{64}$' then
        raise exception 'invalid lease token';
    end if;
    if length(trim(coalesce(p_error, ''))) < 1 or length(p_error) > 2000 then
        raise exception 'invalid worker error';
    end if;

    select * into current_row
      from public.binario_social_publish_queue q
     where q.tenant_id = p_tenant_id
       and q.publication_id = p_publication_id
       and q.status = 'LEASED'
       and q.lease_expires_at > v_now
       and q.lease_sha256 = encode(digest(p_lease_token, 'sha256'), 'hex')
     for update;
    if not found then
        raise exception 'social publish failure checkpoint rejected';
    end if;

    retry_allowed := p_retryable
        and current_row.provider_started_at is null
        and current_row.attempts < 5;
    backoff_seconds := least(
        3600,
        30 * power(2, greatest(0, current_row.attempts - 1))::integer
    );

    update public.binario_social_publish_queue q
       set status = case when retry_allowed then 'PENDING' else 'FAILED' end,
           available_at = case when retry_allowed then v_now + make_interval(secs => backoff_seconds) else q.available_at end,
           last_error = trim(p_error),
           provider_outcome_ambiguous = (current_row.provider_started_at is not null),
           provider_started_at = null,
           lease_worker_id = null,
           lease_sha256 = null,
           lease_expires_at = null,
           updated_at = v_now
     where q.tenant_id = p_tenant_id
       and q.publication_id = p_publication_id;

    return query
    select q.status, q.attempts, q.available_at, q.provider_outcome_ambiguous
      from public.binario_social_publish_queue q
     where q.tenant_id = p_tenant_id
       and q.publication_id = p_publication_id;
end;
$$;

revoke all on function public.binario_begin_social_provider_effect(text,text,text,timestamptz) from public, anon, authenticated;
revoke all on function public.binario_complete_social_publish_job(text,text,text,text,timestamptz) from public, anon, authenticated;
revoke all on function public.binario_fail_social_publish_job(text,text,text,text,boolean,timestamptz) from public, anon, authenticated;

grant execute on function public.binario_begin_social_provider_effect(text,text,text,timestamptz) to service_role;
grant execute on function public.binario_complete_social_publish_job(text,text,text,text,timestamptz) to service_role;
grant execute on function public.binario_fail_social_publish_job(text,text,text,text,boolean,timestamptz) to service_role;

comment on function public.binario_begin_social_provider_effect(text,text,text,timestamptz) is
    'Marks the no-blind-retry boundary immediately before a cloud social provider call; lease time is database-owned.';
comment on function public.binario_complete_social_publish_job(text,text,text,text,timestamptz) is
    'Lease-bound successful completion for a cloud social provider call; lease time is database-owned.';
comment on function public.binario_fail_social_publish_job(text,text,text,text,boolean,timestamptz) is
    'Lease-bound failure completion; provider-started failures are terminal and ambiguous; lease time is database-owned.';
