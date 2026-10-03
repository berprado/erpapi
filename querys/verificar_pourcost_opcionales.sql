-- Verificacion de SOLO LECTURA previa al despliegue de POUR COST v12.41
-- (opcional por defecto por categoria, ver documentos/pour_cost/pourcost.md seccion 6).
--
-- Correr en cada BD de produccion (casa matriz y Beer Garden) ANTES de definir las
-- variables POURCOST_OPCIONAL_CAT<id_categoria>=<id_producto> en ese Web Service.
-- Los ids de abajo son los del entorno `test` (BD local adminerp): si en una produccion
-- las consultas 1 o 5 muestran otros nombres, esos ids no valen ahi y hay que buscar los
-- correctos (alm_producto.id de cada producto, alm_categoria.id de cada categoria).
--
-- Mapa usado (categoria -> producto):
--   1 WHISKYS -> 64 AGUA S-GAS 2LT        7 VODKAS   -> 63 SPRITE 3LT
--   2 RON     -> 62 COCA COLA 3LT         9 GIN      -> 61 AGUA TONICA 1LT
--   3 LICOR   -> 479 ROCKSTAR            10 COCTELES -> 63 SPRITE 3LT
--   4 FERNET  -> 62 COCA COLA 3LT        11 CERVEZAS -> 492 AMSTEL LATA 473ML
--   5 SINGANI -> 60 GINGER ALE 2LT       21 GINVIP   -> 61 AGUA TONICA 1LT

-- 1. Productos de las reglas (esperado: 7 filas, todas HAB, con los nombres del mapa).
SELECT id, nombre, estado
FROM alm_producto
WHERE id IN (60, 61, 62, 63, 64, 479, 492)
ORDER BY id;

-- 2. Categorias de combos con opcionales y SIN regla (esperado: vacio; si aparece alguna,
--    sus combos contaran solo el principal hasta que se le asigne una variable).
SELECT b.id_categoria, c.nombre, COUNT(DISTINCT b.id) AS combos
FROM vw_pourcost_receta v
JOIN bar_combo_coctel b ON b.id = v.id_combo_coctel
JOIN alm_categoria c ON c.id = b.id_categoria
WHERE v.tipo_parte_combo = 'OPCIONAL'
  AND b.id_categoria NOT IN (1, 2, 3, 4, 5, 7, 9, 10, 11, 21)
GROUP BY b.id_categoria, c.nombre;

-- 3. Combos con regla pero SIN su opcional por defecto entre sus opcionales (esperado: vacio;
--    cada fila es un combo que contara solo el principal: corregir la receta en el ERP o
--    elegir otro producto para esa categoria).
SELECT b.id_categoria, c.nombre AS categoria, b.codigo, b.nombre AS combo, r.prod AS opcional_esperado
FROM bar_combo_coctel b
JOIN alm_categoria c ON c.id = b.id_categoria
JOIN (SELECT 1 AS cat, 64 AS prod UNION ALL SELECT 2, 62 UNION ALL SELECT 3, 479 UNION ALL SELECT 4, 62
      UNION ALL SELECT 5, 60 UNION ALL SELECT 7, 63 UNION ALL SELECT 9, 61 UNION ALL SELECT 10, 63
      UNION ALL SELECT 11, 492 UNION ALL SELECT 21, 61) r ON r.cat = b.id_categoria
WHERE EXISTS (SELECT 1 FROM vw_pourcost_receta w
              WHERE w.id_combo_coctel = b.id AND w.tipo_parte_combo = 'OPCIONAL')
  AND NOT EXISTS (SELECT 1 FROM vw_pourcost_receta w
                  WHERE w.id_combo_coctel = b.id AND w.id_producto = r.prod AND w.tipo_parte_combo = 'OPCIONAL')
ORDER BY b.id_categoria, b.nombre;

-- 4. El join vista-combo que usa el endpoint debe ser 1:1 (las dos cifras deben ser iguales).
SELECT (SELECT COUNT(*) FROM vw_pourcost_receta) AS vista,
       (SELECT COUNT(*) FROM vw_pourcost_receta v
        JOIN bar_combo_coctel b ON b.id = v.id_combo_coctel) AS con_join;

-- 5. Categorias de las reglas (esperado: 10 filas; 'VODKAS ' lleva un espacio al final en la BD).
SELECT id, nombre
FROM alm_categoria
WHERE id IN (1, 2, 3, 4, 5, 7, 9, 10, 11, 21)
ORDER BY id;
