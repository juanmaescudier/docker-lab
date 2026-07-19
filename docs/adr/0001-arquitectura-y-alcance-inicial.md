# ADR-0001: Arquitectura y alcance inicial del laboratorio

- **Estado:** Aceptado
- **Fecha:** 2026-07-19

## Contexto

Construyo un laboratorio de contenedores de nivel portfolio para consolidar mi perfil Cloud/DevOps Junior. Necesito una aplicación que sirva de hilo conductor y que me haga tocar Docker, CI/CD, observabilidad, orquestación e IaC, sin que el desarrollo de la app me robe el foco.

## Decisión

- La app es un **asistente inteligente de nutrición**, pero construida como **"esqueleto que anda"**: cada servicio existe y hace algo real, con lógica de negocio mínima. La silueta del producto, no el producto completo.
- **Monorepo** con una **carpeta por servicio** en `services/`.
- **Docker Compose** en la raíz (`compose.yaml`) orquesta todo el stack; cada servicio tiene su propio `Dockerfile`.
- El **M0 arranca con un único servicio `api`** (Flask) + Postgres + Redis. La división en más servicios llega en el M2.
- Carpeta `infra/` reservada para observabilidad (M3), Kubernetes (M4) y Terraform (M5).

## Alternativas consideradas

- **Varios mini-labs sueltos** en vez de un proyecto que evoluciona: descartado, un proyecto con narrativa cuenta mejor la historia en entrevista.
- **Arrancar ya multiservicio** en el M0: descartado para no saturar; se sube la dificultad de forma gradual.
- **App genérica de tutorial**: descartada; una idea propia motiva más y da mejor relato.

## Consecuencias

- Gano una narrativa coherente y un alcance controlado por módulos.
- Acepto que la app quede deliberadamente incompleta como producto (frontend, catálogo grande e IA real quedan fuera al inicio).
- Riesgo a vigilar: que el desarrollo de la app crezca y desvíe el foco del objetivo, que es contenedores y orquestación.
