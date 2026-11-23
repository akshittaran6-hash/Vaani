-- Vaani database schema (Supabase Postgres). Contract: docs/CONTRACTS.md §1.
-- Idempotent: safe to run again on an existing database (creates only what is missing,
-- replaces functions). Apply with scripts/db_apply.py, then rls.sql, then seed.sql.

-- ---------------------------------------------------------------------------
-- Helpers
-- ---------------------------------------------------------------------------

-- "Today" for the demo is always the IST calendar date, whatever the server's timezone.
-- The eval freezes the clock per database (`alter database … set vaani.now_ist = '…'`);
-- unset everywhere else, so these are just "now in IST".
create or replace function public.vaani_now_ist() returns timestamp
language sql stable as $$
  select coalesce(nullif(current_setting('vaani.now_ist', true), '')::timestamp,
                  now() at time zone 'Asia/Kolkata')
$$;

create or replace function public.vaani_today() returns date
language sql stable as $$ select public.vaani_now_ist()::date $$;

create or replace function public.vaani_touch_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end $$;

-- ---------------------------------------------------------------------------
-- Catalogue (loaded from data/*.json by the seed)
-- ---------------------------------------------------------------------------

create table if not exists public.areas (
  area_id                  text primary key,
  name_en                  text not null,
  name_te                  text not null,
  name_hi                  text not null,
  aliases                  text[] not null default '{}',
  lat                      double precision not null,
  lng                      double precision not null,
  nearby_unsupported_areas text[] not null default '{}',
  unsupported_area_reply   jsonb not null default '{}'::jsonb,
  is_sample_data           boolean not null default true
);

create table if not exists public.restaurants (
  restaurant_id        text primary key,
  slug                 text not null unique,
  name                 text not null,
  name_spoken_te       text not null,
  name_spoken_hi       text not null,
  name_aliases         text[] not null default '{}',
  area_id              text not null references public.areas(area_id),
  address              text not null,
  cuisines             text[] not null default '{}',
  food_type            text not null check (food_type in ('veg', 'non-veg', 'both')),
  rating               numeric(2,1) not null check (rating between 0 and 5),
  price_for_two_inr    integer not null check (price_for_two_inr > 0),
  highlight            text not null,
  popular_dishes       text[] not null default '{}',
  opening_hours        jsonb not null,
  features             jsonb not null default '{}'::jsonb,
  booking_rules        jsonb not null,
  slot_length_minutes  integer not null default 90,
  faqs                 jsonb not null default '[]'::jsonb,
  phone                text not null,
  accent_color         text not null,
  is_sample_data       boolean not null default true
);
create index if not exists restaurants_area_idx on public.restaurants(area_id);

create table if not exists public.restaurant_tables (
  restaurant_id text not null references public.restaurants(restaurant_id) on delete cascade,
  table_id      text not null,
  capacity      integer not null check (capacity > 0),
  primary key (restaurant_id, table_id)
);

-- One row per bookable start time per day. Each start time is an independent seating
-- (a table booked at 20:00 does not block 20:30) — a deliberate demo simplification.
create table if not exists public.restaurant_slots (
  restaurant_id    text not null references public.restaurants(restaurant_id) on delete cascade,
  date             date not null,
  time             time not null,
  booked_table_ids text[] not null default '{}',
  blocked          boolean not null default false,
  primary key (restaurant_id, date, time)
);

create table if not exists public.hospitals (
  hospital_id      text primary key,
  slug             text not null unique,
  name             text not null,
  name_spoken_te   text not null,
  name_spoken_hi   text not null,
  name_aliases     text[] not null default '{}',
  area_id          text not null references public.areas(area_id),
  type             text not null check (type in ('multi-speciality hospital', 'clinic')),
  address          text not null,
  rating           numeric(2,1) not null check (rating between 0 and 5),
  highlight        text not null,
  specialities     text[] not null default '{}',
  facilities       jsonb not null default '{}'::jsonb,
  opd_hours        jsonb not null,
  languages_spoken text[] not null default '{}',
  faqs             jsonb not null default '[]'::jsonb,
  phone            text not null,
  accent_color     text not null,
  is_sample_data   boolean not null default true
);
create index if not exists hospitals_area_idx on public.hospitals(area_id);

create table if not exists public.doctors (
  doctor_id            text primary key,
  hospital_id          text not null references public.hospitals(hospital_id) on delete cascade,
  name                 text not null,
  name_spoken_te       text not null,
  name_spoken_hi       text not null,
  gender               text not null check (gender in ('female', 'male')),
  speciality           text not null,
  qualification        text not null,
  experience_years     integer not null check (experience_years >= 0),
  languages            text[] not null default '{}',
  consultation_fee_inr integer not null check (consultation_fee_inr >= 0),
  schedule             jsonb not null,
  slot_length_minutes  integer not null default 15,
  on_leave_dates       date[] not null default '{}',
  is_sample_data       boolean not null default true
);
create index if not exists doctors_hospital_idx on public.doctors(hospital_id);
create index if not exists doctors_speciality_idx on public.doctors(speciality);

create table if not exists public.doctor_slots (
  doctor_id text not null references public.doctors(doctor_id) on delete cascade,
  date      date not null,
  time      time not null,
  status    text not null default 'free' check (status in ('free', 'booked', 'blocked')),
  primary key (doctor_id, date, time)
);

create table if not exists public.speciality_map (
  id           serial primary key,
  phrase       text not null,
  lang         text not null check (lang in ('te', 'hi', 'en')),
  speciality   text,
  is_emergency boolean not null default false,
  check (is_emergency or speciality is not null)
);

-- ---------------------------------------------------------------------------
-- Activity (written by the backend)
-- ---------------------------------------------------------------------------

create table if not exists public.calls (
  call_id        text primary key,
  channel        text not null check (channel in ('phone', 'web')),
  direction      text not null default 'inbound' check (direction in ('inbound', 'outbound')),
  from_number    text,
  started_at     timestamptz not null default now(),
  ended_at       timestamptz,
  language       text[] not null default '{}',
  services_used  text[] not null default '{}',
  transcript     jsonb not null default '[]'::jsonb,
  outcome_json   jsonb,
  tool_timeline  jsonb not null default '[]'::jsonb,
  latency_json   jsonb,
  recording_url  text,
  summary        text
);

create table if not exists public.call_events (
  id      bigserial primary key,
  call_id text not null references public.calls(call_id) on delete cascade,
  ts      timestamptz not null default now(),
  type    text not null check (type in (
            'call_started', 'language_detected', 'agent_switched', 'slot_filled',
            'tool_called', 'booking_created', 'payment_updated', 'call_ended',
            'transcript', 'latency')),
  payload jsonb not null default '{}'::jsonb
);
create index if not exists call_events_call_idx on public.call_events(call_id, ts);

create table if not exists public.bookings (
  booking_id     text primary key check (booking_id ~ '^VN-[0-9]{4}$'),
  service        text not null check (service in ('restaurant', 'hospital')),
  business_id    text not null,
  doctor_id      text references public.doctors(doctor_id),
  date           date not null,
  time           time not null,
  party_size     integer check (party_size is null or party_size > 0),
  table_id       text,
  name           text not null,
  phone          text not null,
  language       text not null default 'en' check (language in ('te', 'hi', 'en', 'ta', 'kn', 'ml')),
  source         text not null default 'vaani_call' check (source in ('vaani_call', 'web', 'walk_in')),
  status         text not null default 'confirmed' check (status in (
                   'confirmed', 'pending_payment', 'paid', 'arrived', 'checked_in', 'cancelled')),
  amount_due_inr integer check (amount_due_inr is null or amount_due_inr >= 0),
  call_id        text references public.calls(call_id) on delete set null,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  check (service <> 'restaurant' or (party_size is not null and table_id is not null and doctor_id is null)),
  check (service <> 'hospital' or doctor_id is not null)
);
create index if not exists bookings_business_date_idx on public.bookings(business_id, date);

-- The hard guarantee against double booking, independent of application code.
create unique index if not exists bookings_one_per_table
  on public.bookings(business_id, date, time, table_id)
  where status <> 'cancelled' and table_id is not null;
create unique index if not exists bookings_one_per_doctor_slot
  on public.bookings(doctor_id, date, time)
  where status <> 'cancelled' and doctor_id is not null;

drop trigger if exists bookings_touch on public.bookings;
create trigger bookings_touch before update on public.bookings
  for each row execute function public.vaani_touch_updated_at();

create table if not exists public.payments (
  payment_id   text primary key,
  booking_id   text not null references public.bookings(booking_id) on delete cascade,
  amount_inr   integer not null check (amount_inr >= 0),
  provider     text not null check (provider in ('razorpay', 'stripe', 'mock')),
  provider_ref text,
  status       text not null default 'created' check (status in ('created', 'paid', 'failed', 'refunded')),
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
create index if not exists payments_booking_idx on public.payments(booking_id);

drop trigger if exists payments_touch on public.payments;
create trigger payments_touch before update on public.payments
  for each row execute function public.vaani_touch_updated_at();

-- Full rows in Realtime UPDATE/DELETE payloads (old_record) for the live widgets.
alter table public.bookings         replica identity full;
alter table public.restaurant_slots replica identity full;
alter table public.doctor_slots     replica identity full;
alter table public.payments         replica identity full;

-- ---------------------------------------------------------------------------
-- Atomic booking functions. Errors are raised with message = an error code from
-- docs/CONTRACTS.md §2 and hint = a human-readable explanation.
-- ---------------------------------------------------------------------------

-- Random VN-xxxx id that is not yet used. Callers hold the slot lock, so the only
-- race left is two different slots picking the same id; the PK catches that.
create or replace function public.vaani_new_booking_id() returns text
language plpgsql volatile as $$
declare
  v_id text;
begin
  for i in 1..50 loop
    v_id := 'VN-' || (1000 + floor(random() * 9000))::int::text;
    if not exists (select 1 from public.bookings where booking_id = v_id) then
      return v_id;
    end if;
  end loop;
  raise exception 'ID_EXHAUSTED' using hint = 'No free booking id after 50 tries';
end $$;

create or replace function public.book_table(
  p_restaurant_id text,
  p_date          date,
  p_time          time,
  p_party_size    integer,
  p_name          text,
  p_phone         text,
  p_language      text default 'en',
  p_source        text default 'vaani_call',
  p_call_id       text default null
) returns table (booking_id text, table_id text, deposit_needed boolean, deposit_inr integer)
language plpgsql volatile as $$
#variable_conflict use_column
declare
  v_rules     jsonb;
  v_max       integer;
  v_threshold integer;
  v_deposit   integer;
  v_slot      public.restaurant_slots%rowtype;
  v_table     text;
  v_id        text;
  v_needs_dep boolean;
begin
  select r.booking_rules into v_rules from public.restaurants r where r.restaurant_id = p_restaurant_id;
  if not found then
    raise exception 'UNKNOWN_BUSINESS' using hint = format('No restaurant %s', p_restaurant_id);
  end if;

  v_max       := (v_rules ->> 'max_party_size')::int;
  v_threshold := (v_rules ->> 'deposit_required_for_party_size_at_least')::int;
  v_deposit   := coalesce((v_rules ->> 'deposit_inr')::int, 0);

  if p_party_size is null or p_party_size < 1 or p_party_size > v_max then
    raise exception 'PARTY_TOO_LARGE' using hint = format('Party %s, max %s', p_party_size, v_max);
  end if;
  if coalesce(trim(p_name), '') = '' or coalesce(trim(p_phone), '') = '' then
    raise exception 'MISSING_DETAILS' using hint = 'Name and phone are required';
  end if;
  if (p_date + p_time) < public.vaani_now_ist() then
    raise exception 'INVALID_TIME' using hint = 'That time has already passed';
  end if;

  -- Lock the slot row: concurrent bookings for the same restaurant/date/time queue here.
  select * into v_slot from public.restaurant_slots s
   where s.restaurant_id = p_restaurant_id and s.date = p_date and s.time = p_time
   for update;
  if not found then
    raise exception 'INVALID_TIME' using hint = 'Not a bookable time for this restaurant';
  end if;
  if v_slot.blocked then
    raise exception 'BLOCKED' using hint = 'Staff blocked this slot';
  end if;

  -- Smallest free table that fits (T2 before T10).
  select t.table_id into v_table
    from public.restaurant_tables t
   where t.restaurant_id = p_restaurant_id
     and t.capacity >= p_party_size
     and not (t.table_id = any (v_slot.booked_table_ids))
   order by t.capacity, length(t.table_id), t.table_id
   limit 1;
  if v_table is null then
    raise exception 'SLOT_FULL' using hint = 'No free table for that party size';
  end if;

  update public.restaurant_slots s
     set booked_table_ids = array_append(s.booked_table_ids, v_table)
   where s.restaurant_id = p_restaurant_id and s.date = p_date and s.time = p_time;

  v_needs_dep := v_threshold is not null and p_party_size >= v_threshold;
  v_id := public.vaani_new_booking_id();

  insert into public.bookings (booking_id, service, business_id, date, time, party_size, table_id,
                               name, phone, language, source, status, amount_due_inr, call_id)
  values (v_id, 'restaurant', p_restaurant_id, p_date, p_time, p_party_size, v_table,
          trim(p_name), trim(p_phone), p_language, p_source,
          case when v_needs_dep then 'pending_payment' else 'confirmed' end,
          case when v_needs_dep then v_deposit else null end,
          p_call_id);

  return query select v_id, v_table, v_needs_dep, case when v_needs_dep then v_deposit else 0 end;
end $$;

create or replace function public.book_appointment(
  p_doctor_id text,
  p_date      date,
  p_time      time,
  p_name      text,
  p_phone     text,
  p_language  text default 'en',
  p_source    text default 'vaani_call',
  p_call_id   text default null
) returns table (booking_id text, fee_inr integer, hospital_id text)
language plpgsql volatile as $$
#variable_conflict use_column
declare
  v_doc  public.doctors%rowtype;
  v_slot public.doctor_slots%rowtype;
  v_id   text;
begin
  select * into v_doc from public.doctors d where d.doctor_id = p_doctor_id;
  if not found then
    raise exception 'UNKNOWN_DOCTOR' using hint = format('No doctor %s', p_doctor_id);
  end if;
  if p_date = any (v_doc.on_leave_dates) then
    raise exception 'DOCTOR_ON_LEAVE' using hint = 'Doctor is on leave that day';
  end if;
  if coalesce(trim(p_name), '') = '' or coalesce(trim(p_phone), '') = '' then
    raise exception 'MISSING_DETAILS' using hint = 'Name and phone are required';
  end if;
  if (p_date + p_time) < public.vaani_now_ist() then
    raise exception 'INVALID_TIME' using hint = 'That time has already passed';
  end if;

  select * into v_slot from public.doctor_slots s
   where s.doctor_id = p_doctor_id and s.date = p_date and s.time = p_time
   for update;
  if not found then
    raise exception 'INVALID_TIME' using hint = 'Not a slot in this doctor''s schedule';
  end if;
  if v_slot.status = 'blocked' then
    raise exception 'BLOCKED' using hint = 'Staff blocked this slot';
  end if;
  if v_slot.status = 'booked' then
    raise exception 'SLOT_TAKEN' using hint = 'Slot already booked';
  end if;

  update public.doctor_slots s set status = 'booked'
   where s.doctor_id = p_doctor_id and s.date = p_date and s.time = p_time;

  v_id := public.vaani_new_booking_id();
  insert into public.bookings (booking_id, service, business_id, doctor_id, date, time,
                               name, phone, language, source, status, amount_due_inr, call_id)
  values (v_id, 'hospital', v_doc.hospital_id, p_doctor_id, p_date, p_time,
          trim(p_name), trim(p_phone), p_language, p_source,
          case when v_doc.consultation_fee_inr > 0 then 'pending_payment' else 'confirmed' end,
          v_doc.consultation_fee_inr, p_call_id);

  return query select v_id, v_doc.consultation_fee_inr, v_doc.hospital_id;
end $$;

-- Cancels a booking and frees its table / doctor slot. Idempotent.
create or replace function public.cancel_booking(p_booking_id text)
returns public.bookings
language plpgsql volatile as $$
declare
  v_b public.bookings%rowtype;
begin
  select * into v_b from public.bookings b where b.booking_id = p_booking_id for update;
  if not found then
    raise exception 'UNKNOWN_BOOKING' using hint = format('No booking %s', p_booking_id);
  end if;
  if v_b.status = 'cancelled' then
    return v_b;
  end if;

  if v_b.service = 'restaurant' then
    update public.restaurant_slots s
       set booked_table_ids = array_remove(s.booked_table_ids, v_b.table_id)
     where s.restaurant_id = v_b.business_id and s.date = v_b.date and s.time = v_b.time;
  else
    update public.doctor_slots s set status = 'free'
     where s.doctor_id = v_b.doctor_id and s.date = v_b.date and s.time = v_b.time
       and s.status = 'booked';
  end if;

  update public.bookings b set status = 'cancelled' where b.booking_id = p_booking_id
  returning * into v_b;
  return v_b;
end $$;
