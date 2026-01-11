import os
import glob
import re
import logging
import argparse
import time
import sys
import pandas as pd
from sqlalchemy import create_engine, text
from typing import Optional

"""
CSV to SQL Loader with Automatic Schema Detection

This script loads CSV files into a PostgreSQL database, attempts to
automatically detect primary keys and foreign key relationships,
and stores the detected schema information.
"""

# config and logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_USER = os.getenv("DB_USER", "user")
DB_PASS = os.getenv("DB_PASSWORD", "pass")
DB_HOST = os.getenv("DB_HOST", "db")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "csvdb")
CSV_FOLDER = "/app/csv_files"

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

class DataLoader:
    def __init__(self, dry_run = False):
        self.dry_run = dry_run
        self.engine = None
        self.loaded_tables = {}
        self.primary_keys = {}
        self.relationships = []

    def connect_db(self, retries= 10, delay= 3): # Attempt to connect to the database multiple times.
        if self.dry_run:
            logger.info("Dry Run, no DB")
            return

        for attempt in range(retries):
            try:
                self.engine = create_engine(DATABASE_URL)
                with self.engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                logger.info("Database connected")
                return
            except Exception as e:
                time.sleep(delay)
       
        logger.error("Could not connect to DB")
        sys.exit(1)

    def clean_name(self, name: str) -> str:
        #Converts CamelCase or mixed strings to snake_case
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name) #CamelCase to Camel_Case
        s2 = re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1) #camelCase to camel_Case
        s3 = s2.lower()
        s4 = s3.replace(" ", "_").replace("-", "_").strip()
        return s4

    def load_data(self): 
        logger.info("Loading CSV files into database...")
        csv_files = glob.glob(os.path.join(CSV_FOLDER, "*.csv"))
       
        if not csv_files:
            logger.warning("No CSV files found")
            return

        for file_path in csv_files:
            file_name = os.path.basename(file_path)
            table_name = self.clean_name(os.path.splitext(file_name)[0])

            try:
                df = pd.read_csv(file_path)
                df.columns = [self.clean_name(c) for c in df.columns]

                for col in df.columns:
                    # Check if column looks like an ID
                    if col.endswith("_id") or col == "id" or col.endswith("id"):
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                        df[col] = df[col].astype("Int64")

                self.loaded_tables[table_name] = df

                if self.dry_run:
                    logger.info("dry run not loading tables")
                else:
                    # loading to sql
                    df.to_sql(table_name, self.engine, if_exists="replace", index=False)
                    logger.info(f"{table_name}: Loaded {len(df)} rows")
           
            except Exception as e:
                logger.error(f"error processing {file_name}: {e}")

    def find_primary_keys(self):
        """
        Try to guess a primary key for each table.
        Assumption: most tables have an id or *_id column.
        """
        for table, df in self.loaded_tables.items():
            pk = self._find_pk_candidate(df, table)
           
            if pk:
                self.primary_keys[table] = pk
                if self.dry_run:
                    logger.info(f"dry run: PK for '{table}' is '{pk}'")
                else:
                    self._apply_primary_key(table, pk)
            else:
                logger.warning(f"{table}: no primary key detected")

    def _find_pk_candidate(self, df: pd.DataFrame, table_name: str) -> Optional[str]:
        if '_' in table_name:
            base_name = table_name.split('_', 1)[1]
        else:
            base_name = table_name
        if base_name.endswith('s'):
            base_name = base_name[:-1] #base name is 2nd singuar, customer_name -> name

        candidates = [
            'id',
            f"{table_name}_id", f"{table_name}id",
            f"{base_name}_id", f"{base_name}id",
        ]

        for col in df.columns:
            if col in candidates:
                # Must be unique and not null
                if df[col].is_unique and not df[col].isnull().any():
                    return col
        return None

    def _apply_primary_key(self, table: str, pk: str):
        try:
            with self.engine.begin() as conn:
                conn.execute(text(f'ALTER TABLE "{table}" ADD PRIMARY KEY ("{pk}");'))
            logger.info(f"{table}: primary key added")
        except Exception as e:
            logger.error(f"{table} error: {e}")

    def find_relationships(self):
        all_tables = list(self.loaded_tables.keys())

        for table, df in self.loaded_tables.items():
            table_pk = self.primary_keys.get(table)

            for col in df.columns:
                # Skip if it's the table's own PK or doesn't look like an ID
                if col == table_pk or not (col.endswith("_id") or col.endswith("id")):
                    continue

                base_col = col.replace("_id", "").replace("id", "") #customer_id -> customer
               
                potential_targets = { #potential target table names
                    base_col, # "customer"
                    base_col + "s", # "customers"
                    f"_{base_col}", # "_customer"
                    f"_{base_col}s" # "_customers"
                }

                for t in all_tables: # Also look for tables that end with the base name (e.g. "sales_customers")
                    if t.endswith(f"_{base_col}") or t.endswith(f"_{base_col}s"):
                        potential_targets.add(t)

                for target in potential_targets: #Check which potential target exists
                    if target == table or target not in all_tables:
                        continue

                    target_pk = self.primary_keys.get(target)
                    if not target_pk:
                        continue

                    if self.validate_and_log_fk(table, col, target, target_pk):
                        self.relationships.append({
                            "source_table": table,
                            "source_col": col,
                            "target_table": target,
                            "target_col": target_pk
                        })
                   
                        break

    def validate_and_log_fk(self, table, col, target, target_pk) -> bool:
        logger.info(f"Checking fk: {table}.{col}")
       
        if self.dry_run:
            return True

        invalid_sql = f"""
            SELECT COUNT(*)
            FROM "{table}"
            WHERE "{col}" IS NOT NULL
            AND "{col}" NOT IN (SELECT "{target_pk}" FROM "{target}");
        """

        with self.engine.connect() as conn:
            try:
                invalid_count = conn.execute(text(invalid_sql)).scalar()
                if invalid_count == 0:
                    logger.info("fk valid")
                    return True
                else:
                    logger.warning(f"{invalid_count} invalid references found in {table}")

                    # Try to detect and fix offset mismatch
                    fk_sql = f'SELECT DISTINCT "{col}" FROM "{table}" WHERE "{col}" IS NOT NULL'
                    fk_values = [row[0] for row in conn.execute(text(fk_sql)).fetchall()]

                    pk_sql = f'SELECT DISTINCT "{target_pk}" FROM "{target}"'
                    pk_values = [row[0] for row in conn.execute(text(pk_sql)).fetchall()]

                    if not fk_values or not pk_values:
                        return False

                    pk_set = set(pk_values)

                    # Assume numeric; try to find a common offset
                    try:
                        ref_fk = fk_values[0]
                        fixed = False
                        for candidate_pk in pk_values:
                            offset = candidate_pk - ref_fk
                            if offset == 0:
                                continue
                            if all((f + offset) in pk_set for f in fk_values):
                                logger.info(f"Detected constant offset {offset}, fixing FK by adding {offset} to {col} in {table}")
                                update_sql = f'UPDATE "{table}" SET "{col}" = "{col}" + {offset}'
                                conn.execute(text(update_sql))
                                conn.commit()
                                # Re-validate
                                new_invalid = conn.execute(text(invalid_sql)).scalar()
                                if new_invalid == 0:
                                    logger.info("Fix successful, fk now valid")
                                    fixed = True
                                    break
                                else:
                                    logger.error("Fix failed, reverting or handling not implemented")
                                    # Note: No revert for simplicity
                        return fixed
                    except TypeError as te:
                        logger.debug("Columns not numeric for offset calculation")
                        return False

            except Exception as e:
                logger.error(f"fk error: {e}")
                return False

    def save_relationships(self):
        if self.dry_run or not self.relationships:
            return
        db_schema = "database_schema"
        try:
            meta_df = pd.DataFrame(self.relationships)
            meta_df.to_sql(db_schema, self.engine, if_exists="replace", index=False)
            with self.engine.begin() as conn:
                conn.execute(text(f'ALTER TABLE "{db_schema}" ADD COLUMN id SERIAL PRIMARY KEY;'))
            logger.info(f"schema stored at {db_schema}")
        except Exception as e:
            logger.error(f"Schema error: {e}")

    def run(self):
        self.connect_db()
        self.load_data()
        self.find_primary_keys()
        self.find_relationships()
        self.save_relationships()
        logger.info("Done loading")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    loader = DataLoader(dry_run=args.dry_run)
    loader.run()