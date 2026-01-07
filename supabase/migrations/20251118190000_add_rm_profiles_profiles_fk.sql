-- Add foreign key from rm_profiles.id to profiles.id for PostgREST joins
ALTER TABLE public.rm_profiles
ADD CONSTRAINT rm_profiles_id_profiles_fkey
FOREIGN KEY (id) REFERENCES public.profiles (id);