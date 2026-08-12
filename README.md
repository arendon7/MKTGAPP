# BINARIO Marketing App — canonical source

Este repositorio (`arendon7/MKTGAPP`) es desde 2026-08-12 la fuente canónica de desarrollo y recuperación de BINARIO Marketing App / App13.

## Regla principal

El source vive en Git. Los ZIP, `.app`, DMG y bundles son productos reproducibles de CI y **nunca** la única copia de una versión.

## Estado de recuperación

La Wave 21 documentada no llegó a producir un ZIP/source final recuperable. Por eso no se falsifica como release existente. La reconstrucción parte del último estado funcional documentado y de los contratos posteriores preservados:

- Binario IA v0.8.1 FULL STANDALONE PRO MAC R5;
- v0.9.0/R1: 377 tests, 353 módulos Python documentados;
- Editor Video RC5: 34/34 PASS documentados;
- App Factory R1 integrada;
- App13/Wave20: runtime 0.5.5a1, 472/472 engineering PASS y UX 19/19 documentados;
- Wave 21: planeada/certificada documentalmente, pero su artefacto final no llegó a generarse;
- Wave 22: control-plane recuperado en el repositorio legado `arendon7/MKTG-APP`.

La rama `recovery/git-canonicalization` contiene la reconstrucción auditable. Nada se declara equivalente byte-a-byte a la Wave 21 perdida.

## Arquitectura recuperada

- Hub y descubrimiento de apps por `apps/*/manifest.json`;
- Runtime Center;
- Workflow Studio/recipes;
- proyectos y archivos persistentes;
- Editor Video: assets, timeline, split/delete, clipper y planes de audio;
- preparación de datasets para agentes desde documentos/Q&A;
- diagnóstico seguro de providers sin guardar secretos;
- App Factory registry;
- CI y snapshot de source.

## Desarrollo

```bash
python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m binario_marketing.cli apps
```

Los datos de usuario se mantienen fuera del repo, por defecto en `~/Documents/Binario IA/`.
