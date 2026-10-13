-- Development data for MySQL (same shape as dev/seed.sql for Postgres: fact_ventas, 50k rows)
-- The init client defaults to latin1: without this, the UTF-8 bytes of 'Bajío' get stored as 'BajÃ­o'
SET NAMES utf8mb4;
SET SESSION cte_max_recursion_depth = 100000;
CREATE TABLE fact_ventas (
  pedido_id   int,
  fecha_venta date,
  region_desc varchar(40),
  canal       varchar(40),
  monto_bruto decimal(12,2),
  descuento   decimal(12,2)
) CHARACTER SET utf8mb4;
INSERT INTO fact_ventas
WITH RECURSIVE g(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM g WHERE n < 50000)
SELECT n,
       DATE_ADD(DATE '2025-01-01', INTERVAL (n % 600) DAY),
       ELT(1 + n % 4, 'Norte', 'Centro', 'Sur', 'Bajío'),
       ELT(1 + n % 3, 'Tienda', 'Web', 'Mayoreo'),
       ROUND(100 + RAND() * 900, 2),
       ROUND(RAND() * 50, 2)
FROM g;
-- SELECT-only user (CLAUDE.md: database users with SELECT only)
CREATE USER 'd2h_reader'@'%' IDENTIFIED BY 'd2h';
GRANT SELECT ON d2h.fact_ventas TO 'd2h_reader'@'%';
