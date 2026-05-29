# Guia completa de despliegue en Seenode para erpapi

## 1. Objetivo

Esta guia documenta el despliegue de este proyecto FastAPI en Seenode desde GitHub, incluyendo el escenario en el que la base de datos se consume a traves de un tunel.

## 2. Alcance del proyecto

- Backend: FastAPI
- ASGI server: Uvicorn
- ORM: SQLAlchemy
- Driver MySQL: PyMySQL
- Configuracion por variables de entorno en `config.py`
- Dependencias en `requirements.txt`

## 3. Prerrequisitos

1. Repositorio en GitHub con rama de despliegue (por ejemplo, `main`).
2. Cuenta en Seenode con permisos para crear Web Service.
3. Variables de entorno disponibles para Seenode.
4. Acceso a la base de datos de destino (directo o por tunel estable).
5. Validacion local de dependencias completada.

## 4. Validaciones previas recomendadas (local)

Ejecutar en PowerShell desde la raiz del proyecto:

```powershell
& "c:\wamp\www\erpapi\venv\Scripts\python.exe" -m pip install -r requirements.txt
& "c:\wamp\www\erpapi\venv\Scripts\python.exe" -m pip check
```

Resultado esperado de `pip check`:

- `No broken requirements found.`

Notas:

- `pip check` no modifica paquetes ni codigo.
- Si aparecen conflictos, corregir primero versiones en `requirements.txt` y volver a validar.

## 5. Requisitos minimos de estructura para Seenode

Seenode (FastAPI) espera:

1. Archivo `main.py` con instancia `app = FastAPI(...)`.
2. Archivo `requirements.txt` en la raiz.
3. Comandos de build/start configurados.
4. Puerto configurado en dashboard y consistente con Uvicorn.

## 6. Despliegue paso a paso en Seenode

## 6.1 Crear el servicio

1. Entrar al dashboard de Seenode.
2. Crear un `Web Service`.
3. Conectar repositorio GitHub.
4. Seleccionar rama de despliegue.

## 6.2 Configurar Build y Start

Usar esta configuracion base:

- Build Command:

```text
pip install -r requirements.txt
```

- Start Command:

```text
uvicorn main:app --host 0.0.0.0 --port 8000
```

- Port (campo de Seenode):

```text
8000
```

Importante:

- Seenode indica que no debes depender de variable `PORT` automatica.
- El puerto del dashboard debe coincidir exactamente con el puerto del start command.

## 6.3 Variables de entorno en Seenode

Cargar al menos estas variables (segun `config.py`):

```env
APP_ENV=production
SECRET_KEY=<clave_larga_de_32+_caracteres>

TEST_DB_HOST=<valor>
TEST_DB_USER=<valor>
TEST_DB_PASS=<valor>
TEST_DB_NAME=<valor>
TEST_DB_PORT=<valor>

PROD_DB_HOST=<valor>
PROD_DB_USER=<valor>
PROD_DB_PASS=<valor>
PROD_DB_NAME=<valor>
PROD_DB_PORT=<valor>
```

Recomendacion:

- Si `APP_ENV=production`, validar que los `PROD_DB_*` apunten al destino real.
- Evitar dejar secretos en el repositorio.

## 7. Conexion a BD por tunel: que debes considerar

Este punto es critico para que el despliegue funcione en Seenode.

## 7.1 Regla principal

La app en Seenode debe poder alcanzar `PROD_DB_HOST:PROD_DB_PORT` desde la red donde corre el contenedor.

Si hoy tu tunel solo existe en tu PC local (por ejemplo, `127.0.0.1:3306` en tu maquina), ese endpoint no sera accesible desde Seenode.

## 7.2 Escenarios validos

1. Tunel permanente en una maquina/servicio accesible por Seenode.
2. Endpoint privado/red interna con conectividad real desde el servicio Seenode.
3. Migrar a MySQL administrado en Seenode y eliminar la dependencia del tunel externo.

## 7.3 Escenarios no validos (comunes)

1. Tunel levantado manualmente en laptop del desarrollador.
2. Host de BD configurado como `localhost` esperando que Seenode vea tu equipo local.

## 7.4 Recomendacion operativa

Para produccion, prioriza una de estas dos rutas:

1. Ruta A (recomendada): BD administrada en Seenode para reducir complejidad de red.
2. Ruta B: mantener BD externa, pero con tunel gestionado y monitoreado 24/7 fuera de la laptop.

Checklist de estabilidad del tunel:

- Reconexion automatica.
- Alertas por caida.
- Credenciales rotadas.
- Regla de firewall minima (solo origenes necesarios).
- Prueba de conectividad antes de cada deploy.

## 7.5 Implementacion concreta: tunel TCP con LocalToNet

Como en tu caso el tunel es TCP de LocalToNet, la configuracion en Seenode debe apuntar al endpoint publico TCP que entrega LocalToNet.

Arquitectura esperada:

1. Agente/cliente de LocalToNet conectado de forma persistente cerca de la base de datos.
2. LocalToNet publica un endpoint TCP remoto (host y puerto publicos).
3. Seenode se conecta a ese host/puerto mediante `PROD_DB_HOST` y `PROD_DB_PORT`.

Configuracion tipo en variables de entorno de Seenode:

```env
APP_ENV=production
PROD_DB_HOST=<host_tcp_publico_de_localtonet>
PROD_DB_PORT=<puerto_tcp_publico_de_localtonet>
PROD_DB_USER=<usuario_mysql>
PROD_DB_PASS=<password_mysql>
PROD_DB_NAME=<base_mysql>
```

Puntos clave para que funcione bien:

1. No usar `localhost` en `PROD_DB_HOST` para produccion en Seenode.
2. El endpoint TCP de LocalToNet debe ser estable (idealmente reservado/fijo).
3. El agente de LocalToNet debe estar 24/7 (servicio del sistema), no manual.
4. Validar que firewall/NAT permita el trafico requerido por LocalToNet y MySQL.

Riesgos operativos especificos de LocalToNet TCP:

1. Caida del agente local = caida de conectividad de la app hacia la BD.
2. Cambio de host/puerto del tunel = fallo inmediato de conexion en Seenode.
3. Latencia adicional del salto por tunel en consultas pesadas.

Medidas recomendadas:

1. Ejecutar el agente en un servidor siempre activo, no en laptop personal.
2. Implementar monitoreo de conectividad a `PROD_DB_HOST:PROD_DB_PORT`.
3. Documentar runbook de recuperacion del tunel (reinicio, rotacion de credenciales, fallback).
4. Mantener opcion de migracion a MySQL administrado en Seenode para reducir dependencia externa.

## 8. Verificacion post deploy (smoke test)

Una vez en estado `Live`:

1. Abrir URL publica y verificar carga inicial.
2. Probar endpoint de salud del backend.
3. Probar login real.
4. Validar lectura de datos desde BD.
5. Revisar logs de runtime en Seenode.

Prueba rapida sugerida:

1. `GET /api`
2. `POST /api/auth/login`
3. `GET /api/operacion/activa` con JWT
4. `GET /api/inventario/pendientes` con JWT

## 9. Troubleshooting rapido

## 9.1 Build falla

- Verificar `requirements.txt`.
- Revisar logs de build.
- Confirmar version de Python compatible en entorno.

## 9.2 502 Bad Gateway

Causa frecuente:

- Puerto no coincide entre dashboard y start command.

Accion:

- Alinear `Port=8000` y `--port 8000`.

## 9.3 Error de BD al arrancar

Posibles causas:

- Variables `PROD_DB_*` incorrectas.
- Tunel caido o inaccesible.
- Firewall bloqueando salida/entrada.

Accion:

- Verificar host/puerto efectivos del tunel.
- Probar conectividad desde un entorno equivalente al de despliegue.
- Si usas LocalToNet TCP, validar que el agente este activo y que el endpoint publico no haya cambiado.

## 9.4 Arranca pero falla en endpoints protegidos

- Validar `SECRET_KEY` y formato del token.
- Revisar reloj/zonas horarias si hay expiracion inesperada.

## 10. Procedimiento minimo de release recomendado

1. Validar dependencias (`pip install -r requirements.txt`, `pip check`).
2. Confirmar variables de entorno en Seenode.
3. Confirmar conectividad de BD (tunel/host final).
4. Push a rama de despliegue.
5. Revisar build y runtime logs.
6. Ejecutar smoke test funcional.
7. Marcar despliegue como aprobado.

## 11. Decision tecnica recomendada para este proyecto

Si el objetivo es estabilidad de produccion con minimo riesgo operativo:

1. Mantener `requirements.txt` pineado (como esta actualmente).
2. Mantener `pip check` como validacion previa en cada release.
3. Evitar depender de tuneles manuales en equipos personales.
4. Estandarizar el puerto Seenode en `8000` y Uvicorn en `--port 8000`.
5. Documentar el runbook de respuesta ante caida del tunel.

## 12. Referencias utiles de Seenode

- FastAPI deployment guide.
- Build and start commands.
- Port configuration.
- Web services.
- Managed MySQL databases.
