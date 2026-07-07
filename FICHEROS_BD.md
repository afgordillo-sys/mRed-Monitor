# Estructura de ficheros en BD — Mred_Monitor

Documento de referencia para saber qué tablas almacenan ficheros/imágenes y cómo consultarlos según el tipo de caso. Derivado del análisis de todas las plantillas XML del proyecto.

---

## Resumen de tablas de ficheros

| Tabla | Campo fichero | Clave | Aplica en |
|-------|--------------|-------|-----------|
| `gen_ot_fotos` | NOMBRE_FICHERO | NUMEROORDEN | Apoyos, CT, LDPEN, UTS |
| `gen_an_foto` | NOMBRE_FICHERO | via gen_an_anomalia → NUMEROORDEN | Casi todas las plantillas |
| `gen_rd_ot_equipos_afectados` | IMG_EQUIPO | NUMEROORDEN | Solo robos/daños (TemplateRD, TemplateDRADRS) |
| `gen_ri_ot_fotos` | NOMBRE_FICHERO | NUMEROORDEN | Solo TemplateCt.xml |
| `gen_ri_ot_fotos` | NOMBRE_FICHERO | COD_REC_OT_CABECERA | Solo TemplateCtRecin.xml |
| `gen_obra_ppi_item_foto` | NOM_FICHERO | NUMERO_OBRA + COD_PPI_ITEM | Obras PPI (plantillaObra, E2, E4, E6) |

---

## GRUPO A — Ficheros por NUMEROORDEN (OTs)

### Clasificación por plantilla

| Plantilla | Tipo de OT | Tablas de ficheros |
|-----------|------------|--------------------|
| TemplateAp.xml | Apoyos (línea aérea) | gen_ot_fotos (TERMOGRAFIA, NO_ACCESIBLE, AVISO) + gen_an_foto |
| TemplateBT.xml | Baja Tensión | gen_an_foto |
| TemplateCt.xml | Centros de Transformación | gen_ot_fotos (TERMOGRAFIA, NO_ACCESIBLE) + gen_an_foto + gen_ri_ot_fotos |
| TemplateCtDT7.xml | CT DT7 | gen_an_foto |
| TemplateCarta.xml | Carta (DR7, DPRP/DPRN, CCM) | gen_an_foto |
| TemplateDPA.xml | DPA | gen_an_foto |
| TemplateDRADRS.xml | Robos/Daños (variante) | gen_rd_ot_equipos_afectados (IMG_EQUIPO) |
| TemplateLDPEN.xml | LDPEN | gen_ot_fotos (TERMOGRAFIA) + gen_an_foto |
| TemplateLDT7.xml | LDT7 | gen_an_foto |
| TemplateLDT8.xml | LDT8 | gen_an_foto |
| TemplateOther.xml | Otras (genérico) | — sin ficheros — |
| TemplateOther_2.xml | Otras 2 | — sin ficheros — |
| TemplateRD.xml | Robos/Daños | gen_rd_ot_equipos_afectados (IMG_EQUIPO) |
| TemplateTSub.xml | Subestaciones | gen_an_foto |
| TemplateUTS.xml | UTS | gen_ot_fotos (EVIDENCIAS_PREV_UTS, EVIDENCIAS_UTS) + gen_an_foto |

---

### A.1 — gen_ot_fotos (Apoyos, CT, LDPEN, UTS y otras)

Tipos de foto usados en las plantillas:
- `TERMOGRAFIA` — fotos de termografía (Ap, Ct, LDPEN)
- `NO_ACCESIBLE` — elemento no accesible (Ap, Ct)
- `AVISO` — foto del aviso (Ap)
- `EVIDENCIAS_PREV_UTS` — evidencias previas (UTS)
- `EVIDENCIAS_UTS` — evidencias fin trabajo (UTS)

```sql
SELECT
  f.NUMEROORDEN,
  f.NOMBRE_FICHERO,
  f.TIPO,
  f.DESCRIPCION,
  f.PROCESADO,
  f.BAJA,
  f.ORIGEN,
  f.COD_BRIGADA,
  CONCAT('/var/www/vhosts/xoneideintcore.com/xonerepository/ReplicaFiles/1KEGG99N/', f.NOMBRE_FICHERO) AS RUTA
FROM gen_ot_fotos f
WHERE f.NUMEROORDEN = 'XXXXXXXXX'
  AND IFNULL(f.BAJA, 0) = 0
ORDER BY f.PROCESADO ASC, f.TIPO
```

---

### A.2 — gen_an_foto (via gen_an_anomalia — casi todas las plantillas)

```sql
SELECT
  a.NUMEROORDEN,
  a.ORDEN_ORIGEN,
  a.ORDEN_ACTUALIZACION,
  a.COD_AN_ANOMALIA,
  a.CODIGO_AVISO_GAMAD,
  a.LOCALIZACION,
  f.NOMBRE_FICHERO,
  f.COD_TIPO_FOTO,
  IFNULL(f.BAJA, 0) AS BAJA,
  CONCAT('/var/www/vhosts/xoneideintcore.com/xonerepository/ReplicaFiles/1KEGG99N/', f.NOMBRE_FICHERO) AS RUTA
FROM gen_an_anomalia a
INNER JOIN gen_an_foto f
  ON (
      NULLIF(IFNULL(f.COD_AN_ANOMALIA,''), '') = a.COD_AN_ANOMALIA
      OR NULLIF(IFNULL(f.CODIGO_AVISO_GAMAD,''), '') = a.CODIGO_AVISO_GAMAD
  )
WHERE (
    a.ORDEN_ORIGEN           = 'XXXXXXXXX'
    OR a.NUMEROORDEN         = 'XXXXXXXXX'
    OR a.ORDEN_ACTUALIZACION = 'XXXXXXXXX'
  )
  AND IFNULL(f.BAJA, 0) = 0
  AND LOWER(SUBSTRING_INDEX(f.NOMBRE_FICHERO, '.', -1)) IN ('png','jpg','jpeg')
```
> `gen_an_anomalia` tiene tres campos de OT: ORDEN_ORIGEN, NUMEROORDEN, ORDEN_ACTUALIZACION. Se busca en los tres.

---

### A.3 — gen_rd_ot_equipos_afectados (solo robos/daños: TemplateRD, TemplateDRADRS)

```sql
SELECT
  afec.NUMEROORDEN,
  afec.IMG_EQUIPO,
  CONCAT('/var/www/vhosts/xoneideintcore.com/xonerepository/ReplicaFiles/1KEGG99N/', afec.IMG_EQUIPO) AS RUTA
FROM gen_rd_ot_equipos_afectados afec
WHERE afec.NUMEROORDEN = 'XXXXXXXXX'
  AND afec.IMG_EQUIPO IS NOT NULL
  AND afec.IMG_EQUIPO <> ''
```

---

### A.4 — gen_ri_ot_fotos (solo TemplateCt.xml — CTs con OT de inspección)

```sql
SELECT
  f.NUMEROORDEN,
  f.NOMBRE_FICHERO,
  f.TABLA,
  f.G3E_FID,
  f.G3E_FNO,
  f.COD_TIPO_FOTO,
  m.DESC_TIPO_FOTO,
  CONCAT('/var/www/vhosts/xoneideintcore.com/xonerepository/ReplicaFiles/1KEGG99N/', f.NOMBRE_FICHERO) AS RUTA
FROM gen_ri_ot_fotos f
LEFT JOIN gen_ri_maestro_tipo_fotos m ON m.COD_TIPO_FOTO = f.COD_TIPO_FOTO
WHERE f.NUMEROORDEN = 'XXXXXXXXX'
  AND IFNULL(f.BAJA, 0) = 0
  AND LOWER(SUBSTRING_INDEX(f.NOMBRE_FICHERO, '.', -1)) IN ('png','jpg','jpeg')
```
> En TemplateCtRecin.xml se usa COD_REC_OT_CABECERA en lugar de NUMEROORDEN (ver Grupo B).

---

### A.5 — PDF de resumen de OT pendiente de generar

```sql
SELECT
  O.NUMEROORDEN,
  O.CLASE_ORDEN,
  O.CLASE_ACTIVIDAD,
  O.AREA_EMPRESA,
  IFNULL(O.PDF_CREADO, 0) AS PDF_CREADO,
  O.NOMBRE_FICHERO_PDF,
  m.PDF_PLANTILLA
FROM gen_ot_cabecera O
LEFT JOIN monitor_ot_pdf_generate m
  ON IFNULL(O.AREA_EMPRESA,'') LIKE CONCAT(m.AREA_EMPRESA,'%')
  AND IFNULL(m.CLASE_ACTIVIDAD, O.CLASE_ACTIVIDAD) LIKE CONCAT('%', O.CLASE_ACTIVIDAD, '%')
  AND IFNULL(m.CLASE_ORDEN, O.CLASE_ORDEN) = O.CLASE_ORDEN
  AND IFNULL(m.NO_CLASE_ACTIVIDAD,'') NOT LIKE CONCAT('%', O.CLASE_ACTIVIDAD, '%')
  AND IFNULL(m.NO_CLASE_ORDEN,'') NOT LIKE CONCAT('%', O.CLASE_ORDEN, '%')
WHERE O.NUMEROORDEN = 'XXXXXXXXX'
  AND IFNULL(O.PDF_CREADO, 0) = 0
  AND m.PDF_PLANTILLA IS NOT NULL
```
> Si devuelve resultado → PDF pendiente. El estado en `gen_ot_estados` debe ser 5 para que el monitor lo genere.

---

## GRUPO B — Ficheros por COD_REC_OT_CABECERA (Recepciones CT — TemplateCtRecin.xml)

Entidad independiente de las OTs. Corresponde a recepciones de Centros de Transformación.

### B.1 — gen_ri_ot_fotos (fotos de revisión de elementos de CT)

```sql
SELECT
  f.COD_REC_OT_CABECERA,
  f.NOMBRE_FICHERO,
  f.TABLA,
  f.G3E_FID,
  f.G3E_FNO,
  f.COD_TIPO_FOTO,
  m.DESC_TIPO_FOTO,
  CONCAT('/var/www/vhosts/xoneideintcore.com/xonerepository/ReplicaFiles/1KEGG99N/', f.NOMBRE_FICHERO) AS RUTA
FROM gen_ri_ot_fotos f
LEFT JOIN gen_ri_maestro_tipo_fotos m ON m.COD_TIPO_FOTO = f.COD_TIPO_FOTO
WHERE f.COD_REC_OT_CABECERA = 'XXXXXXXXX'
  AND IFNULL(f.BAJA, 0) = 0
  AND LOWER(SUBSTRING_INDEX(f.NOMBRE_FICHERO, '.', -1)) IN ('png','jpg','jpeg')
```

### B.2 — PDF de recepción pendiente

```sql
SELECT
  O.COD_REC_OT_CABECERA,
  O.COD_ESTADO,
  O.PROCESADO,
  IFNULL(O.PDF_CREADO, 0) AS PDF_CREADO,
  O.NOMBRE_FICHERO_PDF
FROM gen_rec_ot_cabecera O
WHERE O.COD_REC_OT_CABECERA = 'XXXXXXXXX'
  AND IFNULL(O.PDF_CREADO, 0) = 0
```

---

## GRUPO C — Ficheros por NUMERO_OBRA (Obras PPI)

Entidad independiente. Plantillas: `plantillaObra.xml`, `plantillaE2.xml`, `plantillaE4.xml`, `plantillaE6.xml`.

### C.1 — gen_obra_ppi_item_foto (documentos/imágenes por ítem de inspección)

```sql
SELECT
  f.NUMERO_OBRA,
  f.COD_PPI_ITEM,
  f.NOM_FICHERO,
  CONCAT('/var/www/vhosts/xoneideintcore.com/xonerepository/ReplicaFiles/1KEGG99N/', f.NOM_FICHERO) AS RUTA
FROM gen_obra_ppi_item_foto f
WHERE f.NUMERO_OBRA = XXXXXXXXX
  AND IFNULL(f.BAJA, 0) = 0
ORDER BY f.COD_PPI_ITEM
```
> Para filtrar por ítem concreto añadir: `AND f.COD_PPI_ITEM = 'XXXXXXXXX'`

### C.2 — PDF de obra pendiente

```sql
SELECT
  cab.NUMERO_OBRA,
  cab.COD_PPI_CABECERA,
  cab.ESTADO,
  IFNULL(cab.CREACION_PDF, 0) AS CREACION_PDF,
  cab.NOMBRE_FICHERO_PDF
FROM gen_obra_ppi_cabecera cab
WHERE cab.NUMERO_OBRA = XXXXXXXXX
  AND IFNULL(cab.CREACION_PDF, 0) = 0
```

---

## Ruta base de ficheros en servidor

Todos los ficheros se almacenan en:
```
/var/www/vhosts/xoneideintcore.com/xonerepository/ReplicaFiles/1KEGG99N/{NOMBRE_FICHERO}
```

---

## Fuentes del análisis
- `monitor_pdf.json` — lógica de generación de PDFs y tabla `monitor_ot_pdf_generate`
- `TemplateAp.xml` — tipos TERMOGRAFIA, NO_ACCESIBLE, AVISO en gen_ot_fotos
- `TemplateCt.xml` — gen_ri_ot_fotos por NUMEROORDEN
- `TemplateCtRecin.xml` — gen_ri_ot_fotos por COD_REC_OT_CABECERA
- `TemplateUTS.xml` — tipos EVIDENCIAS_PREV_UTS, EVIDENCIAS_UTS en gen_ot_fotos
- `TemplateDRADRS.xml`, `TemplateRD.xml` — gen_rd_ot_equipos_afectados (IMG_EQUIPO)
- `plantillaObra.xml`, `plantillaE4.xml` — gen_obra_ppi_item_foto (NOM_FICHERO)
- Todas las plantillas Template*.xml — gen_an_foto (FotosAnomalias)
