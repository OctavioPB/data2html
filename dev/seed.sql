-- Datos de desarrollo para examples/semantic/ventas.yaml
CREATE TABLE fact_ventas (
  pedido_id   int,
  fecha_venta date,
  region_desc text,
  canal       text,
  monto_bruto numeric(12,2),
  descuento   numeric(12,2)
);
INSERT INTO fact_ventas
SELECT g,
       DATE '2025-01-01' + (g % 600),
       (ARRAY['Norte','Centro','Sur','Bajío'])[1 + g % 4],
       (ARRAY['Tienda','Web','Mayoreo'])[1 + g % 3],
       round((100 + random() * 900)::numeric, 2),
       round((random() * 50)::numeric, 2)
FROM generate_series(1, 50000) g;
CREATE USER d2h_reader PASSWORD 'd2h';
GRANT SELECT ON fact_ventas TO d2h_reader;
