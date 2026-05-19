package org.upm.inesdata.federated.sql.index.schema.postgres;

import org.upm.inesdata.federated.sql.index.schema.BaseSqlDialectStatements;
import org.eclipse.edc.sql.dialect.PostgresDialect;
import org.eclipse.edc.sql.translation.PostgresqlOperatorTranslator;

import static java.lang.String.format;

/**
 * PostgreSQL-specific SQL dialect statements used for JSON operations. Extends {@link BaseSqlDialectStatements} and
 * provides PostgreSQL-specific implementations for JSON-related operations.
 */
public class PostgresDialectStatements extends BaseSqlDialectStatements {
  /**
   * Constructs a PostgresDialectStatements object using a PostgreSQL operator translator.
   */
  public PostgresDialectStatements() {
    super(new PostgresqlOperatorTranslator());
  }

  /**
   * Retrieves the PostgreSQL operator for formatting as JSON.
   *
   * @return the PostgreSQL JSON cast operator.
   */
  @Override
  public String getFormatAsJsonOperator() {
    return PostgresDialect.getJsonCastOperator();
  }

  @Override
  public String getInsertDataServiceTemplate() {
    return format(
        "INSERT INTO %s (%s, %s, %s) VALUES (?, ?, ?) ON CONFLICT (%s) DO NOTHING",
        getDataServiceTable(),
        getDataServiceIdColumn(),
        getDataServiceTermsColumn(),
        getDataServiceEndpointUrlColumn(),
        getDataServiceIdColumn()
    );
  }

  @Override
  public String getInsertCatalogDataServiceTemplate() {
    return format(
        "INSERT INTO %s (catalog_id, data_service_id) VALUES (?, ?) ON CONFLICT (catalog_id, data_service_id) DO NOTHING",
        getCatalogDataServiceTable()
    );
  }
}
