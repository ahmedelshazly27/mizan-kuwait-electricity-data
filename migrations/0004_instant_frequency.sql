-- Loads at an instant (the half-hourly curve on the yearly peak day): frequency
-- 'instant', with the time in observed_at.
alter table public.observations drop constraint observations_frequency_check;
alter table public.observations add constraint observations_frequency_check
  check (frequency in ('annual', 'half_year', 'monthly', 'daily', 'instant'));
alter table public.observations add constraint observations_instant_has_time
  check (frequency <> 'instant' or observed_at is not null);
