# Wave 46 · Release Candidate Readiness

Wave 46 cambia el criterio de avance: una app que compila, pasa tests y genera FULL MAC **no es automáticamente una release de producción**.

## Estados

### DEVELOPMENT
El source todavía contiene uno o más bloqueadores de release, por ejemplo:
- versión `dev/alpha/beta/rc`;
- `RELEASE_READY = False`;
- `RELEASE_TAG` ausente.

### RELEASE_CANDIDATE_BLOCKED
El source puede estar preparado para release, pero falta uno o más gates externos:
- firma `Developer ID Application`;
- notarización Apple;
- UAT física PASS ligada al mismo `git_sha` y arquitectura.

### PRODUCTION_READY
Solo existe si simultáneamente:
1. versión canónica estable;
2. `RELEASE_READY = True`;
3. `RELEASE_TAG` canónico;
4. bundle firmado con Developer ID;
5. bundle notarizado;
6. UAT física PASS del mismo SHA/arquitectura.

## Evidencia embebida

Cada FULL MAC incluye:
- `Contents/Resources/BUILD_PROVENANCE.json`;
- `Contents/Resources/RELEASE_READINESS.json`;
- `Contents/Resources/release-tools/release_candidate_gate.py`;
- `Contents/Resources/release-tools/collect_release_uat.py`;
- `Contents/Resources/release-tools/record_release_uat.py`.

El build CI actual sigue usando firma ad-hoc. Por tanto debe declarar explícitamente `production_ready=false` y permanecer fail-closed.

## UAT física

`collect_release_uat.py` genera una sesión ligada al SHA y arquitectura del `.app`. Los checks automáticos no bastan: cada gate manual permanece `PENDING`.

`record_release_uat.py` registra cada gate como `PASS` o `FAIL` con una nota concreta. Solo cuando los checks automáticos están PASS y **todos** los gates manuales están PASS se produce:

```json
{"overall":"UAT_PASS","uat_passed":true}
```

El gate de release rechaza evidencia cuyo `git_sha` o arquitectura no corresponda al candidato.

## Gate final

Evaluación informativa/fail-closed:

```bash
python scripts/release_candidate_gate.py --repo . --app "/ruta/Binario Marketing IA.app" --expect-blocked
```

Gate de producción:

```bash
python scripts/release_candidate_gate.py --repo . --app "/ruta/Binario Marketing IA.app" --uat-evidence /ruta/release-uat-evidence.json --production
```

El segundo comando solo devuelve éxito cuando no queda ningún blocker.

## Lo que Wave 46 NO hace

- no cambia `0.9.0.dev1` a estable;
- no cambia `RELEASE_READY` a `True`;
- no crea tags;
- no simula Developer ID;
- no simula notarización;
- no marca UAT como PASS automáticamente.

Esos cambios pertenecen al cierre de release y deben quedar respaldados por evidencia real del mismo candidato.
