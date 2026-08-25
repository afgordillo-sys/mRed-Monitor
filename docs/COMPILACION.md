# Compilación por entornos — Mred_Monitor

Manual de `build.py`, el compilador que genera los ficheros de configuración y plantillas
para cada entorno (int y prod) a partir de una única fuente parametrizada.

---

## Índice

1. [Qué problema resuelve](#1-qué-problema-resuelve)
2. [Cómo funciona](#2-cómo-funciona)
3. [Configuración: los ficheros `.env`](#3-configuración-los-ficheros-env)
4. [Cómo compilar](#4-cómo-compilar)
5. [Pasos para desplegar](#5-pasos-para-desplegar)
6. [Añadir un placeholder nuevo](#6-añadir-un-placeholder-nuevo)
7. [Añadir un entorno nuevo](#7-añadir-un-entorno-nuevo)
8. [Qué NO toca el compilador](#8-qué-no-toca-el-compilador)
9. [Validaciones y mensajes de error](#9-validaciones-y-mensajes-de-error)
10. [Problemas conocidos](#10-problemas-conocidos)

---

## 1. Qué problema resuelve

Antes, los ficheros de la raíz del repositorio **eran la variante de integración**: llevaban
el host y el código de repositorio de INT escritos a mano. Para desplegar en producción
había que repetir las mismas sustituciones manualmente y guardar el resultado en `env/prod/`.

Ese proceso manual causaba dos problemas:

- **Errores de sustitución.** En `env/prod/TemplateBT.xml` una ruta quedó como
  `'var/www/...'`, sin la barra inicial, porque se editó a mano.
- **Desincronización.** 10 plantillas de la raíz nunca llegaron a `env/prod/`.

Ahora hay **una sola fuente** (los ficheros de la raíz, con placeholders) y un comando que
genera cada entorno. Lo que varía entre entornos vive en los `.env`, no repartido por 26 ficheros.

### Lo que realmente cambia entre entornos

Solo tres valores. Todo lo demás es idéntico:

| Concepto | int | prod |
|----------|-----|------|
| Host del vhost | `xoneideintcore.com` | `xoneidecore.com` |
| Código ReplicaFiles | `1KEGG99N` | `AAUMWQVC` |
| Host de healthz | `localhost` | `192.168.1.14` |

---

## 2. Cómo funciona

```
        FUENTE (raíz del repo)                      SALIDA
   ┌──────────────────────────────┐        ┌──────────────────────┐
   │ TemplateAp.xml               │        │ dist/int/            │
   │ TemplateCt.xml               │        │   TemplateAp.xml     │
   │ ... 24 .xml                  │        │   ... 24 .xml        │
   │ monitor_avisos.json          │───▶    │   config/            │
   │ monitor_otros.json           │        │     monitor_*.json   │
   │ monitor_pdf.json             │        ├──────────────────────┤
   └──────────────────────────────┘        │ dist/prod/           │
                  ▲                        │   (misma estructura) │
                  │                        └──────────────────────┘
        ┌─────────┴──────────┐
        │ .env  (común)      │
        │ .env.int           │
        │ .env.prod          │
        └────────────────────┘
```

**Ficheros fuente.** `build.py` escanea **solo el nivel superior** de la raíz buscando
`.xml`, `.json` y `.html`. Al no ser recursivo, `config/`, `env/`, `dist/`, `.git/` y
`.claude/` quedan fuera por construcción: el compilador no puede escribir en las carpetas
protegidas ni leerlas como fuente.

**Reparto en destino.** Los `monitor_*.json` van a `dist/<entorno>/config/`, replicando la
disposición real del servidor. Cualquier otro fichero va a `dist/<entorno>/`.

**Sintaxis de placeholder.** `{{CLAVE}}`, con una regex deliberadamente estricta:

```
\{\{([A-Z][A-Z0-9_]*)\}\}
```

Solo mayúsculas, dígitos y `_`, **sin espacios**. Esto es lo que evita colisionar con
Scriban en las plantillas HTML, que siempre lleva espacios, minúsculas o puntos:
`{{ if data }}`, `{{ for elm in data }}`, `{{elm.MAP_TITLE}}`. Ninguna de esas formas
encaja en la regex.

**Clave desconocida.** Si aparece un `{{ALGO}}` que no está definido, el compilador lo
**deja intacto**, nunca lo sustituye por cadena vacía. En `.xml` y `.json` eso además es un
error que aborta el build; en `.html` es solo un aviso, porque puede ser Scriban legítimo.

**Finales de línea.** Se preservan tal cual. El proyecto tiene ficheros con CRLF y otros
con LF, y el compilador respeta lo que traiga cada uno, sin BOM.

---

## 3. Configuración: los ficheros `.env`

Tres ficheros en la raíz del repositorio:

| Fichero | Contenido |
|---------|-----------|
| `.env` | Claves comunes a todos los entornos |
| `.env.int` | Valores de integración |
| `.env.prod` | Valores de producción |

`.env.<entorno>` **sobrescribe** lo que declare `.env`. Formato `CLAVE=valor`, una por línea;
las líneas vacías y las que empiezan por `#` se ignoran.

### Estado actual

`.env` — la estructura de rutas, común a todos los entornos:

```
MONITOR_PATH=/var/www/vhosts/{{VHOST}}/core/xonemonitorcore/Monitor/
REPOSITORY_PATH=/var/www/vhosts/{{VHOST}}/xonerepository/
REPLICA_FILES={{REPOSITORY_PATH}}ReplicaFiles/{{REPLICA_CODE}}/
```

`.env.int`:

```
VHOST=xoneideintcore.com
REPLICA_CODE=1KEGG99N
HEALTHZ_HOST=localhost
```

`.env.prod`:

```
VHOST=xoneidecore.com
REPLICA_CODE=AAUMWQVC
HEALTHZ_HOST=192.168.1.14
```

### Dos detalles importantes

**Los valores admiten `{{...}}` anidado.** `MONITOR_PATH` referencia a `VHOST`, y
`REPLICA_FILES` referencia a `REPOSITORY_PATH` y a `REPLICA_CODE`. Se resuelven
recursivamente, con detección de ciclos (máximo 10 pasadas). Gracias a eso, cambiar el host
de un entorno es editar **una sola línea**.

**La barra final va dentro del valor.** `MONITOR_PATH` acaba en `/`, igual que hace
`##GP_MONITORPATH##` en runtime. Así el uso en los ficheros queda
`{{MONITOR_PATH}}ide_iberdrola.png`, sin barra suelta.

### Claves disponibles

| Clave | Para qué sirve | Usos |
|-------|----------------|------|
| `MONITOR_PATH` | Carpeta `Monitor/` del servidor: logos, QR, plantillas HTML, scripts | 90 |
| `REPLICA_FILES` | Carpeta de ficheros replicados, incluye el código de repositorio | 27 |
| `REPOSITORY_PATH` | Raíz de `xonerepository/`, para rutas de borrado de ficheros | 3 |
| `HEALTHZ_HOST` | Host del endpoint de healthcheck | 1 |
| `VHOST` | Host del vhost. No se usa directo, solo dentro de otras claves | — |
| `REPLICA_CODE` | Código de repositorio. Solo dentro de `REPLICA_FILES` | — |

Total: **121 sustituciones** en 26 ficheros.

---

## 4. Cómo compilar

Requiere Python 3 y nada más: `build.py` usa solo librería estándar.

```bash
python build.py                 # compila todos los entornos detectados
python build.py -e prod         # solo prod
python build.py -e int prod     # varios entornos
python build.py --list          # lista los entornos detectados
python build.py --check         # valida sin escribir nada (dry-run)
python build.py --clean         # borra dist/ antes de compilar
python build.py --help          # ayuda
```

Salida de una compilación correcta:

```
Compilando 27 fichero(s) para: int, prod
[int] OK: 27 fichero(s) escritos en dist/int/, 121 sustitucion(es)
[prod] OK: 27 fichero(s) escritos en dist/prod/, 121 sustitucion(es)
Terminado sin errores.
```

El comando devuelve **código de salida 0** si todo fue bien y **1** si hubo cualquier error,
así que sirve tal cual en un script o en integración continua.

`dist/` está en `.gitignore`: es un artefacto generado, no se versiona.

---

## 5. Pasos para desplegar

### 1. Editar la fuente

Se edita **siempre** el fichero de la raíz, nunca el de `dist/` ni el de `env/`. Si la
modificación incluye una ruta del servidor, se usa el placeholder en lugar del valor literal:

```xml
<!-- MAL: valor literal de un entorno -->
'/var/www/vhosts/xoneideintcore.com/core/xonemonitorcore/Monitor/logo.png' AS MAP_LOGO,

<!-- BIEN: placeholder -->
'{{MONITOR_PATH}}logo.png' AS MAP_LOGO,
```

### 2. Validar antes de compilar

```bash
python build.py --check
```

No escribe nada. Detecta placeholders sin definir, JSON roto y XML roto. Si esto falla, se
corrige antes de seguir.

### 3. Compilar

```bash
python build.py --clean
```

`--clean` garantiza que no quede en `dist/` ningún fichero de una compilación anterior.

### 4. Revisar el resultado

Que no haya quedado ningún placeholder sin resolver:

```bash
grep -rE "\{\{[A-Z][A-Z0-9_]*\}\}" dist/
```

Que en prod no se haya colado nada de integración:

```bash
grep -rE "xoneideintcore|1KEGG99N" dist/prod/
```

Las dos órdenes deben devolver **vacío**.

### 5. Subir al servidor

Se sube el contenido de `dist/<entorno>/` respetando la estructura:

| Origen | Destino en el servidor |
|--------|------------------------|
| `dist/prod/*.xml` | `/var/www/vhosts/xoneidecore.com/core/xonemonitorcore/Monitor/` |
| `dist/prod/config/monitor_*.json` | la carpeta `config/` del monitor |

> Las imágenes (`ide_iberdrola.png`, `Apoyo_Etiquetado_*.png`, `carta_*.png`), la plantilla
> `Resumen_diario_plantilla.html` y la credencial de Firebase ya están en el servidor y no
> forman parte de la compilación.

### 6. Commitear la fuente

Se commitean los cambios de la raíz y de los `.env`. **`dist/` no se commitea.**

---

## 6. Añadir un placeholder nuevo

Cuando aparezca un valor nuevo que cambie entre entornos:

1. **Declarar la clave** en `.env.int` y `.env.prod` con el valor de cada entorno. Si el
   valor se construye a partir de otro (por ejemplo, cuelga de `{{VHOST}}`), declararlo en
   `.env` usando `{{...}}` anidado y dejar solo la parte variable en los `.env.<entorno>`.

2. **Sustituir en los ficheros fuente.** El nombre debe ser MAYÚSCULAS, dígitos y `_`, sin
   espacios, o la regex no lo reconocerá.

3. **Validar:**
   ```bash
   python build.py --check
   ```
   Si la clave falta en algún entorno, el comando dice exactamente `fichero:línea`.

### Ejemplo: parametrizar el correo de alertas

```
# .env.int
MAIL_ALERTAS=afgordillo@xone.es

# .env.prod
MAIL_ALERTAS=soporte.mred@iberdrola.es
```

Y en `monitor_otros.json`, cambiar `"to": "afgordillo@xone.es"` por `"to": "{{MAIL_ALERTAS}}"`.

---

## 7. Añadir un entorno nuevo

Los entornos se **autodescubren** a partir de los ficheros `.env.*`. No hay que tocar código.

Para añadir un `pre`, basta crear `.env.pre` con las mismas claves:

```
VHOST=xoneidepre.com
REPLICA_CODE=XXXXXXXX
HEALTHZ_HOST=10.0.0.5
```

Y comprobar que aparece:

```bash
python build.py --list
python build.py -e pre
```

---

## 8. Qué NO toca el compilador

Distinguir bien estas familias evita romper cosas:

| Sintaxis | Quién la resuelve | ¿La toca `build.py`? |
|----------|-------------------|----------------------|
| `{{CLAVE}}` | **`build.py`, al compilar** | **Sí** |
| `##GP_*##` | XoneMonitorCore, desde el `appsettings.json` del servidor | No |
| `##ROW_*##`, `##CHKNAME##`, `##APPNAME##`, `##EXCEPTION##` | Runtime del monitor (fila SQL / contexto) | No |
| `##FLD_*##`, `##ID##`, `##PAGE##`, `##TOTAL_PAGES##` | Runtime de XOnePDFController | No |
| `{{ if ... }}`, `{{elm.CAMPO}}` | Scriban, al generar el HTML | No |

Los `##GP_*##` ya son un mecanismo de entorno **en runtime**, y por eso `monitor_pdf.json`
no necesita ni un solo placeholder: usa `##GP_MONITORPATH##` y `##GP_REPLICAFILES##`.

**Regla práctica:** si el valor lo resuelve el servidor al ejecutar, se usa `##GP_*##`. Si
hay que fijarlo al generar el fichero, se usa `{{CLAVE}}`.

`config/` y `env/` son de **solo lectura** y el compilador nunca escribe en ellas.

---

## 9. Validaciones y mensajes de error

Si alguna validación falla, **no se escribe ningún fichero de ese entorno**: nunca queda un
`dist/` a medias.

| Validación | Comportamiento |
|------------|----------------|
| Placeholder sin definir en `.xml` / `.json` | **Error**, con `fichero:línea` |
| Placeholder sin definir en `.html` | Aviso; se deja intacto (posible Scriban) |
| El JSON generado no parsea | **Error** |
| El XML generado no parsea | **Error**, solo si la fuente sí parseaba |
| Clave definida y no usada | Aviso |
| Referencia circular en el `.env` | **Error** |
| Entorno inexistente | **Error**, lista los disponibles |

La validación del XML solo se exige si el fichero fuente ya era XML bien formado. Así una
plantilla que hoy no lo sea no bloquea la compilación, pero sí se detecta si la sustitución
la rompe.

### Ejemplos

```
[int] ERROR: monitor_otros.json:517: {{RUTA_NUEVA}} no esta definida en int
[int] FALLIDO: 1 error(es), no se ha escrito nada
Terminado CON ERRORES.
```

```
[prod] ERROR: la clave X referencia {{NO_EXISTE}}, que no esta definida
```

```
ERROR: entorno(s) desconocido(s): pre
       disponibles: int, prod
```

---

## 10. Problemas conocidos

### No uses `sed -i` sobre los ficheros del proyecto

**`sed -i` en Git Bash sobre Windows elimina todos los CR de los ficheros con CRLF.** El
proyecto tiene 20 ficheros con CRLF y 7 con LF; una pasada de `sed -i` reescribe los
primeros por completo y el diff resultante es el fichero entero, no la línea que querías
cambiar.

Para sustituciones masivas, hazlas en binario con Python:

```python
data = path.read_bytes()
path.write_bytes(data.replace(b"antes", b"despues"))
```

`build.py` ya hace lo correcto: lee y escribe con `newline=""`, sin traducir nada.

Ojo también con `grep -c`, que cuenta **líneas** con coincidencia, no caracteres. Para
contar CR de verdad:

```bash
tr -cd '\r' < fichero | wc -c
```

### Cómo comprobar que la parametrización no perdió nada

Como la raíz **es** la variante de integración, `dist/int` tiene que reproducir los
ficheros originales **byte a byte**. Es la prueba más fiable ante cualquier duda:

```bash
# 1. Guardar el estado actual antes de tocar nada
mkdir -p /tmp/baseline && cp *.xml *.json /tmp/baseline/

# 2. Hacer los cambios y compilar
python build.py --clean

# 3. Comparar
for f in /tmp/baseline/*; do
  n=$(basename "$f")
  case "$n" in monitor_*.json) d=dist/int/config/$n ;; *) d=dist/int/$n ;; esac
  cmp -s "$f" "$d" || echo "DIFIERE: $n"
done
```

No debe imprimir nada.

### Los `env/` están desincronizados

`env/int` y `env/prod` son fotos manuales de lo desplegado, con fechas dispares, y les
faltan plantillas. **No son fuente de nada.** Sirven como referencia histórica; la fuente
es la raíz del repositorio.

---

## Ficheros relacionados

| Fichero | Qué es |
|---------|--------|
| `build.py` | El compilador |
| `.env` | Claves comunes |
| `.env.int`, `.env.prod` | Valores por entorno |
| `.gitignore` | Ignora `env/` y `dist/` |
| `docs/FICHEROS_BD.md` | Qué tablas de BD almacenan ficheros e imágenes |
