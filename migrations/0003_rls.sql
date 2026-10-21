-- Read-only for everyone through the API. No insert, update or delete policy exists,
-- and the client roles have no write privileges: only the pipeline (through the
-- Management API, as the database owner) loads data.

do $$
declare t text;
begin
  foreach t in array array['builds', 'sources', 'source_tables', 'variables', 'units', 'fuels', 'plants',
                           'plant_aliases', 'sectors', 'observations', 'conflicts', 'conflict_members',
                           'validation_results']
  loop
    execute format('alter table public.%I enable row level security', t);
    execute format('revoke all on public.%I from anon, authenticated', t);
    execute format('grant select on public.%I to anon, authenticated', t);
    execute format('create policy %I on public.%I for select to anon, authenticated using (true)', t || '_read', t);
  end loop;
end $$;

do $$
declare v text;
begin
  foreach v in array array['obs_canonical', 'latest', 'revisions', 'generation', 'capacity', 'peak_load',
                           'consumption_secondary', 'coverage', 'crosscheck']
  loop
    execute format('revoke all on public.%I from anon, authenticated', v);
    execute format('grant select on public.%I to anon, authenticated', v);
  end loop;
end $$;

-- New tables and functions created later must not become writable by default.
alter default privileges in schema public revoke insert, update, delete, truncate on tables from anon, authenticated;
revoke all on schema pipeline from anon, authenticated;
revoke create on schema public from anon, authenticated;
