---

# 📘 Guía Técnica

## Refactorización de consultas basadas en `codigo` hacia `id_producto`

---

## 1. 🎯 Propósito del Documento

Este documento tiene como objetivo:

* Identificar los problemas estructurales en las consultas actuales del sistema
* Explicar los riesgos asociados al uso del campo `codigo` como clave de relación
* Justificar la necesidad de refactorización hacia el uso de `id_producto`
* Definir una estrategia técnica clara para implementar el cambio sin afectar la operación del sistema

---

## 2. 🧠 Contexto Actual

Actualmente, varias consultas del sistema (especialmente en inventario y paloteo) utilizan relaciones como:

```sql
d.codigo_producto_receta = a.codigo
```

Donde:

* `d.codigo_producto_receta` proviene de `comandas_v9_detallada`
* `a.codigo` proviene de `alm_producto`

Sin embargo, la misma vista `comandas_v9_detallada` ya contiene:

```sql
id_producto_receta
```

📌 Es decir: el sistema ya dispone de una clave técnica más robusta, pero no está siendo utilizada.

---

## 3. 🚨 Problema Principal

### Uso incorrecto de claves de negocio como claves técnicas

El campo `codigo`:

* Es editable
* No está diseñado como identificador inmutable
* No tiene garantía estructural de integridad referencial

Mientras que:

```text
id (alm_producto)
```

* Es único
* Es inmutable
* No se reutiliza
* Representa la verdadera identidad del producto

---

## 4. ⚠️ Riesgos del enfoque actual

---

### 4.1 🔥 Inconsistencia por cambios de código

Escenario:

1. Producto original:

```text
id = 150
codigo = "GIN01"
```

2. Se usa en:

* comandas
* inventario
* paloteo

3. Se modifica el código:

```text
codigo = "GIN-IMPORTADO"
```

#### Resultado:

* Los joins dejan de coincidir
* Se generan datos huérfanos
* Se rompe la trazabilidad histórica

---

### 4.2 🧨 Dependencia de integridad manual

Actualmente:

* No existe `FOREIGN KEY` entre tablas
* La integridad depende del correcto mantenimiento del `codigo`

👉 Esto es altamente riesgoso en sistemas productivos

---

### 4.3 🐌 Impacto en performance

Comparación:

| Tipo de JOIN       | Rendimiento |
| ------------------ | ----------- |
| VARCHAR (`codigo`) | Más lento   |
| INT (`id`)         | Más rápido  |

👉 En consultas grandes (como `comandas_v9_detallada`), esto es significativo

---

### 4.4 👻 Bugs silenciosos

El uso de `codigo` puede generar:

* duplicaciones invisibles
* errores en agregaciones (`SUM`, `MAX`)
* diferencias “fantasma” en inventario

---

## 5. 🧠 Diagnóstico Técnico

La vista:

```sql
comandas_v9_detallada
```

ya incluye:

```sql
id_producto_receta
```

📌 Esto significa:

👉 El sistema ya está correctamente modelado
👉 Solo falta alinear las consultas

---

## 6. ✅ Solución Propuesta

---

### 6.1 🔄 Refactorización de JOINs

---

#### ❌ Antes

```sql
INNER JOIN alm_producto a 
    ON d.codigo_producto_receta = a.codigo
```

---

#### ✅ Después

```sql
INNER JOIN alm_producto a 
    ON d.id_producto_receta = a.id
```

---

### 6.2 📦 Refactorización de subconsultas

---

#### ❌ Antes

```sql
SELECT DISTINCT d.codigo_producto_receta
```

---

#### ✅ Después

```sql
SELECT DISTINCT d.id_producto_receta
```

---

### 6.3 🔧 Ajustes adicionales recomendados

Si otras vistas usan `codigo`, se recomienda:

* incorporar `id_producto`
* migrar progresivamente todos los joins

---

## 7. 🏗️ Impacto de la Refactorización

---

### 7.1 ✅ Beneficios técnicos

* Integridad referencial real
* Eliminación de dependencias frágiles
* Reducción de errores silenciosos
* Mejora en rendimiento de consultas

---

### 7.2 ✅ Beneficios funcionales

* Inventario más confiable
* Paloteo más preciso
* Cálculo de COGS más consistente
* Auditoría completamente trazable

---

### 7.3 ✅ Beneficios a largo plazo

* Base sólida para APIs (FastAPI)
* Escalabilidad del sistema
* Soporte para multi-sucursal
* Evolución hacia arquitectura enterprise

---

## 8. 🧩 Estrategia de Implementación

---

### 🟡 Fase 1 – Migración parcial (segura)

* Reemplazar joins en nuevas consultas
* Mantener `codigo` solo como atributo visual

---

### 🟢 Fase 2 – Validación

Ejecutar:

```sql
SELECT *
FROM comandas_v9_detallada d
LEFT JOIN alm_producto a 
    ON d.id_producto_receta = a.id
WHERE a.id IS NULL;
```

👉 Resultado esperado: `0 filas`

---

### 🔵 Fase 3 – Migración completa

* Refactorizar vistas críticas
* Eliminar dependencias de `codigo` en lógica

---

## 9. 🧠 Principio de Diseño Adoptado

> 🔒 **Las relaciones entre entidades deben basarse en identificadores técnicos inmutables, no en atributos de negocio.**

---

## 10. 🏁 Conclusión

El sistema actualmente funciona, pero está apoyado en una base frágil:

👉 uso de `codigo` como clave de relación

La refactorización propuesta:

* no requiere cambios estructurales complejos
* aprovecha capacidades ya existentes (`id_producto_receta`)
* mejora significativamente la robustez del sistema

---

## 🚀 Recomendación Final

Implementar la refactorización de manera progresiva comenzando por:

1. Consultas de inventario
2. Consultas de paloteo
3. Vistas base del sistema

---

Si quieres, en el siguiente paso podemos convertir este documento en:

👉 **checklist ejecutable + script de refactorización real**
para aplicar cambios sin romper producción

Ahí ya pasamos de teoría a cirugía en vivo 😏
