# Git canonical policy

1. `arendon7/MKTGAPP` is the source of truth.
2. Work happens in named branches; every coherent change is committed before moving to the next block.
3. `main` only receives reviewed/tested source.
4. Generated ZIP/APP/DMG files are CI artifacts, not canonical source.
5. Every delivery must be reproducible from a commit SHA.
6. User data, provider keys, caches, renders and evidence stay out of Git.
7. Recovery claims distinguish `exact`, `documented`, and `reconstructed` states.
8. A missing binary never blocks source continuity again: source + manifests + build scripts remain versioned.
