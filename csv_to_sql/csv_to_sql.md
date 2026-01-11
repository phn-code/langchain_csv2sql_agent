CSV to SQL Loader with Auto Schema Detection

Overview

This Python program automatically loads CSV files into a PostgreSQL database and attempts to infer the database schema.
It standardizes table and column names, detects primary keys, identifies foreign key relationships, validates those relationships, and stores the detected schema information for later use.

The script also supports a dry-run mode, allowing safe testing without writing any data to the database.

Features

Automatically loads all CSV files from a directory into PostgreSQL

Cleans table and column names into snake_case

Attempts to detect and apply primary keys

Infers foreign key relationships between tables

Validates foreign key integrity

Stores detected schema relationships in a metadata table

Supports dry-run mode for safe execution


Environment Variables
The database connection is configured using environment variables:
| Variable      | Description       | Default |
| ------------- | ----------------- | ------- |
| `DB_USER`     | Database username | `user`  |
| `DB_PASSWORD` | Database password | `pass`  |
| `DB_HOST`     | Database host     | `db`    |
| `DB_PORT`     | Database port     | `1234`  |
| `DB_NAME`     | Database name     | `csvdb` |

CSV files must be placed in:
/app/csv_files

How It Works
1. Database Connection

The program connects to PostgreSQL using SQLAlchemy.
If the connection fails, it retries several times before exiting.
In dry-run mode, no database connection is made.

2. Name Cleaning

All table and column names are converted to snake_case:
Removes spaces and hyphens
Converts CamelCase to lowercase with underscores
CustomerID → customer_id
Order Date → order_date

3. Loading CSV Files

All CSV files in the target folder are read using Pandas
Each file becomes a database table
Tables are replaced if they already exist
DataFrames are stored in memory for later analysis

4. Primary Key Detection
For each table, the program attempts to detect a primary key by:
Searching for common ID column patterns (id, table_id, customer_id)
Ensuring the column is unique and contains no null values
If found:
The column is stored as the primary key
A primary key constraint is added in the database (unless in dry-run mode)

5. Foreign Key Detection
The program detects relationships by:
Scanning columns ending in _id or id
Matching column names to other table names
Checking that the target table has a primary key

6. Foreign Key Validation
Each detected relationship is validated by checking for invalid references:
Rows where the foreign key value does not exist in the target table
Warnings are logged if invalid references are found

7. Schema Metadata Storage
Detected relationships are saved into a metadata table:
Stored fields:
Source table
Source column
Target table
Target column

This allows future tools or agents to understand the database structure.