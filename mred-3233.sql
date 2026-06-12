select * from gen_obra where estado=5;
select * from gen_obra_ppi_cabecera; 
-- escenario 1.
SELECT 
go.NUMERO_OBRA, go.COD_UBICACION, gut.DESC_UBICACION, go.FECHA_INICIO, go.FECHA_FIN 
FROM gen_obra go
INNER JOIN gen_uts_ubicaciontecnica gut ON gut.COD_UBICACION = go.COD_UBICACION 
WHERE go.NUMERO_OBRA = 82134565 
AND gut.COD_UBICACION = 'S3010-M030K' ;


SELECT 
gopc.COD_TIPO_PPI_CABECERA, 
obs.COD_PPI_OBSERVACION, 
obs.TEXTO, gopc.NUMERO_OBRA,
mppic.DESCRIPCION, mppic.TIPO,
mppic.ACTIVIDAD, mppic.DESCRIPCION,  
utseq.COD_EQUIPO AS 'CODIGO EQUIPO', 
utseq.DESC_EQUIPO AS 'DESCRIPCION',
utseq.COD_UBICACION_SAP AS 'SISTEMA', 
utseq.FAB_ACTIVO_FIJO AS 'FABRICANTE', 
utseq.TIPO AS 'DENOMINACION TIPO', 
utseq.ANYO_CONSTRUCCION AS 'AÑO FABRICACION'
FROM gen_obra_ppi_cabecera gopc 
INNER JOIN gen_maestro_obra_tipo_ppi_cabecera mppic ON mppic.COD_TIPO_PPI_CABECERA = gopc.COD_TIPO_PPI_CABECERA
INNER JOIN gen_uts_equipo utseq ON utseq.COD_EQUIPO = gopc.COD_EQUIPO
INNER JOIN gen_obra_ppi_observaciones obs ON gopc.NUMERO_OBRA = obs.NUMERO_OBRA
WHERE mppic.CLASE_OBJETO = 'DS_INT' 
AND gopc.NUMERO_OBRA = 82134599;




/*Obtener Documentos*/
SELECT
    ROW_NUMBER() OVER (ORDER BY COD_PPI_ITEM) AS NUMERO,
    COD_PPI_ITEM,
    COUNT(*) OVER () AS TOTAL_REGISTROS,
    CONCAT('Item ', ROW_NUMBER() OVER (ORDER BY COD_PPI_ITEM)) AS ITEM,
    CONCAT('Documento ', ROW_NUMBER() OVER (ORDER BY COD_PPI_ITEM), ' de ', COUNT(*) OVER ()) AS LITERAL
FROM gen_obra_ppi_item_foto
WHERE NUMERO_OBRA = 82134599
GROUP BY COD_PPI_ITEM
ORDER BY COD_PPI_ITEM;

-- Los documentos por Item
SELECT NOM_FICHERO FROM gen_obra_ppi_item_foto WHERE COD_PPI_ITEM='157850AB89'; 
  
/*Obtener Equipos de inspeccion*/
/*cabecera*/
SELECT 
'resumen de la obra',
go.NUMERO_OBRA, 
go.COD_UBICACION, 
gut.DESC_UBICACION, 
go.FECHA_INICIO, 
go.FECHA_FIN 
FROM gen_obra go
INNER JOIN gen_uts_ubicaciontecnica gut ON gut.COD_UBICACION = go.COD_UBICACION 
WHERE go.NUMERO_OBRA = 82134599 
and gut.COD_UBICACION = 'S3010';

/*cada item*/
SELECT
    COD_PPI_ITEM,
    'Equipos de medida',
    CONCAT('Item ', ROW_NUMBER() OVER (ORDER BY COD_PPI_ITEM)) AS LITERAL
FROM gen_obra_ppi_equipos_inspeccion OEI
WHERE OEI.NUMERO_OBRA = 82134599
GROUP BY COD_PPI_ITEM
ORDER BY COD_PPI_ITEM;

/*El listado para cada item*/
SELECT   
	COD_PPI_ITEM,
    OEI.DEN_TIPO AS MAP_DEN_TIPO,        
    -- OEI.COD_EQUIPO AS MAP_COD_EQUIPO,       
    CONCAT(OEI.FABRICANTE,'/',OEI.MODELO) AS MAP_FABRICANTE_MODELO,
   -- OEI.EQKTX AS MAP_DESCRIPCION,      
    -- OEI.FABRICANTE AS MAP_FABRICANTE,     
    -- OEI.MODELO AS MAP_MODELO,     
    OEI.NUM_SERIE AS MAP_SERIE
FROM gen_obra_ppi_equipos_inspeccion OEI   
WHERE OEI.COD_PPI_ITEM = '6F885B4998';

82134563
82134565
82134566
82134599
-- gen_obra_ppi_cabecera -> revision