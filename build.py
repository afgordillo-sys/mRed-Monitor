#!/usr/bin/env python3
"""Compilador de entornos para Mred_Monitor.

Toma los .xml / .json / .html de la raiz del repositorio, sustituye los
placeholders {{CLAVE}} por el valor del entorno correspondiente y escribe
el resultado en dist/<entorno>/, replicando la disposicion del servidor.

Las carpetas config/ y env/ son de solo lectura: este script nunca escribe
en ellas. Solo lee el nivel superior de la raiz y escribe en dist/.

Uso:
    python build.py                 compila todos los entornos detectados
    python build.py -e prod         solo prod
    python build.py -e int prod     varios entornos
    python build.py --list          lista los entornos detectados
    python build.py --check         valida sin escribir nada
    python build.py --clean         borra dist/ antes de compilar
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"

# Extensiones que se procesan y se copian a dist/.
EXTENSIONS = {".xml", ".json", ".html"}

# Los monitor_*.json viven bajo config/ en el servidor.
CONFIG_PREFIX = "monitor_"

# Placeholder de compilacion: solo MAYUSCULAS, digitos y _ , sin espacios.
# Deliberadamente estricto para no colisionar con Scriban, que siempre lleva
# espacios, minusculas o puntos: {{ if data }}, {{elm.MAP_TITLE}}.
PLACEHOLDER = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")

# Placeholder que ocupa un valor JSON completo, entre comillas y en posicion de
# valor de objeto: "enable": "{{FLAG}}". Si el valor resuelto parsea como JSON, se
# emite SIN las comillas, para que el fichero generado lleve el tipo correcto y no
# una cadena. Vale cualquier JSON: booleano, null, numero, objeto o array.
#
# Dos guardas deliberadas:
#   1. Exige un ':' delante, asi que una clave JSON que fuera un placeholder
#      ("{{X}}": 1) nunca pierde las comillas y no puede generar JSON invalido.
#   2. Exige que el placeholder ocupe el valor entero, asi que
#      "http://{{HEALTHZ_HOST}}:6060/healthz" sigue siendo sustitucion de cadena.
RAW_IN_JSON = re.compile(r':(\s*)"\{\{([A-Z][A-Z0-9_]*)\}\}"')

# Placeholder entre comillas, en cualquier posicion. Se usa para clasificar por el
# caracter no blanco de alrededor y decidir el tratamiento: valor de objeto,
# elemento de array, clave de objeto o texto dentro de una cadena mayor.
QUOTED_PLACEHOLDER = re.compile(r'"\{\{([A-Z][A-Z0-9_]*)\}\}"')

# Placeholder sin comillas en un .json: rompe el JSON fuente. Se detecta para dar
# un error accionable en lugar de un fallo del parser.
UNQUOTED_IN_JSON = re.compile(r':(\s*)(\{\{[A-Z][A-Z0-9_]*\}\})')

# Literales de Python que no son JSON valido. Escribirlos en el .env deja el valor
# como cadena en silencio, asi que se avisa.
PYTHON_LITERALS = {"True", "False", "None"}

# Limite de pasadas al resolver {{...}} anidado dentro de los valores del .env.
MAX_DEPTH = 10


class BuildError(Exception):
    """Error que impide generar un entorno."""


# --------------------------------------------------------------------------
# Carga de entornos
# --------------------------------------------------------------------------

def parse_env_file(path: Path) -> dict[str, str]:
    """Lee un fichero CLAVE=valor. Ignora blancos y comentarios (#)."""
    values: dict[str, str] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise BuildError(f"{path.name}:{number}: se esperaba CLAVE=valor -> {raw!r}")
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            raise BuildError(f"{path.name}:{number}: clave vacia")
        values[key] = value.strip()
    return values


def discover_environments() -> list[str]:
    """Devuelve los entornos detectados a partir de los ficheros .env.<nombre>."""
    names = {p.suffix.lstrip(".") for p in ROOT.glob(".env.*") if p.is_file()}
    return sorted(n for n in names if n)


def resolve_values(values: dict[str, str]) -> tuple[dict[str, str], set[str]]:
    """Expande los {{...}} anidados dentro de los propios valores del .env.

    Devuelve (valores resueltos, claves referenciadas por otras claves). Lo
    segundo evita avisar de "clave no usada" para las que solo se consumen
    dentro de otro valor, como VHOST dentro de MONITOR_PATH.
    """
    resolved = dict(values)
    referenced: set[str] = set()
    for _ in range(MAX_DEPTH):
        pending = False
        for key, value in resolved.items():
            def substitute(match: re.Match[str], key: str = key) -> str:
                name = match.group(1)
                if name == key:
                    raise BuildError(
                        f"referencia circular en el .env: la clave {key} acaba "
                        f"dependiendo de si misma"
                    )
                if name not in resolved:
                    raise BuildError(
                        f"la clave {key} referencia {{{{{name}}}}}, que no esta definida"
                    )
                referenced.add(name)
                return resolved[name]

            expanded = PLACEHOLDER.sub(substitute, value)
            if expanded != value:
                resolved[key] = expanded
                pending = True
        if not pending:
            return resolved, referenced
    raise BuildError(
        f"referencias circulares entre claves del .env "
        f"(mas de {MAX_DEPTH} pasadas sin estabilizar)"
    )


def load_environment(env: str) -> tuple[dict[str, str], set[str]]:
    """Combina .env (comun) con .env.<entorno> (que sobrescribe) y resuelve."""
    values: dict[str, str] = {}
    common = ROOT / ".env"
    if common.is_file():
        values.update(parse_env_file(common))
    specific = ROOT / f".env.{env}"
    if not specific.is_file():
        raise BuildError(f"no existe {specific.name}")
    values.update(parse_env_file(specific))
    return resolve_values(values)


# --------------------------------------------------------------------------
# Fuentes
# --------------------------------------------------------------------------

def discover_sources() -> list[Path]:
    """Ficheros fuente del NIVEL SUPERIOR de la raiz, nunca recursivo.

    Al no recorrer subdirectorios, config/, env/, dist/, .git/ y .claude/
    quedan excluidos por construccion, lo que garantiza que no se toque
    ninguna carpeta protegida.
    """
    return [
        p for p in sorted(ROOT.iterdir())
        if p.is_file()
        and p.suffix.lower() in EXTENSIONS
        and not p.name.startswith(".")
    ]


def destination_for(source: Path, env: str) -> Path:
    """Reparte el fichero en dist/<entorno>/ o dist/<entorno>/config/."""
    if source.suffix.lower() == ".json" and source.name.startswith(CONFIG_PREFIX):
        return DIST / env / "config" / source.name
    return DIST / env / source.name


def read_source(path: Path) -> str:
    """Lee preservando los finales de linea tal cual (newline='')."""
    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def write_output(path: Path, text: str) -> None:
    """Escribe sin traducir finales de linea y sin BOM."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)


# --------------------------------------------------------------------------
# Sustitucion y validacion
# --------------------------------------------------------------------------

def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def json_value(value: str) -> tuple[bool, object]:
    """Intenta interpretar el valor del .env como JSON. Devuelve (parsea, resultado).

    Es el filtro que decide si un placeholder que ocupa un valor entero se emite
    SIN comillas. Una sola regla para las dos posiciones (valor de objeto y
    elemento de array): si parsea como JSON se inyecta, si no se queda como cadena.

    Notese lo que NO parsea, y es justo lo que se quiere:
        localhost, mredint, 1KEGG99N   -> cadena
        192.168.1.14                   -> cadena, no es un numero valido
        01, 007                        -> cadena, JSON prohibe ceros a la izquierda
        True, False, None              -> cadena, mayuscula de Python (se avisa)
    """
    try:
        return True, json.loads(value)
    except (json.JSONDecodeError, ValueError):
        return False, None


def antes_de(text: str, pos: int) -> str:
    """Ultimo caracter no blanco antes de pos, o '' si no hay."""
    i = pos - 1
    while i >= 0 and text[i].isspace():
        i -= 1
    return text[i] if i >= 0 else ""


def despues_de(text: str, pos: int) -> str:
    """Primer caracter no blanco desde pos, o '' si no hay."""
    i = pos
    while i < len(text) and text[i].isspace():
        i += 1
    return text[i] if i < len(text) else ""


def es_elemento_de_array(text: str, inicio: int, fin: int) -> bool:
    """True si el placeholder entre comillas ocupa un elemento de array entero.

    Antes tiene que haber '[' o ',' (abre el array o separa del elemento previo) y
    despues ',' o ']'. Un ':' en cualquiera de los dos lados descarta: seria un
    valor de objeto (lo trata la pasada de escalares) o una clave de objeto (que
    no se toca nunca).
    """
    return antes_de(text, inicio) in "[," and despues_de(text, fin) in ",]"


class Rendered:
    """Resultado de sustituir un fichero."""

    def __init__(self) -> None:
        self.text = ""
        self.subs = 0
        self.used: set[str] = set()
        self.unknown: dict[str, int] = {}
        # Inyecciones sin comillas aplicadas: (clave, valor, linea).
        self.raw: list[tuple[str, str, int]] = []
        # Elementos de array inyectados y omitidos: (clave, linea).
        self.elementos_inyectados: list[tuple[str, int]] = []
        self.elementos_omitidos: list[tuple[str, int]] = []
        # Claves con literal de Python en posicion sin comillas: (clave, valor, linea).
        self.python_literals: list[tuple[str, str, int]] = []
        # Errores propios de la sustitucion, ya con fichero:linea resuelto aparte.
        self.errors: list[tuple[str, int]] = []


def render(text: str, values: dict[str, str], is_json: bool) -> Rendered:
    """Sustituye los placeholders conocidos.

    En los .json se hace primero una pasada de inyeccion sin comillas, para que
    un valor booleano o numerico salga con su tipo real y no como cadena. El
    resto se sustituye como texto.

    Una clave desconocida se deja INTACTA, nunca se sustituye por cadena vacia.
    Eso es lo que protege a Scriban en los .html.
    """
    result = Rendered()

    if is_json:
        def inject(match: re.Match[str]) -> str:
            spacing, name = match.group(1), match.group(2)
            if name not in values:
                return match.group(0)  # la pasada normal lo reporta como desconocida
            value = values[name]
            line = line_of(text, match.start())
            if value in PYTHON_LITERALS:
                result.python_literals.append((name, value, line))
                return match.group(0)
            if not json_value(value)[0]:
                return match.group(0)  # sigue siendo cadena, la pasada normal lo hace
            result.used.add(name)
            result.subs += 1
            result.raw.append((name, value, line))
            return f":{spacing}{value}"

        text = RAW_IN_JSON.sub(inject, text)
        text = render_array_elements(text, values, result)

    def substitute(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in values:
            result.unknown.setdefault(name, line_of(text, match.start()))
            return match.group(0)
        result.used.add(name)
        result.subs += 1
        return values[name]

    result.text = PLACEHOLDER.sub(substitute, text)
    return result


def render_array_elements(text: str, values: dict[str, str], result: Rendered) -> str:
    """Inyecta u omite placeholders que ocupan un elemento de array entero.

    Un valor vacio OMITE el elemento, consumiendo una coma adyacente para que el
    array siga siendo valido. Un valor que parsea como JSON se inyecta verbatim.
    Cualquier otra cosa es un error: en posicion de elemento de array se puede ser
    estricto, porque un array de cadenas no es algo que aparezca en estos ficheros.

    Se recorre de derecha a izquierda para que las posiciones ya calculadas no se
    desplacen al ir modificando el texto.
    """
    for match in reversed(list(QUOTED_PLACEHOLDER.finditer(text))):
        name = match.group(1)
        inicio, fin = match.start(), match.end()
        if not es_elemento_de_array(text, inicio, fin):
            continue
        if name not in values:
            continue  # la pasada normal lo reporta como clave desconocida

        line = line_of(text, inicio)
        value = values[name]

        if value == "":
            # Omision: se come UNA coma adyacente. Si la hay detras se lleva la coma
            # y los blancos siguientes, con lo que la linea desaparece limpia y el
            # elemento siguiente conserva el sangrado que tenia el placeholder.
            fin_recorte = fin
            while fin_recorte < len(text) and text[fin_recorte].isspace():
                fin_recorte += 1
            if fin_recorte < len(text) and text[fin_recorte] == ",":
                fin_recorte += 1
                while fin_recorte < len(text) and text[fin_recorte] in " \t\r\n":
                    fin_recorte += 1
                inicio_recorte = inicio
            else:
                # Es el ultimo elemento: hay que quitar la coma de delante.
                inicio_recorte = inicio
                j = inicio - 1
                while j >= 0 and text[j].isspace():
                    j -= 1
                if j >= 0 and text[j] == ",":
                    inicio_recorte = j
                fin_recorte = fin
            text = text[:inicio_recorte] + text[fin_recorte:]
            result.used.add(name)
            result.subs += 1
            result.elementos_omitidos.append((name, line))
            continue

        parsea, _ = json_value(value)
        if not parsea:
            result.errors.append((
                f"el valor de {name} ocupa un elemento de array, asi que debe ser "
                f"JSON valido (un objeto entre llaves) o estar vacio para omitir el "
                f"elemento. Valor actual: {value[:60]}",
                line,
            ))
            continue

        text = text[:inicio] + value + text[fin:]
        result.used.add(name)
        result.subs += 1
        result.elementos_inyectados.append((name, line))

    return text


def parses_as_xml(text: str) -> bool:
    try:
        ET.fromstring(text)
    except ET.ParseError:
        return False
    return True


def validate_json_source(source: Path, original: str) -> list[str]:
    """Comprueba que un .json fuente sigue siendo JSON valido.

    Se hace independientemente del entorno: mide la sintaxis del fichero, no los
    valores. Para eso los placeholders se neutralizan por una cadena antes de
    parsear.
    """
    errors: list[str] = []

    # Un placeholder sin comillas rompe el JSON. Se detecta aparte para poder dar
    # el arreglo concreto en lugar de un error del parser.
    for match in UNQUOTED_IN_JSON.finditer(original):
        token = match.group(2)
        errors.append(
            f"{source.name}:{line_of(original, match.start())}: {token} sin comillas "
            f"rompe el JSON fuente. Escribelo como \"{token}\": build.py quitara las "
            f"comillas al generar si el valor es booleano, null o numero"
        )
    if errors:
        return errors

    neutral = PLACEHOLDER.sub("X", original)
    try:
        json.loads(neutral)
    except json.JSONDecodeError as exc:
        errors.append(f"{source.name}: el JSON fuente no parsea ({exc})")
    return errors


def validate_output(source: Path, original: str, rendered: str) -> list[str]:
    """Comprueba que la sustitucion no ha roto el fichero."""
    errors: list[str] = []
    suffix = source.suffix.lower()

    if suffix == ".json":
        try:
            json.loads(rendered)
        except json.JSONDecodeError as exc:
            errors.append(f"{source.name}: el JSON generado no parsea ({exc})")

    elif suffix == ".xml":
        # Solo se exige si la fuente ya era XML bien formado. Asi una plantilla
        # que hoy no lo es no bloquea el build, pero se detecta si la
        # sustitucion la rompe.
        if parses_as_xml(original) and not parses_as_xml(rendered):
            errors.append(
                f"{source.name}: el XML generado no parsea (la fuente si parseaba)"
            )

    return errors


# --------------------------------------------------------------------------
# Compilacion
# --------------------------------------------------------------------------

def build_environment(env: str, sources: list[Path], check: bool) -> bool:
    """Compila un entorno. Devuelve True si termino sin errores."""
    label = f"[{env}]"
    try:
        values, referenced = load_environment(env)
    except BuildError as exc:
        print(f"{label} ERROR: {exc}")
        return False

    errors: list[str] = []
    warnings: list[str] = []
    # Las claves consumidas dentro de otro valor del .env ya cuentan como usadas.
    used: set[str] = set(referenced)
    total_subs = 0
    raw_injections: list[str] = []
    elementos: list[str] = []
    pending: list[tuple[Path, str]] = []

    for source in sources:
        original = read_source(source)
        is_json = source.suffix.lower() == ".json"
        source_errors = validate_json_source(source, original) if is_json else []
        errors.extend(source_errors)

        out = render(original, values, is_json)
        used |= out.used
        total_subs += out.subs

        for name, line in sorted(out.unknown.items()):
            if source.suffix.lower() == ".html":
                # En los .html puede ser Scriban legitimo: se avisa, no falla.
                warnings.append(
                    f"{source.name}:{line}: {{{{{name}}}}} sin definir, "
                    f"se deja intacto (posible Scriban)"
                )
            else:
                errors.append(
                    f"{source.name}:{line}: {{{{{name}}}}} no esta definida en {env}"
                )

        # Cada inyeccion sin comillas se declara: es el efecto menos evidente del
        # compilador y conviene que nunca pase desapercibido.
        for name, value, line in out.raw:
            raw_injections.append(f"{name}={value} en {source.name}:{line}")

        for name, line in out.elementos_inyectados:
            elementos.append(f"inyectado: {name} en {source.name}:{line}")
        # La omision borra configuracion. Si el valor se quedo vacio por olvido, esta
        # linea es lo unico que lo delata, asi que siempre se imprime.
        for name, line in out.elementos_omitidos:
            elementos.append(f"omitido:   {name} en {source.name}:{line}")

        for mensaje, line in out.errors:
            errors.append(f"{source.name}:{line}: {mensaje}")

        for name, value, line in out.python_literals:
            warnings.append(
                f"{source.name}:{line}: {name}={value} usa mayuscula de Python; "
                f"en JSON se escribe en minuscula ({value.lower()}). "
                f"Se deja como cadena"
            )

        # Si la fuente ya estaba mal, validar la salida solo repite la misma causa.
        if not source_errors:
            errors.extend(validate_output(source, original, out.text))
        pending.append((destination_for(source, env), out.text))

    unused = sorted(set(values) - used)
    if unused:
        warnings.append(f"claves definidas y no usadas: {', '.join(unused)}")

    for injection in raw_injections:
        print(f"{label} sin comillas: {injection}")
    for elemento in elementos:
        print(f"{label} elemento {elemento}")
    for warning in warnings:
        print(f"{label} aviso: {warning}")
    for error in errors:
        print(f"{label} ERROR: {error}")

    if errors:
        print(f"{label} FALLIDO: {len(errors)} error(es), no se ha escrito nada")
        return False

    # Solo se escribe si TODOS los ficheros del entorno han validado, para no
    # dejar un dist/ a medias.
    if not check:
        for destination, rendered in pending:
            write_output(destination, rendered)

    action = "validados" if check else f"escritos en dist/{env}/"
    print(f"{label} OK: {len(sources)} fichero(s) {action}, {total_subs} sustitucion(es)")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compila los ficheros de configuracion y plantillas por entorno.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-e", "--env", nargs="+", metavar="ENTORNO",
        help="entornos a compilar (por defecto: todos los detectados)",
    )
    parser.add_argument(
        "--list", action="store_true", help="lista los entornos detectados y sale"
    )
    parser.add_argument("--check", action="store_true", help="valida sin escribir nada")
    parser.add_argument("--clean", action="store_true", help="borra dist/ antes de compilar")
    args = parser.parse_args(argv)

    available = discover_environments()
    if not available:
        print("ERROR: no se ha encontrado ningun fichero .env.<entorno> en la raiz")
        return 1

    if args.list:
        print("Entornos detectados:")
        for env in available:
            print(f"  {env}  (.env.{env})")
        return 0

    targets = args.env or available
    desconocidos = [env for env in targets if env not in available]
    if desconocidos:
        print(f"ERROR: entorno(s) desconocido(s): {', '.join(desconocidos)}")
        print(f"       disponibles: {', '.join(available)}")
        return 1

    sources = discover_sources()
    if not sources:
        print("ERROR: no hay ficheros fuente (.xml / .json / .html) en la raiz")
        return 1

    if args.clean and not args.check:
        if DIST.exists():
            shutil.rmtree(DIST)
            print("dist/ borrado")

    mode = "Validando" if args.check else "Compilando"
    print(f"{mode} {len(sources)} fichero(s) para: {', '.join(targets)}")

    ok = True
    for env in targets:
        if not build_environment(env, sources, args.check):
            ok = False

    print("Terminado sin errores." if ok else "Terminado CON ERRORES.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
