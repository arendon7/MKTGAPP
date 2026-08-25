# Post-W99 · Development Entrypoint

## Purpose

La rama `dev/post-w99-action-center` conserva dos runtimes deliberadamente distintos:

- `binario-marketing serve` → runtime canónico/release existente; no cambia.
- `binario-marketing serve-dev` → entrypoint estable de la cadena post-W99 de desarrollo.

`serve-dev` resuelve `service_post_w99_dev_app`, que actualmente carga Action Center + Pipeline Priority + Global Navigator + Commercial Outcome Intelligence + Decision Review + Executive Marketing Cockpit. Así el CLI no necesita conocer el nombre de cada incremento post-W99.

Esto permite seguir construyendo producto mientras `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53` y su candidato físico W99 permanecen congelados para la UAT del issue #113.

## Defaults

`serve-dev` usa loopback `127.0.0.1` y puerto `8766` por defecto. Igual que el runtime canónico, rechaza binds no-loopback salvo `--allow-network` explícito.

## Contract

El comando de desarrollo no cambia `service.py`, `version.py`, el tag intent `v0.9.0`, los builders W99 ni el artefacto físico. No debe interpretarse como W100, release candidate ni production-ready.
