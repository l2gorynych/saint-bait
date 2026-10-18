-- Execute once in the SQL editor of your Supabase project.
-- Authentication > Providers > Anonymous sign-ins must be enabled.
-- The desktop app uses only the publishable/anon key, never service_role.
create table if not exists public.catches (
  id uuid primary key,
  contributor_id uuid not null default auth.uid() references auth.users(id),
  occurred_at timestamptz not null,
  received_at timestamptz not null default now(),
  waterbody_id text not null check (waterbody_id ~ '^[A-Za-z0-9_.-]{1,100}$'),
  x double precision not null check (x between -100000 and 100000),
  y double precision not null check (y between -100000 and 100000),
  species text not null check (species ~ '^[A-Za-z0-9_.-]{1,128}$'),
  weight_g integer not null check (weight_g between 1 and 2000000),
  grade integer check (grade between 0 and 4),
  clip_m integer check (clip_m between 0 and 10000),
  bait_id text check (bait_id is null or bait_id ~ '^[A-Za-z0-9_.-]{1,128}$'),
  fish_id uuid,
  groundbait_used boolean,
  groundbait jsonb not null default '[]' check(jsonb_typeof(groundbait)='array' and jsonb_array_length(groundbait)<=20),
  equipment jsonb not null default '[]' check
    (jsonb_typeof(equipment)='array' and jsonb_array_length(equipment)<=20 and octet_length(equipment::text)<=20000)
);
create index if not exists catches_location_time on public.catches(waterbody_id,x,y,occurred_at desc);
alter table public.catches enable row level security;
drop policy if exists catches_read on public.catches;
create policy catches_read on public.catches for select to authenticated using(true);
drop policy if exists catches_insert_own on public.catches;
create policy catches_insert_own on public.catches for insert to authenticated
  with check (contributor_id=auth.uid() and occurred_at between '2020-01-01'::timestamptz and now()+interval '1 day');
grant select,insert on public.catches to authenticated;
revoke all on public.catches from anon;

alter table public.catches add column if not exists fish_id uuid;
alter table public.catches add column if not exists groundbait_used boolean;
alter table public.catches add column if not exists groundbait jsonb not null default '[]';
drop function if exists public.nearby_catches(text,double precision,double precision,double precision,integer);
create function public.nearby_catches(
  p_waterbody text,p_x double precision,p_y double precision,p_radius double precision default 3,p_limit integer default 100
) returns table(id uuid,occurred_at timestamptz,waterbody_id text,x double precision,y double precision,
                species text,weight_g integer,grade integer,clip_m integer,bait_id text,equipment jsonb,
                fish_id uuid,groundbait_used boolean,groundbait jsonb)
language sql stable security invoker set search_path=public as $$
  select c.id,c.occurred_at,c.waterbody_id,c.x,c.y,c.species,c.weight_g,c.grade,c.clip_m,c.bait_id,c.equipment,
         c.fish_id,c.groundbait_used,c.groundbait
  from public.catches c
  where c.waterbody_id=p_waterbody
    and c.x between p_x-least(3,greatest(0,p_radius)) and p_x+least(3,greatest(0,p_radius))
    and c.y between p_y-least(3,greatest(0,p_radius)) and p_y+least(3,greatest(0,p_radius))
  order by c.occurred_at desc,c.id limit least(100,greatest(1,p_limit));
$$;
revoke all on function public.nearby_catches(text,double precision,double precision,double precision,integer) from public,anon;
grant execute on function public.nearby_catches(text,double precision,double precision,double precision,integer) to authenticated;

alter table public.catches add column if not exists fish_id uuid;
alter table public.catches add column if not exists groundbait_used boolean;
alter table public.catches add column if not exists groundbait jsonb not null default '[]';

create table if not exists public.market_observations(
  id uuid primary key,
  contributor_id uuid not null default auth.uid() references auth.users(id),
  observed_at timestamptz not null,
  waterbody_id text not null check(waterbody_id ~ '^[A-Za-z0-9_.-]{1,100}$'),
  fish_id uuid not null,
  species text not null check(species ~ '^[A-Za-z0-9_.-]{1,128}$'),
  weight_g integer not null check(weight_g between 1 and 2000000),
  grade integer not null check(grade between 0 and 4),
  freshness integer not null check(freshness between 0 and 100),
  price_cents integer not null check(price_cents between 0 and 2000000000)
);
create index if not exists market_recent on public.market_observations(waterbody_id,observed_at desc);
alter table public.market_observations enable row level security;
drop policy if exists market_read on public.market_observations;
create policy market_read on public.market_observations for select to authenticated using(true);
drop policy if exists market_insert on public.market_observations;
create policy market_insert on public.market_observations for insert to authenticated
  with check(contributor_id=auth.uid() and observed_at between '2020-01-01'::timestamptz and now()+interval '1 day');
revoke all on public.market_observations from anon;
grant select,insert on public.market_observations to authenticated;
