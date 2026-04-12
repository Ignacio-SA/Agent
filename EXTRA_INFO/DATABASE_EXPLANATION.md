# Estructura de Tablas de Ventas en Microsoft Fabric

El Stored Procedure `sp_GetSalesForChatbot` extrae toda la informacion de las ventas cruzando **dos elementos principales** dentro de la base de datos `LH_Silver_Cloud_PRO`.

## 1. Las Tablas Involucradas

### Cabecera (Header) de la Venta
**Tabla:** `[LH_Silver_Cloud_PRO].[dbo].[dt_silver_ingested_cosmos_sales_header]`
*   **Alias en el codigo:** `h`
*   **Que contiene:** La informacion general del "ticket" o transaccion completa. 
*   **Campos clave que extraemos:** 
    *   `id`: Identificador unico de la venta.
    *   `FranchiseCode`: (Importante) El codigo de la franquicia usado para filtrar.
    *   `FranchiseeCode`: Codigo del franquiciado logueado.
    *   `ShiftCode`: Codigo del turno del cajero.
    *   `PosCode`: Identificador de la caja registradora o punto de venta.
    *   `UserName`: Usuario/Cajero que realizo la operacion.

### Detalle (Productos) de la Venta
**Vista/Tabla:** `[LH_Silver_Cloud_PRO].[dbo].[vw_Silver_Cloud_NewDetails]`
*   **Alias en el codigo:** `d`
*   **Que contiene:** El detalle linea por linea de cada articulo que se vendio dentro de un ticket.
*   **Campos clave que extraemos:**
    *   `SaleDocId`: Clave foranea que une el articulo con el ticket.
    *   `SaleDateTimeUtc`: Fecha y hora de la venta (ajustada luego a UTC-3).
    *   `Quantity`: Cantidad de unidades vendidas.
    *   `ArticleId` y `ArticleDescription`: Codigo y nombre del producto.
    *   `UnitPriceFix`: Precio del articulo.
    *   `Type` y `TypeDetail`: Determina si es un producto suelto, combo, promocion, etc.

---

## 2. Como se cruzan? (El JOIN)

El cruce se realiza a traves de un `JOIN` clasico de SQL:

```sql
FROM [LH_Silver_Cloud_PRO].[dbo].[dt_silver_ingested_cosmos_sales_header] h
JOIN [LH_Silver_Cloud_PRO].[dbo].[vw_Silver_Cloud_NewDetails] d 
  ON h.id = d.SaleDocId
```

**Explicacion del cruce:**
Por cada producto (detalle) que existe en la tabla `d`, se busca cual fue su documento de venta usando `d.SaleDocId`. Se iguala ese valor con el identificador principal del ticket en la tabla de cabecera (`h.id`). 

Esto genera una tabla final plana donde, si un ticket tuvo 3 articulos diferentes, habra 3 parrafos (filas) que repiten la misma informacion del ticket, pero cada una mostrando un articulo distinto.
