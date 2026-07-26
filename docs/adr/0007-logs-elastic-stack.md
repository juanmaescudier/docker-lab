# ADR-0007: Centralización de logs con el Elastic Stack

- **Estado:** Aceptado
- **Fecha:** 2026-07-26

## Contexto

Con M3a tenía métricas: sabía **que** algo iba mal (un pico de errores 5xx, latencia alta), pero no **por qué**. Para diagnosticar hacen falta los logs, y hasta ahora estaban dispersos: un `docker compose logs` por servicio, sin poder buscar ni correlacionar. Quiero centralizarlos en un solo sitio, poder buscarlos por servicio y por resultado, y que el flujo completo esté documentado.

## Decisión

Monto **Elasticsearch + Kibana + Fluent Bit** en un `compose.logging.yaml` aparte, con una red `logging` dedicada. El flujo es:

```
Contenedores (stdout) → Fluent Bit (tail) → Elasticsearch (índice/día) → Kibana
```

Decisiones concretas:

- **Elastic Stack y no Grafana Loki.** Elastic es el nombre más reconocible en logs y me enseña tecnología nueva (índices, búsqueda full-text, mapeos), mientras que Loki reutiliza el modelo de etiquetas de Prometheus que ya domino. Reservo **Loki para mi laboratorio de Linux** y así cubro los dos enfoques: el pesado/estándar y el ligero/cloud-native.
- **Recolección con el plugin `tail`** (Fluent Bit lee `/var/lib/docker/containers/*/*-json.log`) y no con el log driver `fluentd` de Docker. Dos razones: está **desacoplado** (si Fluent Bit se cae, los contenedores siguen funcionando y al volver retoma por donde iba, gracias a su BD de posiciones) y es el **mismo patrón que se usa en Kubernetes**, donde Fluent Bit corre como DaemonSet leyendo los ficheros del nodo. Lo aprendido aquí se reutiliza en M4.
- **Un índice por día** (`docker-lab-AAAA.MM.DD`, con `Logstash_Format`): facilita retener y borrar logs viejos, basta con eliminar índices.
- **Logging estructurado en JSON en la app**, en un módulo aislado (`app/logging_config.py`): cada petición genera un log con `service`, `level`, `method`, `path`, `status`, `duration_ms` y un `request_id`. El nivel se deriva del resultado (5xx → ERROR, 4xx → WARNING, resto → INFO).
- **Seguridad de Elasticsearch desactivada** (`xpack.security.enabled=false`) y **single-node**: solo para el laboratorio, para no gestionar certificados. En producción esto no se hace nunca.
- **Heap de la JVM fijado** (`-Xms512m -Xmx512m`): Elasticsearch es lo más pesado del stack y sin fijarlo la JVM se reserva un porcentaje de la RAM del host.

## Alternativas consideradas

- **Grafana Loki:** más ligero y se integraría en el Grafana que ya tengo (métricas y logs en una sola UI). Descartado para este lab por aportar menos aprendizaje nuevo; lo monto en el laboratorio de Linux.
- **OpenSearch** (el fork libre de Elasticsearch, Apache 2.0, respaldado por AWS): casi idéntico y con camino directo a AWS OpenSearch gestionado. Descartado por reconocimiento de marca, pero es la alternativa natural si la licencia SSPL fuera un problema.
- **Log driver `fluentd` de Docker** (modelo push): los logs llegarían ya con el nombre del contenedor y no depende del sistema de ficheros. Descartado porque acopla el arranque de los contenedores al colector y es un patrón propio de Docker que no se traslada a Kubernetes. Queda como plan B documentado.
- **Dejar los logs en texto plano:** descartado. Sin campos no se puede filtrar por código de estado ni agregar por ruta.

## Consecuencias

- Los logs de todos los servicios están centralizados y consultables desde Kibana con filtros como `service: nutriapp and status >= 400` o `duration_ms > 100`.
- El campo `service` es **estable entre reconstrucciones**, a diferencia del ID de contenedor: filtrar por ID obligaba a buscarlo de nuevo tras cada `--build`.
- El `request_id` sienta la base para **correlacionar** logs cuando parta la app en varios servicios, y se devuelve en la cabecera `X-Request-ID` para poder rastrear una petición concreta reportada por un cliente.
- **Limitación de entorno (dev vs prod):** el `tail` de ficheros **solo funciona en Docker sobre Linux nativo**. En Docker Desktop/WSL2 esos ficheros viven dentro de la VM interna de Docker y un bind mount los ve vacíos (comprobado: el mount lista cero ficheros y Fluent Bit no engancha ninguno). Por eso valido los logs en la VM Ubuntu, que replica producción. Es la misma lección que con cAdvisor en M3a.
- **Lección de mapeos en Elasticsearch:** el primer documento que llega define el tipo de cada campo y el resto debe respetarlo. Los logs de Elasticsearch y Kibana usan formato ECS con claves como `log.level`; al indexarlas, ES quiere que `log` sea un objeto, pero ya estaba mapeado como texto por las líneas no-JSON (Postgres, Redis, access log de gunicorn). Resultado: `illegal_state_exception` y documentos **rechazados en silencio**. Lo detecté porque había activado `Trace_Error` en el output, y lo resolví excluyendo con un filtro `grep` los logs del propio stack de Elastic —que además son ruido: no tiene sentido almacenar en Elasticsearch los logs de Elasticsearch.
- **Coste de identificación:** con el plugin `tail` la identidad del origen es el ID de contenedor (va en la etiqueta, persistida con `Include_Tag_Key`), no el nombre del servicio. Se compensa con el campo `service` que emite la propia app. En Kubernetes el filtro `kubernetes` resuelve esto de forma nativa añadiendo pod, namespace y labels.
- **Mejoras futuras:** separar índices por fuente (`app-*`, `infra-*`) con **index templates** en lugar de dejar que ES infiera los mapeos; política de retención (ILM) para no crecer sin límite; unificar el access log de gunicorn en JSON; y adoptar el esquema **ECS** para hablar el mismo idioma que el resto del ecosistema.
