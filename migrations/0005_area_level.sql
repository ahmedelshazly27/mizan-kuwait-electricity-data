-- Supply areas (numbered as printed in the MEW yearbook's regional peak table).
alter table public.observations drop constraint observations_level_check;
alter table public.observations add constraint observations_level_check
  check (level in ('national', 'plant', 'unit', 'sector', 'area'));
