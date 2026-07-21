# ADR-0003: Autenticación por sesión con Flask-Session sobre Redis

- **Estado:** Aceptado
- **Fecha:** 2026-07-21

## Contexto

El dominio Usuarios necesita registro, login y una forma de saber quién hace cada petición. La aplicación tendrá un frontend en el navegador más adelante, y en producción irá detrás de un reverse proxy (nginx) con TLS. Hay que elegir el mecanismo de autenticación y si implementarlo a mano o con una librería.

## Decisión

Autenticación por **sesión de servidor** con **Flask-Session respaldada por Redis**:

- El identificador de sesión viaja en una **cookie `HttpOnly` + `SameSite=Lax`**; los datos de la sesión se guardan en Redis, no en el navegador.
- Las contraseñas se guardan **hasheadas con sal** (werkzeug), nunca en claro.
- Se usa una **librería mantenida** en lugar de gestión de sesiones casera, porque la autenticación es justo donde no conviene reinventar la rueda.

## Alternativas consideradas

- **Token opaco o JWT en cabecera `Authorization`**: peor encaje con un frontend de navegador (el token acabaría en `localStorage`, expuesto a XSS), y los JWT no se revocan fácilmente. Se reserva por si en el futuro hay clientes móviles o de terceros.
- **Sesión hecha a mano** (token + Redis): más transparente para aprender, pero amplía la superficie de error en código de seguridad (RNG seguro, flags de cookie, session fixation) sin aportar ventaja real en producción.

## Consecuencias

- Detrás de nginx, frontend y API quedan en el **mismo origen** → las cookies funcionan sin complicaciones de CORS.
- En producción hay que poner **`SESSION_COOKIE_SECURE=true`** (la cookie solo por HTTPS); en desarrollo (http) es `false`.
- Queda pendiente añadir **token CSRF** si el frontend lo requiere (el `SameSite` cubre el caso habitual).
- Añadir la columna `password_hash` obligó a recrear la base de datos, porque `db.create_all()` no altera tablas existentes: refuerza la necesidad de **migraciones (Alembic)** más adelante.
