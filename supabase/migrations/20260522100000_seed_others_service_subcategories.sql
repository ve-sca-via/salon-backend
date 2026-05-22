-- Ensure each active service category has an "Others" subcategory for vendor custom services
INSERT INTO service_subcategories (parent_category_id, name, description, display_order, is_active)
SELECT
    sc.id,
    'Others',
    'Custom or vendor-defined services',
    9999,
    TRUE
FROM service_categories sc
WHERE sc.is_active = TRUE
  AND NOT EXISTS (
    SELECT 1
    FROM service_subcategories ss
    WHERE ss.parent_category_id = sc.id
      AND LOWER(TRIM(ss.name)) = 'others'
  );
