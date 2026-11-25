-- Which method filled each job's structured fields: 'rules' or 'rules+llm:<model>'.
-- Needed so the extraction eval and README can say how much the rules alone covered.
alter table jobs add column if not exists extraction_source text;
alter table jobs add column if not exists extraction_error text;
