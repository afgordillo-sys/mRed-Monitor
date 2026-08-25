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


def render(text: str, values: dict[str, str]) -> tuple[str, int, set[str], dict[str, int]]:
    """Sustituye los placeholders conocidos.

    Una clave desconocida se deja INTACTA, nunca se sustituye por cadena
    vacia. Eso es lo que protege a Scriban en los .html.

    Devuelve (texto, sustituciones, claves usadas, {clave desconocida: linea}).
    """
    count = 0
    used: set[str] = set()
    unknown: dict[str, int] = {}

    def substitute(match: re.Match[str]) -> str:
        nonlocal count
        name = match.group(1)
        if name not in values:
            unknown.setdefault(name, line_of(text, match.start()))
            return match.group(0)
        used.add(name)
        count += 1
        return values[name]

    return PLACEHOLDER.sub(substitute, text), count, used, unknown


def parses_as_xml(text: str) -> bool:
    try:
        ET.fromstring(text)
    except ET.ParseError:
        return False
    return True


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
    pending: list[tuple[Path, str]] = []

    for source in sources:
        original = read_source(source)
        rendered, subs, keys, unknown = render(original, values)
        used |= keys
        total_subs += subs

        for name, line in sorted(unknown.items()):
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

        errors.extend(validate_output(source, original, rendered))
        pending.append((destination_for(source, env), rendered))

    unused = sorted(set(values) - used)
    if unused:
        warnings.append(f"claves definidas y no usadas: {', '.join(unused)}")

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
