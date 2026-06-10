

Esta guía detalla el diseño técnico e implementación del endpoint para automatizar el proceso de **Consolidación de Ajustes de Inventario** en el backend desarrollado con FastAPI y SQLAlchemy. 

El objetivo principal es reemplazar el registro manual en el panel de administración del POS, permitiendo que la PWA calcule las diferencias (Real vs. Ideal), genere los documentos de ajuste correspondientes (Ingresos/Salidas) y actualice el inventario maestro en una sola transacción atómica y segura.

---

## 1. Arquitectura del Proceso (Flujo de Datos)

El flujo se ejecuta completamente en el backend bajo una única transacción de base de datos (`START TRANSACTION`), garantizando que si cualquier paso falla, se realice un `rollback` automático y no se corrompa el inventario.


```

```text
File generated successfully: guia_tecnica_consolidacion_ajustes.md


```

[PWA Frontend] -> POST /api/inventario/consolidar -> [FastAPI Backend]
|
+---------------------------------------------------------+
|
v

1. Validar estado operativa (Estado 24: Inicio Cierre)
|
v
2. Calcular Deltas Matemáticos:
* Físico (bar_detalle_fisico) VS Ideal (vista_inventario_barra_con_filtro)
* Excluir productos de la tabla 'inventario_excluido'
|
v


3. ¿Existen Sobrantes? (Físico > Ideal)
├── SÍ -> Insertar Cabecera en `bar_ajuste` (Estado 16, Movimiento 84)
│         └── Capturar ID autoincremental -> Insertar en `bar_detalle_ajuste`
|
v
4. ¿Existen Faltantes? (Físico < Ideal)
├── SÍ -> Insertar Cabecera en `bar_salida_inventario` (Estado 16, Tipo Salida 77)
│         └── Capturar ID autoincremental -> Insertar en `bar_detalle_salida_inv`
|
v
5. Consolidación Final (Etapa 5):
├── Actualizar stock en `bar_inventario` (Igualar a Físico Real)
├── Cambiar estado de Cabeceras creadas de 16 a 20 (Cerrado)
└── Insertar auditoría en `ope_novedades`
|
v
[COMMIT Base de Datos] -> Respuesta Exitosa a PWA -> Inventario Sincronizado (Diferencias = 0)

```

---

## 2. Mapeo de Modelos en SQLAlchemy (`models.py`)

Para interactuar con las tablas de ajustes mediante el ORM, es necesario añadir las definiciones de las estructuras de cabeceras y detalles que faltaban en tu archivo `models.py`.

```python
# Añadir a models.py

class AjusteIngreso(Base):
    __tablename__ = "bar_ajuste"
    
    id = Column(Integer, primary_key=True, index=True)
    fecha = Column(Date)
    numero_documento = Column(String(50), nullable=True)
    observaciones = Column(String(255))
    recepcionado_por = Column(String(255))
    ind_estado_ingreso = Column(Integer, default=16)  # 16: En Proceso, 20: Cerrado
    ind_tipo_movimiento = Column(Integer, default=84) # 84: Ajuste de Ingreso por Sobrante
    id_operacion = Column(Integer, nullable=True)
    id_barra = Column(Integer)
    usuario_reg = Column(String(255))
    fecha_reg = Column(Date)
    fecha_mod = Column(Date, nullable=True)
    estado = Column(String(3), default='HAB')

class DetalleAjusteIngreso(Base):
    __tablename__ = "bar_detalle_ajuste"
    
    id = Column(Integer, primary_key=True, index=True)
    cantidad = Column(Numeric(10, 2))
    precio_costo = Column(Numeric(10, 2), default=0.00)
    precio_costo_real = Column(Numeric(10, 2), nullable=True)
    observaciones = Column(String(255), nullable=True)
    ind_paq_detalle = Column(String(1)) # '1' para Botella Cerrada, '0' para Onzas (Detalle)
    id_ajuste = Column(Integer)  # ID de la cabecera bar_ajuste
    id_producto = Column(Integer)
    usuario_reg = Column(String(255))
    fecha_reg = Column(Date)
    fecha_mod = Column(Date, nullable=True)
    estado = Column(String(3), default='HAB')

class AjusteSalida(Base):
    __tablename__ = "bar_salida_inventario"
    
    id = Column(Integer, primary_key=True, index=True)
    fecha_salida = Column(Date)
    correlativo = Column(String(50), nullable=True)
    responsable = Column(String(255))
    ind_estado_salida = Column(Integer, default=16)  # 16: En Proceso, 20: Cerrado
    observaciones_salida = Column(String(255))
    id_barra = Column(Integer)
    id_operacion = Column(Integer, nullable=True)
    ind_tipo_salida = Column(Integer, default=77)     # 77: Baja por Ajuste de Inventario
    usuario_reg = Column(String(255))
    fecha_reg = Column(Date)
    fecha_mod = Column(Date, nullable=True)
    estado = Column(String(3), default='HAB')

class DetalleAjusteSalida(Base):
    __tablename__ = "bar_detalle_salida_inv"
    
    id = Column(Integer, primary_key=True, index=True)
    cantidad = Column(Numeric(10, 2))
    ind_paq_detalle = Column(String(1)) # '1' para Botella Cerrada, '0' para Onzas (Detalle)
    id_salida_inventario = Column(Integer)  # ID de la cabecera bar_salida_inventario
    id_producto = Column(Integer)
    usuario_reg = Column(String(255))
    fecha_reg = Column(Date)
    fecha_mod = Column(Date, nullable=True)
    estado = Column(String(3), default='HAB')

class InventarioMaestro(Base):
    """Mapeo de la tabla donde el POS lee el Stock Actual en tiempo real."""
    __tablename__ = "bar_inventario"
    
    id = Column(Integer, primary_key=True, index=True)
    id_producto = Column(Integer)
    id_barra = Column(Integer)
    cantidad_paq = Column(Numeric(10, 2))      # Botellas cerradas vigentes
    cantidad_detalle = Column(Numeric(10, 2))  # Onzas vigentes
    usuario_reg = Column(String(255))
    fecha_mod = Column(DateTime)

```

---

## 3. Definición de Esquemas Pydantic (`schemas.py`)

Definimos la estructura del payload simple que recibirá el endpoint desde el cliente web.

```python
# Añadir a schemas.py

class ConsolidarAjustesRequest(BaseModel):
    id_operacion: int = Field(..., gt=0, description="ID de la operativa a consolidar")
    id_barra: int = Field(..., gt=0, description="ID de la barra asociada")
    observaciones: Optional[str] = Field(None, description="Observaciones opcionales para los asientos")

```

---

## 4. Implementación del Endpoint en FastAPI (`main.py`)

A continuación se detalla la lógica central del endpoint. Este realiza las consultas nativas de cruce, procesa las matrices matemáticas de deltas y aplica las inserciones y actualizaciones requeridas.

```python
# Añadir a main.py

@app.post("/api/inventario/consolidar", status_code=status.HTTP_200_OK)
def consolidar_ajustes_inventario(
    payload: schemas.ConsolidarAjustesRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_usuario_actual)
):
    username_actual = current_user.usuario
    nombre_formateado = f"{current_user.paterno} {current_user.materno}, {current_user.nombres}".upper()
    fecha_actual = datetime.now()
    
    # 1. Validar que la operación exista y esté en estado 'INICIO CIERRE' (24)
    _validar_operacion_inicio_cierre(db, payload.id_operacion)
    
    # Validar consistencia de la barra operativa
    barra_operativa = _resolver_barra_operativa(request)
    if payload.id_barra != barra_operativa:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"La barra enviada ({payload.id_barra}) no coincide con la configurada ({barra_operativa})."
        )

    # 2. Obtener el inventario físico guardado previamente desde la PWA (Estado 62)
    inv_fisico_cabecera = db.query(models.InventarioFisicoPOS).filter(
        models.InventarioFisicoPOS.id_operacion == payload.id_operacion,
        models.InventarioFisicoPOS.id_barra == payload.id_barra,
        models.InventarioFisicoPOS.estado == 'HAB'
    ).first()
    
    if not inv_fisico_cabecera:
        raise HTTPException(
            status_code=404,
            detail="No se encontró un registro de inventario físico (paloteo) pendiente para esta operativa."
        )

    try:
        # =====================================================================
        # CONSULTA CORE: Calcular diferencias entre REAL (Físico) e IDEAL (POS)
        # =====================================================================
        # Cruzamos bar_detalle_fisico con vista_inventario_barra_con_filtro.
        # Aplicamos el filtro normativo para excluir productos de 'inventario_excluido'.
        query_diferencias = text("""
            SELECT 
                df.id_producto,
                df.cantidad_unidad AS real_paq,
                df.cantidad_detalle AS real_det,
                COALESCE(id.stock_ideal_unidades, 0) AS ideal_paq,
                COALESCE(id.stock_ideal_onzas, 0) AS ideal_det,
                (df.cantidad_unidad - COALESCE(id.stock_ideal_unidades, 0)) AS delta_paq,
                (df.cantidad_detalle - COALESCE(id.stock_ideal_onzas, 0)) AS delta_det
            FROM bar_detalle_fisico df
            LEFT JOIN (
                SELECT 
                    id_almacen, 
                    cantidad_paq AS stock_ideal_unidades, 
                    cantidad_detalle AS stock_ideal_onzas
                FROM vista_inventario_barra_con_filtro
            ) id ON df.id_producto = id.id_almacen
            WHERE df.id_inventario_fisico = :id_fisico
              AND df.estado = 'HAB'
              AND df.id_producto NOT IN (SELECT id_producto FROM inventario_excluido)
        """)
        
        filas_dif = db.execute(query_diferencias, {"id_fisico": inv_fisico_cabecera.id}).mappings().all()
        
        if not filas_dif:
            return {"status": "skipped", "mensaje": "No se encontraron diferencias que requieran ajustes."}
            
        sobrantes_paq = []
        sobrantes_det = []
        faltantes_paq = []
        faltantes_det = []
        
        # Clasificar deltas en matrices independientes de sumas y restas
        for fila in filas_dif:
            d_paq = float(fila["delta_paq"])
            d_det = float(fila["delta_det"])
            prod_id = fila["id_producto"]
            
            # Procesar Paquetes (Botellas Cerradas)
            if d_paq > 0:
                sobrantes_paq.append({"id_producto": prod_id, "cantidad": d_paq})
            elif d_paq < 0:
                faltantes_paq.append({"id_producto": prod_id, "cantidad": abs(d_paq)})
                
            # Procesar Detalles (Onzas)
            if d_det > 0:
                sobrantes_det.append({"id_producto": prod_id, "cantidad": d_det})
            elif d_det < 0:
                faltantes_det.append({"id_producto": prod_id, "cantidad": abs(d_det)})

        obs_doc = payload.observaciones if payload.observaciones else f"CONSOLIDACION AUTOMATICA OPERATIVA {payload.id_operacion}"

        # =====================================================================
        # EJECUCIÓN ETAPA 3: REGISTRO DE INGRESOS (SOBRANTES)
        # =====================================================================
        id_ajuste_ingreso = None
        if sobrantes_paq or sobrantes_det:
            cabecera_ingreso = models.AjusteIngreso(
                fecha=fecha_actual.date(),
                observaciones=obs_doc,
                recepcionado_por=nombre_formateado,
                ind_estado_ingreso=16, # En Proceso
                ind_tipo_movimiento=84,
                id_operacion=payload.id_operacion,
                id_barra=payload.id_barra,
                usuario_reg=username_actual,
                fecha_reg=fecha_actual.date()
            )
            db.add(cabecera_ingreso)
            db.flush() # SQLAlchemy captura automáticamente el ID autoincremental
            id_ajuste_ingreso = cabecera_ingreso.id
            
            # Inserts de detalles de botellas sobrantes
            for item in sobrantes_paq:
                db.add(models.DetalleAjusteIngreso(
                    cantidad=item["cantidad"],
                    ind_paq_detalle='1',
                    id_ajuste=id_ajuste_ingreso,
                    id_producto=item["id_producto"],
                    usuario_reg=username_actual,
                    fecha_reg=fecha_actual.date()
                ))
            # Inserts de detalles de onzas sobrantes
            for item in sobrantes_det:
                db.add(models.DetalleAjusteIngreso(
                    cantidad=item["cantidad"],
                    ind_paq_detalle='0',
                    id_ajuste=id_ajuste_ingreso,
                    id_producto=item["id_producto"],
                    usuario_reg=username_actual,
                    fecha_reg=fecha_actual.date()
                ))

        # =====================================================================
        # EJECUCIÓN ETAPA 3: REGISTRO DE SALIDAS (FALTANTES)
        # =====================================================================
        id_ajuste_salida = None
        if faltantes_paq or faltantes_det:
            cabecera_salida = models.AjusteSalida(
                fecha_salida=fecha_actual.date(),
                responsable=nombre_formateado,
                ind_estado_salida=16, # En Proceso
                observaciones_salida=obs_doc,
                id_barra=payload.id_barra,
                id_operacion=payload.id_operacion,
                ind_tipo_salida=77,
                usuario_reg=username_actual,
                fecha_reg=fecha_actual.date()
            )
            db.add(cabecera_salida)
            db.flush()
            id_ajuste_salida = cabecera_salida.id
            
            # Inserts de detalles de botellas faltantes
            for item in faltantes_paq:
                db.add(models.DetalleAjusteSalida(
                    cantidad=item["cantidad"],
                    ind_paq_detalle='1',
                    id_salida_inventario=id_ajuste_salida,
                    id_producto=item["id_producto"],
                    usuario_reg=username_actual,
                    fecha_reg=fecha_actual.date()
                ))
            # Inserts de detalles de onzas faltantes
            for item in faltantes_det:
                db.add(models.DetalleAjusteSalida(
                    cantidad=item["cantidad"],
                    ind_paq_detalle='0',
                    id_salida_inventario=id_ajuste_salida,
                    id_producto=item["id_producto"],
                    usuario_reg=username_actual,
                    fecha_reg=fecha_actual.date()
                ))

        # =====================================================================
        # EJECUCIÓN ETAPA 5: CONSOLIDACIÓN Y ACTUALIZACIÓN MAESTRA
        # =====================================================================
        # 1. Sobreescribir las cantidades del Inventario Real en la tabla maestra bar_inventario
        for fila in filas_dif:
            maestro = db.query(models.InventarioMaestro).filter(
                models.InventarioMaestro.id_producto == fila["id_producto"],
                models.InventarioMaestro.id_barra == payload.id_barra
            ).first()
            
            if maestro:
                maestro.cantidad_paq = fila["real_paq"]
                maestro.cantidad_detalle = fila["real_det"]
                maestro.usuario_reg = username_actual
                maestro.fecha_mod = fecha_actual
        
        # 2. Cambiar estados de documentos temporales a Procesado/Cerrado (Estado 20)
        if id_ajuste_ingreso:
            db.execute(
                text("UPDATE bar_ajuste SET ind_estado_ingreso = 20 WHERE id = :id"),
                {"id": id_ajuste_ingreso}
            )
        if id_ajuste_salida:
            db.execute(
                text("UPDATE bar_salida_inventario SET ind_estado_salida = 20 WHERE id = :id"),
                {"id": id_ajuste_salida}
            )
            
        # 3. Actualizar la cabecera del inventario físico a Procesado Completo (Estado 62 -> Cambiar según lógica POS si aplica)
        inv_fisico_cabecera.fecha_mod = fecha_actual.date()
        
        # 4. Inserción de Logs de Auditoría en `ope_novedades`
        if id_ajuste_ingreso:
            log_ingreso = models.Novedad( # Asegúrate de tener mapeada la tabla ope_novedades
                fecha=fecha_actual,
                usuario=username_actual,
                evento=f"Se registró un Ajuste en Barra: BARRA {payload.id_barra}, con el correlativo NRO {id_ajuste_ingreso} vía API PWA",
                id_operacion=payload.id_operacion,
                usuario_reg=username_actual,
                fecha_reg=fecha_actual,
                estado='HAB'
            )
            db.add(log_ingreso)
            
        if id_ajuste_salida:
            log_salida = models.Novedad(
                fecha=fecha_actual,
                usuario=username_actual,
                evento=f"Se registró una baja por ajuste de la barra: BARRA {payload.id_barra}, con el correlativo NRO {id_ajuste_salida} vía API PWA",
                id_operacion=payload.id_operacion,
                usuario_reg=username_actual,
                fecha_reg=fecha_actual,
                estado='HAB'
            )
            db.add(log_salida)

        # Confirmar toda la transacción de manera segura
        db.commit()
        
        return {
            "status": "success",
            "mensaje": "Ajustes consolidados con éxito. Inventario Ideal igualado al Inventario Real.",
            "documento_ingreso_id": id_ajuste_ingreso,
            "documento_salida_id": id_ajuste_salida,
            "productos_afectados": len(filas_dif)
        }

    except Exception as e:
        db.rollback() # Si algo falla, se revierte todo y no se rompe nada
        logger.exception("Error crítico durante la consolidación de ajustes.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error transaccional en el servidor POS: {str(e)}"
        )

```

---

## 5. Consideraciones Críticas de Seguridad y Control

1. **Inyección de Dependencia del Token de Seguridad:** El endpoint requiere imperativamente la validación de `current_user: models.Usuario = Depends(get_usuario_actual)`. Esto evita llamadas maliciosas de agentes externos y asegura la trazabilidad exacta de qué bartender o administrador presionó el botón en la PWA para los registros de `usuario_reg` y `ope_novedades`.
2. **Uso Normativo de `NOT IN`:** Tal como se define en tus requerimientos operacionales, la consulta que calcula las diferencias integra la cláusula `df.id_producto NOT IN (SELECT id_producto FROM inventario_excluido)`. Esto bloquea por completo la creación de registros huérfanos o ajustes basura sobre familias de productos no inventariables.
3. **Manejo Estricto de Decimales:** Los campos que manipulan onzas utilizan tipos de datos `Numeric(10, 2)` en la base de datos MySQL. En Python, al mapear estos valores, asegúrate de convertirlos explícitamente a tipos nativos utilizando `float()` para mantener la consistencia en el redondeo y evitar distorsiones con fracciones de onza.
'''
