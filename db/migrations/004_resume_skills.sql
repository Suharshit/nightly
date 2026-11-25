-- Skills found in the uploaded resume (rules matcher, same list as jobs).
-- Personalisation uses them for skill overlap (Jaccard) with each job's skills.
alter table profiles add column if not exists resume_skills text[] default '{}';
