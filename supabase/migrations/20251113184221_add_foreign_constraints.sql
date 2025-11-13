alter table "public"."rm_score_history" add constraint "fk_rm_score_history_salon" FOREIGN KEY (salon_id) REFERENCES public.salons(id) ON DELETE CASCADE not valid;

alter table "public"."rm_score_history" validate constraint "fk_rm_score_history_salon";


