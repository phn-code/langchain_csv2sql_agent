- The pprogram is a full-stack data intelligence platform that automates the process of turning raw CSV files into a queryable SQL database and provides an AI-powered chat interface to interact with that data.
- It features an intelligent data loader that automatically detects schemas and relationships (Foreign Keys) between disconnected CSVs, and a LangGraph-based agent that answers natural language questions about your data.

🌟 Features
** automated Data Ingestion:**
Loads raw CSV files into PostgreSQL.
Sanitizes table and column names (CamelCase -> snake_case).
Auto-Schema Detection: Automatically identifies Primary Keys and infers Foreign Key relationships between tables based on naming conventions (e.g., matching customer_id in a Sales table to id in a Customers table).
Smart Data Repair: Detects and fixes numeric offset issues in Foreign Keys during ingestion.

🧠 AI Reasoning Engine:
Powered by LangGraph (LangChain) and OpenAI.
Context-aware SQL generation based on the detected schema.

💬 Modern Chat UI:
Clean interface for conversing with your data agents.

🐳 Fully Dockerized: One-command deployment for Database, API, Loader, and UI.

🏗 System Architecture
The project consists of four main services defined in docker-compose.yaml:
db (PostgreSQL 16): Stores the raw data and the inferred schema metadata.
app (Data Loader): A Python service that runs on startup to ingest CSVs, clean data, and map relationships.
langgraph_server (AI Backend): Exposes the LangGraph agent API (Port 2024) to process natural language queries.
chat-ui (Frontend): A Next.js web application (Port 3000) for the user interface.

🚀 Getting Started
Prerequisites
Docker & Docker Compose
An OpenAI API Key
Langchain API Key

Installation
1. Clone the repository:
```bash
git clone 
cd insight_factory


code
Bash
download
content_copy
expand_less
git clone <repository-url>
cd insight_factory

Prepare your Data:
Place your raw .csv files into the loader directory:

code
Bash
download
content_copy
expand_less
# Create the directory if it doesn't exist
mkdir -p csv_to_sql/csv_files

# Copy your CSVs there
cp /path/to/your/data/*.csv ./csv_to_sql/csv_files/

Configure Environment Variables:
Create a .env file in the root directory (or ensure your shell has these exported):

code
Ini
download
content_copy
expand_less
OPENAI_API_KEY=sk-your-openai-key-here

# Optional: For LangSmith Tracing
LANGCHAIN_API_KEY=lsv2-your-langchain-key

Build and Run:

code
Bash
download
content_copy
expand_less
docker-compose up --build

Wait a few moments for the database to initialize and the data loader to finish processing your CSVs.

🖥️ Usage
1. The Data Loading Process

Check the logs of the csv_loader container to see the schema detection in action:

code
Bash
download
content_copy
expand_less
docker logs -f csv_loader

You will see messages indicating that tables were created, Primary Keys were added, and Foreign Keys were inferred and validated.

2. Chatting with Data

Open your browser and navigate to:
http://localhost:3000

Ask questions: "How many customers bought product X?" or "Show me the top 5 sales regions."

The agent will generate SQL queries based on the schema created by the loader and return the results.

3. API Access

The LangGraph API is available at http://localhost:2024.

🛠 Configuration Details
Database Credentials

Defaults are set in docker-compose.yaml.

Host: db

Port: 5432

User: csvuser

Password: csvpass

Database: csvdb

Schema Detection Logic

The data_loader.py script uses the following logic to infer relationships:

Cleaning: Converts file names to snake_case table names.

PK Detection: Looks for columns named id, table_id, or tablename_id that are unique and non-null.

FK Detection: Scans other columns ending in _id. It attempts to match them against known table names (e.g., user_id -> looks for table users or user).

Validation: It runs a SQL query to ensure all FK values exist in the target PK column. If there is a constant numeric offset (e.g., IDs start at 0 in one file but 1 in another), it attempts to UPDATE the data to fix the relationship automatically.

🐛 Troubleshooting

"Database not ready" errors: The services are configured with depends_on and health checks, but if the csv_loader fails to connect immediately, it will retry automatically (up to 10 times).

Invalid Foreign Keys: If the loader warns about "invalid references," it means the ID in your child table doesn't exist in the parent table, and the auto-fixer couldn't find a constant offset. Check your CSV data quality.

Frontend connection refused: Ensure the langgraph_server container is running and healthy (docker ps). The frontend expects the API at http://localhost:2024.

