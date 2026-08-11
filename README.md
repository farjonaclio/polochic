# Tablero de monitoreo · Evaluación final Valle del Polochic

Monitoreo del levantamiento de campo del Programa Conjunto Valle del Polochic
(Panzós, Senahú y Tucurú, Alta Verapaz; El Estor, Izabal).
**CliO Consulting**, agosto–septiembre 2026.

**Tablero en vivo:** https://farjonaclio.github.io/polochic/

---

## Cómo funciona

```
KoboToolbox (eu.kobotoolbox.org)
        │   API v2 · token en GitHub Secrets
        ▼
GitHub Actions · cada 30 minutos          ← el token solo existe dentro del runner
        │   agrega: conteos por comunidad, comunidad×día, centroides
        ▼
datos/datos.json                          ← solo agregados, con commit trazable
        │
        ▼
index.html vía GitHub Pages               ← lo abre PNUD sin credencial
```

El **microdato nunca sale de Kobo**. El token da acceso a consentimientos,
identificación del informante y coordenadas GPS de vivienda; por eso vive en
Secrets y no en el HTML, donde sería legible por cualquiera que abra el código
fuente. Lo único que viaja al repositorio son conteos y centroides comunitarios
calculados con mediana sobre un mínimo de 3 registros, redondeados a ~110 m.

Cada actualización queda como un commit: el historial de `datos/datos.json` es la
trazabilidad del avance, día por día.

---

## Estructura

| Ruta | Qué es |
|---|---|
| `index.html` | El tablero completo. Un solo archivo autocontenido; única dependencia externa es Leaflet desde CDN, con degradación explícita si no carga. |
| `scripts/puente_kobo.py` | El puente. Solo biblioteca estándar de Python: no hay dependencias que instalar ni que se rompan por una versión nueva. |
| `.github/workflows/actualizar.yml` | El cron de 30 minutos y el commit condicional. |
| `datos/datos.json` | Salida del puente. Lo genera Actions; no se edita a mano. |

---

## Comportamiento ante fallos

El tablero **arranca siempre con la instantánea embebida** (corte del 7 de agosto) y
pinta antes de tocar la red. Después intenta `datos/datos.json`:

- **Responde** → los conteos en vivo sustituyen a la instantánea, se repinta, y el chip
  de la cabecera dice «● En vivo · Kobo vía puente · HH:MM».
- **No responde, o responde algo que no reconocemos** → sigue mostrando la instantánea y
  el chip lo declara: «◷ Instantánea del 07/08 · puente sin responder».

Un tablero que se queda en blanco cuando falla la fuente es peor que uno que muestra
datos viejos y lo dice.

---

## Convenciones que sostienen la lectura

**Tres vacíos distintos.** `—` es no medido; `·` es sin actividad registrada al corte;
`0` es cero efectivo. Confundirlos es lo que hace que un tablero mienta sin que nadie
lo note.

**El cierre de una comunidad es manual, a propósito.** El avance viene del dato, pero
que una comunidad esté cerrada por debajo de su meta es una decisión operativa —se
agotó el marco, no había más hogares elegibles— y Kobo no puede saberlo. Si el estado
se derivara solo del conteo, El Rodeo (10/12) y Bella Flor (12/14) volverían a «En
curso» y el déficit de 4 unidades desaparecería justo cuando conectamos la fuente
confiable.

**Meta comprometida ≠ acumulado previsto.** El plan sale del calendario por comunidad,
no de una interpolación lineal. Las 6 unidades sin fecha asignada cuentan en la meta
(325) pero no en el previsto (319), y el tablero dice cuál es la diferencia y por qué.

**Sobremuestra y déficit no se netean.** Son marcos muestrales distintos: +7 en unas
comunidades no sustituyen −4 en otras. Se reportan como KPI independientes.

**Accesibilidad del par de series.** El petróleo de marca (#00708A) queda a ΔE 5,3 del
magenta en visión protán y las dos series dejan de distinguirse. Se usa un paso más
luminoso (#0E93B0).

---

## Operación

### Actualizar a mano
Pestaña **Actions → Actualizar datos desde Kobo → Run workflow**.

### Diagnosticar en local
```bash
export KOBO_TOKEN=...
python3 scripts/puente_kobo.py            # corre el puente y escribe el JSON
python3 scripts/puente_kobo.py --listar   # lista los UID de todos los formularios
```

### Probar el tablero contra otro JSON
```
index.html?datos=URL_DEL_JSON
```

---

## Formularios conectados

UID verificados el 11 de agosto de 2026 contra los formularios desplegados.

| Formulario | Enketo | UID |
|---|---|---|
| Encuesta a Beneficiarios | `M4SCCiH0` | `aj3Xeptowp22xpofSdZ9V2` |
| Encuesta para Actores Territoriales | `6TfpL1YN` | `aLeRzdNXVHqAUGnRsASsq6` |
| Encuesta para Actores Institucionales | `ZneLpqsn` | `aQ4AyWUdKA6kqWLzqfxgt7` |
| Encuesta a Funcionarios Públicos | `gO0SgRm8` | `aX8cALDDfwzGHCxctjRLDV` |

Dos particularidades del esquema, ya resueltas en el puente:

- **El formulario de funcionarios públicos no sigue la convención de los otros tres.**
  Invierte municipio y departamento (`a2_municipio` / `a3_departamento` en vez de
  `a5_municipio` / `a4_departamento`) y llama al consentimiento `consentimiento` en vez
  de `acepta_participar`. El puente lista todas las variantes y toma la primera columna
  no vacía.
- **Ninguno tiene una pregunta de encuestador.** Existe el grupo
  `grp_registro_encuestador`, pero solo con metadatos de la entrevista —duración,
  calidad, idioma, interrupciones—, no con el nombre de quien la aplica. El puente cae a
  `_submitted_by`, la cuenta de Kobo que envía, lo que sirve **solo si cada encuestador
  usa su propia cuenta**.

---

## Mantenimiento

**Si el puente reporta comunidades que el plan no reconoce**, el tablero lo levanta como
alerta. Casi siempre es un nombre escrito distinto en campo; se corrige agregando la
variante al diccionario `NORM` en `scripts/puente_kobo.py`.

**Si un formulario se redespliega** y cambia de UID, el puente falla con error 404.
Ejecutar `--listar` y actualizar el bloque `FORMS`.

**Si el token rota o expira**, Actions falla con 401 y GitHub avisa por correo al dueño
del repositorio. Reemplazar el secret `KOBO_TOKEN`.
