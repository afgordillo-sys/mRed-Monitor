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

| Clave | Para qué sirve | Tipo | Usos |
|-------|----------------|------|------|
| `MONITOR_PATH` | Carpeta `Monitor/` del servidor: logos, QR, plantillas HTML, scripts | texto | 90 |
| `REPLICA_FILES` | Carpeta de ficheros replicados, incluye el código de repositorio | texto | 27 |
| `REPOSITORY_PATH` | Raíz de `xonerepository/`, para rutas de borrado de ficheros | texto | 3 |
| `DB_SCHEMA` | Esquema de base de datos, dentro de consultas SQL | texto | 3 |
| `HEALTHZ_HOST` | Host del endpoint de healthcheck | texto | 1 |
| `<CHECKING>_ENABLED` | 13 flags, uno por checking. Ver abajo | **booleano** | 13 |
| `BORRADOLOGS_API` | Acción de borrado de logs de la API: existe en int, no en prod | **objeto JSON** | 1 |
| `VHOST` | Host del vhost. No se usa directo, solo dentro de otras claves | texto | — |
| `REPLICA_CODE` | Código de repositorio. Solo dentro de `REPLICA_FILES` | texto | — |

Total: **138 sustituciones** en 26 ficheros.

### Flags de checkings

Convención: la clave es **el nombre del checking más el sufijo `_ENABLED`**. Así se sabe
de un vistazo a qué checking corresponde cada flag, y darle uno nuevo a otro checking no
requiere inventar nada.

Los 13 avisos informativos de `monitor_avisos.json` están **apagados en integración y
encendidos en producción**, para que integración no genere alertas:

| Checking | int | prod |
|----------|-----|------|
| `I_AVISO_OTS_SIN_ACEPTAR_15` | `false` | `true` |
| `I_AVISO_OTS_SIN_ACEPTAR_30` | `false` | `true` |
| `I_AVISO_OTS_SIN_LLAMAR_GAMAD_POR_TIEMPO_MAS_7_MIN` | `false` | `true` |
| `I_CAMBIO_IMEI_ANDROID12` | `false` | `true` |
| `I_DISP_10KOP_PENDIENTES` | `false` | `true` |
| `I_ERRORES_LIVE_MRED` | `false` | `true` |
| `I_ERRORES_REPLICA_MRED` | `false` | `true` |
| `I_ERROR_API_URGENTE_1` | `false` | `true` |
| `I_ESTAD0S_SIN_PROCESAR_MAS10MIN` | `false` | `true` |
| `I_ESTAD0S_SIN_PROCESAR_MAS10MIN_SIN_TASK_ID` | `false` | `true` |
| `I_PDF_SIN_GENERAR_24_HORAS` | `false` | `true` |
| `I_PROCESADO99_MAS1HORA_HOY` | `false` | `true` |
| `I_RESUMEN_DIARIO` | `false` | `true` |

Cada uno tiene su propia clave, así que encender o apagar cualquiera es editar una línea
del `.env` de ese entorno, sin afectar a los demás.

> **No todos los `enable` llevan flag, y es correcto.** `I_REVISAR_ERRORES_API`,
> `I_CARGA_100KOP_INVENTARIO` y `I_AVISO_OTS_SIN_LLAMAR_GAMAD_20` están en `false` en los
> **dos** entornos, así que siguen fijos en la fuente. Solo se parametriza lo que de verdad
> cambia entre entornos.

### Valores que no son texto: booleanos y números

En JSON un booleano va **sin comillas**, pero un placeholder tiene que estar dentro del
fichero. Eso deja dos formas y ninguna sirve por sí sola:

| Forma en la fuente | ¿Fuente válida? | Salida |
|--------------------|-----------------|--------|
| `"enable": {{FLAG}}` | **No.** El fichero deja de parsear | `true` — correcto |
| `"enable": "{{FLAG}}"` | Sí | `"true"` — **cadena, tipo incorrecto** |

**La regla:** el placeholder se escribe **entre comillas**, y `build.py` las quita al
generar cuando el valor resuelto es un literal JSON. Así la fuente sigue siendo JSON
válido y la salida lleva el tipo correcto.

```json
"enable": "{{I_CAMBIO_IMEI_ANDROID12_ENABLED}}",
```

```
# .env.int                              # .env.prod
I_CAMBIO_IMEI_ANDROID12_ENABLED=false   I_CAMBIO_IMEI_ANDROID12_ENABLED=true
```

Genera `"enable": false` en int y `"enable": true` en prod, como booleanos reales.

> El tipo importa: en los 3 JSON y en los dos entornos desplegados, `enable` aparece
> **115 veces y siempre como booleano**, nunca como cadena. Solo `continue-if-error` usa
> la forma con comillas.

#### Qué se emite sin comillas

Se intenta interpretar el valor del `.env` como literal JSON. Se acepta si es
`true`, `false`, `null` o un número; cualquier otra cosa se queda como cadena.

| Valor en el `.env` | Resultado |
|--------------------|-----------|
| `true` · `false` · `null` | literal, sin comillas |
| `3` · `-1` · `2.5` | número, sin comillas |
| `localhost` · `mredint` · `1KEGG99N` | cadena (no parsea como JSON) |
| `192.168.1.14` | cadena (no es un número válido) |
| `007` · `01` | cadena (JSON prohíbe ceros a la izquierda) |
| `{"a":1}` · `[1,2]` | objeto o array, sin comillas |
| `True` · `False` (mayúscula de Python) | cadena, **y se avisa** |

Es **una sola regla**: si el valor parsea como JSON, se inyecta con su tipo; si no, se queda
como cadena. Vale igual para un booleano, un número, un objeto o un array.

#### Dos guardas

1. **Solo si ocupa el valor completo.** En
   `"url": "http://{{HEALTHZ_HOST}}:6060/healthz"` el placeholder es parte de una cadena
   mayor, así que se sustituye como texto y las comillas se quedan.
2. **Nunca en una clave de objeto.** Un placeholder usado como clave
   (`"{{X}}": 1`) conserva siempre las comillas, así que no se puede generar JSON inválido
   por esa vía.

En `.xml` y `.html` no aplica: los atributos XML son siempre cadenas.

> **Cuidado con las cadenas de solo dígitos.** Como se admiten números, una clave cuyo
> valor sean solo dígitos pierde las comillas si ocupa un valor entero. Si necesitas que
> un código numérico siga siendo cadena, no lo pongas como valor completo. Para que nunca
> pase desapercibido, `build.py` **declara cada inyección sin comillas** en su salida:
>
> ```
> [prod] sin comillas: I_CAMBIO_IMEI_ANDROID12_ENABLED=true en monitor_avisos.json:46
> ```
>
> Si aparecen más líneas de las que esperabas, mira cuál.

### Elementos de array: inyectar u omitir

Caso distinto: un trozo de configuración que **existe en un entorno y no existe en otro**.
El ejemplo real es la acción que borra los logs de la API, que solo tiene sentido en
integración:

```json
"actions": [
  { "name": "delete-file", "value": "##GP_LOGSMONITORPATH##", ... },
  "{{BORRADOLOGS_API}}",
  { "name": "delete-file", "value": "##GP_LOGSMANAGERPATH##", ... },
```

```
# .env.int
BORRADOLOGS_API={"name":"delete-file","value":"##GP_LOGSAPIPATH##","scan-directory":true,"filter":"*.log","delete-time":"7D"}

# .env.prod  -> vacío a propósito
BORRADOLOGS_API=
```

En int el array sale con 14 acciones; en prod con 13, y el elemento **desaparece con su
coma**, sin dejar `""` ni `null`.

#### Cómo decide la posición

Un placeholder entre comillas se clasifica por el carácter no blanco de antes y de después:

| Antes | Después | Posición | Tratamiento |
|-------|---------|----------|-------------|
| `:` | cualquiera | valor de objeto | inyecta el JSON, o cadena |
| `[` o `,` | `,` o `]` | **elemento de array** | inyecta u omite |
| cualquiera | `:` | clave de objeto | nunca se toca |
| resto | resto | dentro de una cadena mayor | sustitución de texto |

#### Qué vale como valor

En posición de elemento de array la regla es **estricta**, porque en estos ficheros no hay
ningún array con elementos de tipo cadena:

| Valor en el `.env` | Resultado |
|--------------------|-----------|
| vacío | **el elemento se omite**, con una coma adyacente |
| JSON válido | se inyecta verbatim |
| cualquier otra cosa | **error**, indicando qué se esperaba |

La coma se maneja según dónde esté el elemento: si le sigue una coma se elimina esa y la
línea desaparece limpia; si es el último se elimina la coma anterior; si es el único, el
array queda vacío. En los tres casos el resultado es JSON válido, y la validación de salida
lo comprueba.

> **Un vacío olvidado borra configuración.** Es el riesgo de este mecanismo: si alguien
> define la clave y se deja el valor sin rellenar, el elemento desaparece sin más. Por eso
> `build.py` **declara siempre las dos direcciones**:
>
> ```
> [int]  elemento inyectado: BORRADOLOGS_API en monitor_otros.json:814
> [prod] elemento omitido:   BORRADOLOGS_API en monitor_otros.json:814
> ```
>
> Si ves un `omitido` que no esperabas, es que falta un valor. Conviene además dejar un
> comentario en el `.env` cuando el vacío sea deliberado, para que nadie lo "arregle".

#### Por qué no se usa un flag aquí

Porque **una acción no se puede desactivar individualmente**. Según
`references/actions-reference.md` del skill `xone-monitor-generator`, `<action>` solo admite
`name`, `execute-if-error`, `execute-always`, `for-each-row` y `sleep`, más los atributos
propios de cada acción. El `enable` existe en `<checking>` y en `<maintenance>`, nunca en
`<action>` — y las 157 acciones del proyecto lo confirman.

Para un **checking o un maintenance** completo, en cambio, el flag booleano sigue siendo la
vía correcta: es más simple y usa una capacidad documentada del motor.

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

Y, lo más importante antes de tocar producción, **qué checkings cambiarían de estado**.
Compara lo que vas a subir con lo que hay desplegado:

```bash
python - <<'EOF'
import json
for env in ("int", "prod"):
    g = {c["name"]: c.get("enable")
         for c in json.load(open(f"dist/{env}/config/monitor_avisos.json",
                                 encoding="utf-8"))["checkings"]}
    d = {c["name"]: c.get("enable")
         for c in json.load(open(f"env/{env}/config/monitor_avisos.json",
                                 encoding="utf-8"))["checkings"]}
    for n in sorted(set(g) & set(d)):
        if g[n] != d[n]:
            print(f"{env}: {n}  desplegado={d[n]} -> a subir={g[n]}")
EOF
```

Cada línea es un checking que se encenderá o apagará al desplegar. Si alguna no es
intencionada, **no subas el fichero**: parametriza ese `enable` primero.

Ahora mismo esta comprobación **no devuelve nada** en ninguno de los dos entornos: los 18
checkings comunes coinciden exactamente con lo desplegado. Ese es el estado correcto, y
merece la pena ejecutarla cada vez para confirmar que sigue siéndolo.

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
| Placeholder **sin comillas** en un `.json` | **Error** con `fichero:línea` y el arreglo concreto |
| El JSON **fuente** no parsea | **Error** |
| El JSON generado no parsea | **Error** |
| El XML generado no parsea | **Error**, solo si la fuente sí parseaba |
| Valor no vacío y no JSON en un elemento de array | **Error**: debe ser JSON válido o estar vacío |
| Valor `True` / `False` / `None` en posición sin comillas | Aviso: en JSON va en minúscula |
| Clave definida y no usada | Aviso |
| Referencia circular en el `.env` | **Error** |
| Entorno inexistente | **Error**, lista los disponibles |

La validación del XML solo se exige si el fichero fuente ya era XML bien formado. Así una
plantilla que hoy no lo sea no bloquea la compilación, pero sí se detecta si la sustitución
la rompe.

Los `.json` fuente, en cambio, **sí** deben parsear siempre: es lo que garantiza que
editores, formateadores y validadores sigan funcionando sobre ellos. Para medir la sintaxis
del fichero y no la de los valores, los placeholders se neutralizan antes de parsear.

### Ejemplos

```
[int] ERROR: monitor_avisos.json:46: {{FLAG}} sin comillas rompe el JSON fuente.
    Escribelo como "{{FLAG}}": build.py quitara las comillas al generar si el valor
    es booleano, null o numero
[int] FALLIDO: 1 error(es), no se ha escrito nada
Terminado CON ERRORES.
```

```
[int] ERROR: monitor_otros.json:517: {{RUTA_NUEVA}} no esta definida en int
[int] FALLIDO: 1 error(es), no se ha escrito nada
Terminado CON ERRORES.
```

```
[int] ERROR: monitor_otros.json:814: el valor de BORRADOLOGS_API ocupa un elemento de
    array, asi que debe ser JSON valido (un objeto entre llaves) o estar vacio para
    omitir el elemento. Valor actual: delete-file
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

### Checkings que no existen en los dos entornos

Los flags arreglan el caso "está en los dos pero con distinto valor". Queda otro caso: un
checking que **existe o no** según el entorno. La comprobación del paso 4 no lo detecta,
porque solo compara los checkings comunes a ambos lados.

Al leer el resultado, las dos direcciones no pesan igual:

- **Se añadiría** — normalmente es correcto: un checking nuevo, hecho en la fuente y aún
  sin desplegar. Hoy salen `I_AVISO_DISCREPANCIA_CAMPOS_HISTORY`, `CREAR-PDF-OBRAS`,
  `CREAR-PDF_3` y, solo en prod, `CREAR-PDF-CARTA`.
- **Se perdería** — siempre sospechoso: hay algo corriendo en el servidor que la fuente no
  tiene. **Hoy no sale ninguno**, y ese es el estado correcto.

> **`I_AVISO_NO_SELECTIVIDAD` merece un flag.** Está en la fuente con `enable: true`, pero
> solo está desplegado en prod. Compilar int lo **activaría en integración**, que es
> justo lo que los 13 flags evitan para el resto de avisos `I_*`. Si no debe correr en
> integración, necesita su `I_AVISO_NO_SELECTIVIDAD_ENABLED`, apagado en int.

> **Los nombres con guiones no valen como clave.** `CREAR-PDF-CARTA` tendría que usar
> `CREAR_PDF_CARTA_ENABLED`, con guiones bajos, porque la clave debe encajar en
> `[A-Z][A-Z0-9_]*`. En ese caso la convención nombre + `_ENABLED` no se puede aplicar
> literalmente.

Para ver ambas direcciones:

```bash
python - <<'EOF'
import json, re, pathlib
for f in ("monitor_avisos.json", "monitor_pdf.json"):
    for env in ("int", "prod"):
        def nombres(p):
            t = re.sub(r"\{\{[A-Z][A-Z0-9_]*\}\}", "X",
                       pathlib.Path(p).read_text(encoding="utf-8"))
            return {c["name"] for c in json.loads(t)["checkings"]}
        g, d = nombres(f"dist/{env}/config/{f}"), nombres(f"env/{env}/config/{f}")
        for n in sorted(g - d):
            print(f"{env} {f}: +{n} (se añadiría)")
        for n in sorted(d - g):
            print(f"{env} {f}: -{n} (se perdería)")
EOF
```

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
