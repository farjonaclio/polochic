#!/usr/bin/env python3
"""
==================================================================
PUENTE KOBOTOOLBOX -> datos/datos.json
CliO Consulting · Evaluación final Valle del Polochic
------------------------------------------------------------------
QUÉ HACE
  Consulta la API v2 de KoboToolbox (servidor europeo) con un token
  de servicio, calcula los agregados que el tablero necesita y los
  escribe en datos/datos.json. El microdato NUNCA se escribe:
  del script solo salen conteos y centroides comunitarios.

POR QUÉ ASÍ
  El token de Kobo da acceso al microdato completo: consentimientos,
  identificación del informante y coordenadas GPS de vivienda. Puesto
  en el HTML del tablero quedaría a la vista de cualquiera que abra el
  código fuente. Aquí el token vive en GitHub Secrets: solo existe
  dentro del runner, en tiempo de ejecución, y nunca se escribe al repo.

CÓMO SE EJECUTA
  En GitHub Actions cada 30 minutos (.github/workflows/actualizar.yml).
  En local, para depurar:
      export KOBO_TOKEN=...
      python3 scripts/puente_kobo.py
==================================================================
"""

import json
import os
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone

# ------------------------------------------------------------------
# CONFIGURACIÓN
# ------------------------------------------------------------------

KOBO_HOST = "https://eu.kobotoolbox.org"

# UID verificados el 11-ago-2026 contra los formularios desplegados.
# Si alguno se redespliega con otro UID, ejecutar con --listar.
FORMS = {
    "ben": {
        "uid": "aj3Xeptowp22xpofSdZ9V2",
        "enketo": "M4SCCiH0",
        "nombre": "Encuesta a Beneficiarios",
    },
    "lid": {
        "uid": "aLeRzdNXVHqAUGnRsASsq6",
        "enketo": "6TfpL1YN",
        "nombre": "Encuesta para Actores Territoriales",
    },
    "ins": {
        "uid": "aQ4AyWUdKA6kqWLzqfxgt7",
        "enketo": "ZneLpqsn",
        "nombre": "Encuesta para Actores Institucionales",
    },
    "fun": {
        "uid": "aX8cALDDfwzGHCxctjRLDV",
        "enketo": "gO0SgRm8",
        "nombre": "Encuesta a Funcionarios Públicos",
    },
}

# Rutas reales verificadas en los cuatro formularios desplegados.
# Los tres primeros usan grp_cuestionario/grp_info_general/aN_*; el de
# funcionarios públicos invierte municipio y departamento (a2/a3 en vez
# de a5/a4) y llama al consentimiento "consentimiento" y no
# "acepta_participar". Se listan todas las variantes y se toma la primera
# columna no vacía: así el puente sobrevive a un redespliegue que
# reordene o renombre los grupos.
CAMPOS = {
    "fecha": ["a2_fecha", "today", "fecha", "_submission_time"],
    "consentimiento": ["acepta_participar", "consentimiento", "consent"],
    "comunidad": ["a6_comunidad", "comunidad", "nombre_comunidad"],
    "municipio": ["a5_municipio", "a2_municipio", "municipio"],
    "departamento": ["a4_departamento", "a3_departamento", "departamento"],
    "codigo": ["a1_codigo_encuesta", "codigo_encuesta"],
    "encuestador": ["encuestador", "entrevistador", "_submitted_by"],
}

# NOTA OPERATIVA — identificación del encuestador
# Ninguno de los cuatro formularios tiene una pregunta explícita de
# encuestador. El puente cae a `_submitted_by`, que es la cuenta de Kobo
# que envió el registro: sirve solo si cada encuestador usa su propia
# cuenta. Si comparten cuenta, la desagregación por encuestador que hoy
# se lleva a mano no es reconstruible desde la API.

# Normalización de nombres de comunidad. Sin esto "Qotoxhá" y "Qotoxha"
# se cuentan como dos comunidades distintas y el avance por comunidad
# queda partido en dos sin que nadie lo note. Las claves de la derecha
# deben coincidir EXACTAMENTE con CFG.com[].c del tablero.
NORM = {
    "qotoxha": "Qotoxhá, Río Polochic",
    "qotoxhá": "Qotoxhá, Río Polochic",
    "qotoxha rio polochic": "Qotoxhá, Río Polochic",
    "qotoxha, rio polochic": "Qotoxhá, Río Polochic",
    "qotoxhá, río polochic": "Qotoxhá, Río Polochic",
    "rio polochic": "Qotoxhá, Río Polochic",
    "río polochic": "Qotoxhá, Río Polochic",
    "el rodeo": "El Rodeo",
    "rodeo": "El Rodeo",
    "luchadores san esteban": "Luchadores San Esteban",
    "luchadores": "Luchadores San Esteban",
    "san esteban": "Luchadores San Esteban",
    "el recuerdo": "El Recuerdo",
    "recuerdo": "El Recuerdo",
    "bella flor": "Bella Flor",
    "bellaflor": "Bella Flor",
    "pancus": "Pancús",
    "pancús": "Pancús",
    "guaxpom": "Guaxpom",
    "guaxpon": "Guaxpom",
    "guaxpom, tucuru": "Guaxpom",
    "punto 15": "Punto 15",
    "punto15": "Punto 15",
    "punto quince": "Punto 15",
    "tinajas": "Tinajas",
    "las tinajas": "Tinajas",
    "parana": "Paraná",
    "paraná": "Paraná",
    "agua caliente": "Agua Caliente",
    "aguacaliente": "Agua Caliente",
    "pombaaq": "Pombaaq",
    "pombaq": "Pombaaq",
    "pomba aq": "Pombaaq",
    "la esperanza": "La Esperanza",
    "esperanza": "La Esperanza",
    "san marcos": "San Marcos",
    "qotoxha 2": "Qotoxha 2",
    "qotoxha2": "Qotoxha 2",
    "qotoxhá 2": "Qotoxha 2",
    "qotoxha 1": "Qotoxha 1 — CCUC",
    "qotoxha1": "Qotoxha 1 — CCUC",
    "qotoxha 1 ccuc": "Qotoxha 1 — CCUC",
    "qotoxhá 1 — ccuc": "Qotoxha 1 — CCUC",
    "ccuc": "Qotoxha 1 — CCUC",
    "la isla": "La Isla",
    "isla": "La Isla",
}

SALIDA = os.path.join(os.path.dirname(__file__), "..", "datos", "datos.json")

# Guatemala es UTC-6 todo el año (no aplica horario de verano desde 2007).
GT = timezone(timedelta(hours=-6))


# ------------------------------------------------------------------
# ACCESO A LA API
# ------------------------------------------------------------------

def token():
    t = os.environ.get("KOBO_TOKEN", "").strip()
    if not t:
        sys.exit(
            "ERROR: falta KOBO_TOKEN.\n"
            "  En GitHub: Settings -> Secrets and variables -> Actions -> New secret.\n"
            "  En local:  export KOBO_TOKEN=..."
        )
    return t


def get(url):
    req = urllib.request.Request(url, headers={"Authorization": "Token " + token()})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        cuerpo = e.read().decode("utf-8", "replace")[:300]
        if e.code in (401, 403):
            sys.exit(
                f"ERROR {e.code}: el token no es válido o esa cuenta no tiene "
                f"permiso de lectura sobre el formulario.\n  {url}\n  {cuerpo}"
            )
        if e.code == 404:
            sys.exit(
                f"ERROR 404: el UID no existe. Probablemente el formulario se "
                f"redesplegó.\n  Ejecute: python3 scripts/puente_kobo.py --listar\n  {url}"
            )
        sys.exit(f"ERROR {e.code} en {url}\n  {cuerpo}")


def listar_formularios():
    """Diagnóstico: imprime los UID de todos los formularios visibles."""
    d = get(f"{KOBO_HOST}/api/v2/assets/?format=json&limit=200")
    print(f"{'UID':<24} {'ENVÍOS':>7}  NOMBRE")
    print("-" * 78)
    for a in d.get("results", []):
        if a.get("asset_type") != "survey":
            continue
        print(
            f"{a.get('uid',''):<24} "
            f"{a.get('deployment__submission_count', 0):>7}  {a.get('name','')}"
        )
    print("\nCopie el uid que corresponda a cada formulario al bloque FORMS.")


def datos(uid):
    """Descarga paginada. Con el volumen del proyecto basta una página,
    pero el bucle evita un truncamiento silencioso si crece."""
    out, url, guarda = [], f"{KOBO_HOST}/api/v2/assets/{uid}/data/?format=json&limit=5000", 0
    while url and guarda < 40:
        guarda += 1
        d = get(url)
        out.extend(d.get("results", []))
        url = d.get("next")
    return out


# ------------------------------------------------------------------
# LECTURA TOLERANTE DE CAMPOS
# ------------------------------------------------------------------

def leer(reg, alias):
    """Kobo nombra las columnas con la ruta del grupo ("grupo/pregunta").
    Se busca por sufijo para no depender de la estructura de grupos, que
    cambia entre versiones del formulario. Devuelve la primera no vacía."""
    for k in alias:
        v = reg.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
        for campo, valor in reg.items():
            cl = campo.lower()
            if cl.endswith("/" + k) or cl == k:
                if valor is not None and str(valor).strip():
                    return str(valor).strip()
    return ""


def norm(s):
    if not s:
        return ""
    k = " ".join(s.lower().split())
    return NORM.get(k, s.strip())


def dia(s):
    """La API devuelve "2026-08-06T14:22:31.000-06:00"; nos quedamos con
    el día calendario."""
    if not s:
        return ""
    s = str(s)
    return s[:10] if len(s) >= 10 and s[4] == "-" and s[7] == "-" else ""


def consiente(v):
    """Kobo devuelve etiquetas ("Sí", "No"), valores ("si", "1") o vacío
    según cómo se definió la pregunta. Vacío se trata como consentido:
    el formulario de actores institucionales no tiene la pregunta."""
    if not v:
        return True
    v = v.lower()
    return v.startswith("s") or v.startswith("y") or v == "1"


# ------------------------------------------------------------------
# AGREGACIÓN
# De aquí solo salen conteos. Ningún identificador, ninguna respuesta
# individual, ninguna coordenada de vivienda.
# ------------------------------------------------------------------

def mediana(a):
    a = sorted(a)
    m = len(a) // 2
    return a[m] if len(a) % 2 else (a[m - 1] + a[m]) / 2


def agregar(regs):
    por_com = defaultdict(int)
    por_com_dia = defaultdict(int)
    por_enc = defaultdict(int)
    coords = defaultdict(list)
    total = sin_consent = sin_comunidad = sin_fecha = 0

    for r in regs:
        if not consiente(leer(r, CAMPOS["consentimiento"])):
            sin_consent += 1
            continue

        com = norm(leer(r, CAMPOS["comunidad"]))
        f = dia(leer(r, CAMPOS["fecha"]) or r.get("_submission_time", ""))
        enc = leer(r, CAMPOS["encuestador"])

        if not com:
            sin_comunidad += 1
            com = "(sin comunidad)"
        if not f:
            sin_fecha += 1

        total += 1
        por_com[com] += 1
        if f:
            por_com_dia[f"{com}|{f}"] += 1
        if enc:
            por_enc[enc] += 1

        # Se acumulan coordenadas por comunidad para calcular la MEDIANA
        # más abajo. La coordenada individual no se escribe nunca.
        g = r.get("_geolocation")
        if isinstance(g, list) and len(g) == 2 and g[0] and g[1]:
            try:
                coords[com].append((float(g[0]), float(g[1])))
            except (TypeError, ValueError):
                pass

    # Mediana con umbral de 3 registros y redondeo a 3 decimales (~110 m):
    # por debajo de 3 hogares el centroide identificaría viviendas.
    centroides = {}
    for c, pts in coords.items():
        if len(pts) < 3:
            continue
        centroides[c] = {
            "lat": round(mediana([p[0] for p in pts]), 3),
            "lon": round(mediana([p[1] for p in pts]), 3),
            "n": len(pts),
        }

    return {
        "total": total,
        "sinConsent": sin_consent,
        "sinComunidad": sin_comunidad,
        "sinFecha": sin_fecha,
        "porCom": dict(sorted(por_com.items())),
        "porComDia": dict(sorted(por_com_dia.items())),
        "porEnc": dict(sorted(por_enc.items(), key=lambda x: -x[1])),
        "_centroides": centroides,
    }


# ------------------------------------------------------------------
# PROCESO PRINCIPAL
# ------------------------------------------------------------------

def main():
    if "--listar" in sys.argv:
        listar_formularios()
        return

    ahora = datetime.now(GT)
    salida = {
        "generado": ahora.isoformat(timespec="seconds"),
        "corte": "",
        "instrumentos": {},
        "geo": {},
        "avisos": [],
    }

    corte = ""
    for k, f in FORMS.items():
        regs = datos(f["uid"])
        A = agregar(regs)
        geo = A.pop("_centroides")

        # El corte es el último día con producción de CUALQUIER
        # instrumento. Así un día sin producción de uno se dibuja como
        # cero —que es información— y no como día futuro sin dato.
        for clave in A["porComDia"]:
            d = clave.split("|")[1]
            if d > corte:
                corte = d

        if k == "ben":
            salida["geo"] = geo

        salida["instrumentos"][k] = A
        print(
            f"{k:>4} · {f['nombre'][:44]:<44} "
            f"{A['total']:>4} válidos · {A['sinConsent']:>2} sin consent. · "
            f"{A['sinComunidad']:>2} sin comunidad"
        )

        if A["sinComunidad"]:
            salida["avisos"].append(
                f"{A['sinComunidad']} registro(s) de {f['nombre']} sin comunidad "
                f"reconocible. Revisar el diccionario NORM en scripts/puente_kobo.py."
            )
        if A["sinFecha"]:
            salida["avisos"].append(
                f"{A['sinFecha']} registro(s) de {f['nombre']} sin fecha. "
                f"No entran a la serie diaria."
            )

    salida["corte"] = corte or ahora.strftime("%Y-%m-%d")

    ruta = os.path.abspath(SALIDA)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump(salida, fh, ensure_ascii=False, indent=1, sort_keys=True)

    print(f"\nEscrito {ruta}")
    print(f"Corte: {salida['corte']} · generado {salida['generado']}")
    if salida["avisos"]:
        print("\nAVISOS:")
        for a in salida["avisos"]:
            print("  ▲ " + a)


if __name__ == "__main__":
    main()
