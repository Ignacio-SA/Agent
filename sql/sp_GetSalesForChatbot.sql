ALTER PROCEDURE [dbo].[sp_GetSalesForChatbot]
    @FranchiseCode NVARCHAR(100),
    @Year          INT      = NULL,
    @DateFrom      DATETIME = NULL,
    @DateTo        DATETIME = NULL
AS
BEGIN
    -- Si no se pasa año ni fechas, usa el año actual (en horario Argentina UTC-3)
    IF @Year IS NULL AND @DateFrom IS NULL AND @DateTo IS NULL
        SET @Year = YEAR(DATEADD(hour, -3, GETUTCDATE()))

    SELECT h.id, h.FranchiseeCode, h.ShiftCode, h.PosCode,
           h.UserName,
           DATEADD(hour, -3, CAST(d.SaleDateTimeUtc AS DATETIME)) AS SaleDateTimeUtc,
           d.Quantity,
           d.ArticleId, d.ArticleDescription, d.TypeDetail, d.UnitPriceFix
    FROM [LH_Silver_Cloud_PRO].[dbo].[dt_silver_ingested_cosmos_sales_header] h
    JOIN [LH_Silver_Cloud_PRO].[dbo].[vw_Silver_Cloud_NewDetails] d ON h.id = d.SaleDocId
    WHERE h.FranchiseCode = @FranchiseCode
      AND (
            -- Filtro por año en horario Argentina (UTC-3)
            (@DateFrom IS NULL AND @DateTo IS NULL
             AND YEAR(DATEADD(hour, -3, CAST(d.SaleDateTimeUtc AS DATETIME))) = @Year)
            OR
            -- Filtro por rango de fechas (parámetros recibidos en horario Argentina, se convierten a UTC para comparar)
            (@DateFrom IS NOT NULL
             AND CAST(d.SaleDateTimeUtc AS DATETIME) >= DATEADD(hour, 3, @DateFrom)
             AND (@DateTo IS NULL OR CAST(d.SaleDateTimeUtc AS DATETIME) <= DATEADD(hour, 3, @DateTo)))
          )
    ORDER BY d.SaleDateTimeUtc DESC
END
