-- Independent coverage projection. Never rewrites legacy statuses.
BEGIN READ ONLY;
SET LOCAL statement_timeout = '30s';
WITH actor_counts AS (
 SELECT sop,count(*) AS n FROM pisrs.acts WHERE btrim(sop)<>'' GROUP BY sop
), npbs AS (
 SELECT sop_from_docno,count(*) AS n FROM pisrs.npb_catalog GROUP BY sop_from_docno
), versions AS (
 SELECT sop_from_docno,count(*) AS n FROM pisrs.act_text_versions GROUP BY sop_from_docno
), direct_links AS (
 SELECT act_id,count(*) AS n FROM pisrs.act_text_versions WHERE act_id IS NOT NULL GROUP BY act_id
), coverage AS (
 SELECT catalog.register_id,catalog.status AS legacy_status,
 EXISTS(SELECT 1 FROM pisrs.laws law WHERE law.register_id=catalog.register_id
    OR (catalog.sop IS NOT NULL AND law.sop=catalog.sop)
    OR (catalog.moped_id IS NOT NULL AND law.moped_id=catalog.moped_id)) AS legacy_present_now,
 coalesce(npbs.n,0)>0 AS has_known_npb,
 coalesce(direct_links.n,0)>0 AS has_direct_version_link,
 CASE WHEN nullif(btrim(catalog.sop),'') IS NULL THEN 'unknown_no_sop'
      WHEN actor_counts.n>1 THEN 'ambiguous_sop'
      WHEN coalesce(npbs.n,0)=0 THEN 'without_known_npb'
      WHEN coalesce(versions.n,0)<npbs.n THEN 'known_npb_missing_versions'
      WHEN coalesce(direct_links.n,0)=0 THEN 'known_text_without_direct_link'
      ELSE 'known_npb_versions_linked' END AS coverage_reason
 FROM pisrs.act_sync_catalog catalog
 LEFT JOIN pisrs.acts act ON act.register_id=catalog.register_id
 LEFT JOIN actor_counts ON actor_counts.sop=catalog.sop
 LEFT JOIN npbs ON npbs.sop_from_docno=catalog.sop
 LEFT JOIN versions ON versions.sop_from_docno=catalog.sop
 LEFT JOIN direct_links ON direct_links.act_id=act.id
)
SELECT legacy_status,coverage_reason,count(*) AS acts,
 count(*) FILTER(WHERE legacy_present_now) AS current_legacy_presence,
 count(*) FILTER(WHERE has_known_npb) AS with_known_npb,
 count(*) FILTER(WHERE has_direct_version_link) AS with_direct_version_link
FROM coverage GROUP BY legacy_status,coverage_reason ORDER BY 1,2;
ROLLBACK;
