import os
import re
import base64
import urllib.parse
import textwrap  
from typing import TypedDict, Literal, Optional, List, Annotated

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=True)

from langchain_openai import ChatOpenAI
from langchain_community.utilities import SQLDatabase
from langchain_experimental.utilities import PythonREPL
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, END
from langchain_core.messages import BaseMessage, AIMessage

# loading da config
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASSWORD", "password")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "csvdb")

def env_to_bool(var_name: str, default: str = "false") -> bool:
    #converts env string to a bool
    value = os.getenv(var_name, default)  
    value = value.lower()                 
    if value == "true" or value == "1" or value == "t" or value == "yes":
        return True
    else:
        return False

os.environ["LANGCHAIN_TRACING_V2"] = "true" #enable tracing

encoded_user = urllib.parse.quote_plus(DB_USER)
encoded_pass = urllib.parse.quote_plus(DB_PASS)
DATABASE_URL = f"postgresql+psycopg2://{encoded_user}:{encoded_pass}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# try:
#     db = SQLDatabase.from_uri(DATABASE_URL)
#     print("Connected to Database")
# except Exception as e:
#     print(f"Database Connection error: {e}")
#     db = None
    
from sqlalchemy import create_engine
try:
    engine = create_engine(DATABASE_URL)
    db = SQLDatabase(engine, schema="public")
    print("--------------------------------------------------")
    print("DEBUG: Connection Successful.")
    tables = db.get_table_info()
    if tables:
        print(f"DEBUG: Found Tables:\n{tables}")
    else:
        print("DEBUG: Connected, but NO tables found (Check schema/permissions)")
    print("--------------------------------------------------")
except Exception as e:
    print(f"Database Connection ERROR: {e}")
    db = None

# impressed with latency and the cost of gpt 5 nano
llm = ChatOpenAI(model="gpt-5-nano", temperature=0)
repl = PythonREPL() #enviourment to execute python code

# what the agent stores
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages] #enable persistent conversation
    question: str #user original question
    proactive_insights: bool #from .env flag
    schema: str #database schema info
    sql_query: str #generated sql query
    sql_result: str #result from sql query
    sql_valid: bool 
    next_step: Literal["direct_response", "python_analysis", "discovery"] 
    python_code: Optional[str] #code generated from llm
    python_output: Optional[str] #execution text output
    image_base64: Optional[str] #visualization
    insights_output: Optional[str] #proactive insights text
    final_answer: str 
    meta: Optional[dict]  

# helper functions
def get_image_base64(filepath="plot.png"):
    if os.path.exists(filepath):
        with open(filepath, "rb") as f:
            data = base64.b64encode(f.read()).decode('utf-8')
        os.remove(filepath) 
        return data
    return None

FORBIDDEN_SQL_PATTERN = re.compile(
    r"\b(DROP|DELETE|UPDATE|INSERT|ALTER|TRUNCATE)\b",
    re.IGNORECASE,
)

def validate_sql_query_safety(query: str) -> bool:
    #make sure sql query doesn't modify db
    return not FORBIDDEN_SQL_PATTERN.search(query)

# Langchain Nodes
def user_request_node(state: AgentState):
    # First node: get user question and DB schema
    messages = state.get("messages", []) #supports multimodal messages
    current_question = ""
    
    if messages:
        last_msg = messages[-1]
        if isinstance(last_msg.content, list):
            text_parts = []

            for part in last_msg.content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text_parts.append(part.get("text", ""))

            current_question = " ".join(text_parts)
        else:
            current_question = str(last_msg.content) #safe fallback
    # elif state.get("question"):
    #     current_question = state.get("question")
        
    if not current_question:
        return {"final_answer": "Error: No question provided"}
    if not db:
        return {"schema": "Database not connected.", "question": current_question, "final_answer": "No db :()"}
    enable_insights = env_to_bool("PROACTIVE_INSIGHTS")
        
    return {
        "schema": db.get_table_info(), 
        "question": current_question,
        "proactive_insights": enable_insights,
        "sql_result": None,
        "python_output": None, 
        "insights_output": None,
        "image_base64": None,
        "final_answer": None
    }

def node_sql_layer(state: AgentState):
    if not db or "Error" in state.get("schema", ""):
        return {"sql_query": None, "sql_result": "Database connection error.", "sql_valid": False} #fail fast

    prompt_template = """
    You are a Postgres Expert.
    Question: {question}
    Schema: {schema}
    
    Return a SINGLE VALID SQL query. Return ONLY raw SQL.
    If unable to answer, return "NO_SQL".
    """
    prompt = ChatPromptTemplate.from_template(prompt_template)
    # 1 fill the prompt using values from state (question, schema, etc.)
    formatted_prompt = prompt.invoke(state)
    # 2 send the prompt to the LLM
    llm_response = llm.invoke(formatted_prompt)
    # 3. extract the text part from  LLM response
    query = StrOutputParser().invoke(llm_response)
    # 4. strip whitespace
    query = query.strip()
    query = query.replace("```sql", "").replace("```", "").strip() #Removes the starting ```sql
    
    if query == "NO_SQL" or not validate_sql_query_safety(query):
        return {"sql_query": query, "sql_result": "SQL not valid or safe :(", "sql_valid": False}

    try:
        result = db.run(query, include_columns=True)
        if not result:
            return {"sql_query": query, "sql_result": "0 rows returned", "sql_valid": False}
        return {"sql_query": query, "sql_result": str(result), "sql_valid": True} #returning sql query and result
    except Exception as e:
        return {"sql_query": query, "sql_result": f"SQL Error: {str(e)}", "sql_valid": False}

class router_output(BaseModel):
    decision: Literal["direct_response", "python_analysis", "discovery"] #allowed outputs of a router using pydantic model

def node_router(state: AgentState): #routing logic of langchain agent
    raw_question = state.get("question", "")
    if isinstance(raw_question, list):
        question = " ".join(map(str, raw_question)) #converts each list element to a string
    else:
        question = str(raw_question)
    question = question.lower()

    if not state.get("sql_valid", False): #direct response if sql is invalid
        return {"next_step": "direct_response"}

    if any(keyword in question for keyword in ["plot", "chart", "graph", "visualize", "visualization"]): #key word matching for speed
        return {"next_step": "python_analysis"}

    if state.get("proactive_insights") and state.get("sql_valid"): #env flag check for insights
        return {"next_step": "discovery"}

    parser = JsonOutputParser(pydantic_object=router_output)
    prompt_template = """
        Analyze the situation.
        Question: {question}
        SQL Valid: {sql_valid}
        SQL Result: {sql_result}
        
        Rules:
        1. "python_analysis": If user asks for visualization (plot, chart), complex math, or if SQL result looks like raw data needing processing.
        2. "discovery": If SQL result is empty/boring and user asked to "explore".
        3. "direct_response": Simple Q&A answered by SQL.
        
        {format_instructions}
    """
    prompt = ChatPromptTemplate.from_template(prompt_template, partial_variables={"format_instructions": parser.get_format_instructions()})
    
    try:
        # 1 build the prompt from state
        formatted_prompt = prompt.invoke(state)
        # 2. ask the LLM to make a routing decision
        llm_response = llm.invoke(formatted_prompt)
        # 3 parse the LLM output into structured data
        parsed_output = parser.invoke(llm_response)
        # 4 extract the decision
        decision = parsed_output["decision"]
        return {"next_step": decision}
    except:
        return {"next_step": "direct_response"} #fallback

def node_insights(state: AgentState):
    template = "Generate 3 discovery SQL queries for schema: {schema}. Return separated by semicolon."
    prompt = ChatPromptTemplate.from_template(template)
    formatted_prompt = prompt.invoke(state)
    response = llm.invoke(formatted_prompt)
    raw = response.content
    queries = []
    for q in raw.split(";"):
        cleaned_query = q.strip()          # remove whitespace/newlines
        if not cleaned_query:
            continue                       # skip empty strings
        if validate_sql_query_safety(cleaned_query):
            queries.append(cleaned_query)  # keep only safe SQL
    insights = []
    for q in queries:
        try:
            res = db.run(q)
            summary = llm.invoke(f"Summarize finding: {q} -> {res}").content
            insights.append(f"- {summary}")
        except: continue
        
    return {"insights_output": "\n".join(insights) if insights else "No insights found."}

def node_python(state: AgentState):
    """Generates and executes Python code for Visualization."""
    
    # Summarize sql_result, extract columns and sample data
    sql_result = state.get("sql_result", "")
    summary_template = "Extract column names and first 5 rows as string: {data}"
    summary_prompt = ChatPromptTemplate.from_template(summary_template)
    columns_summary = (summary_prompt | llm | StrOutputParser()).invoke({
        "data": sql_result
    })

    prompt_text = """
    You are a Python Data Analyst.
    Your goal is to VISUALIZE the data based on the user's request: "{question}"
    
    The data is ALREADY loaded in a pandas DataFrame named `df`.
    
    Rules:
    1. Use `df` directly. DO NOT create fake data.
    2. Use `matplotlib.pyplot` as `plt`.
    3. create the plot using `plt.bar`, `plt.plot`, etc.
    4. DO NOT use `plt.show()`.
    5. DO NOT print the dataframe.
    6. Return ONLY valid Python code. NO explanations. NO markdown backticks.
    
    Data summary: {columns}
    """
    
    prompt = ChatPromptTemplate.from_template(prompt_text)
    logic = (prompt | llm).invoke({
        "question": state["question"],
        "columns": columns_summary
    }).content
    
    logic = logic.replace("```python", "").replace("```", "").strip()
    logic = textwrap.dedent(logic)  # Dedent to prevent indentation errors
    
    full_code = f"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
from sqlalchemy import create_engine
import sys

try:
    engine = create_engine('{DATABASE_URL}')
    query = \"\"\"{state['sql_query']}\"\"\"
    df = pd.read_sql(query, engine)
except Exception as e:
    print(f"DATA LOAD ERROR: {{e}}")
    raise Exception("Data load failed")  # Raise instead of sys.exit for better REPL handling

print("Executing analysis...")
{logic}

try:
    if plt.get_fignums():
        plt.tight_layout()
        plt.savefig('plot.png')
        print("SUCCESS: Plot generated.")
    else:
        print("WARNING: No plot created.")
except Exception as e:
    print(f"PLOT SAVE ERROR: {{e}}")
"""
    
    try:
        output = repl.run(full_code)
        img_data = get_image_base64("plot.png")
        if img_data:
            return {
                "python_code": full_code, 
                "python_output": "Visualization generated :)", 
                "image_base64": img_data
            }
        else:
            return {
                "python_output": f"code ran but didn't generate image {output}",
                "image_base64": None
            }
    except Exception as e:
        return {"python_output": f"python execution Error: {e}"}

def node_assembly(state: AgentState):
    parts = []
    if state.get("sql_result"): parts.append(f"SQL Data: {state['sql_result']}")
    if state.get("python_output"): parts.append(f"Action Status: {state['python_output']}")
    if state.get("insights_output"): parts.append(f"Insights: {state['insights_output']}")
    context = "\n".join(parts)
    
    # Check if we successfully generated an image
    has_image = bool(state.get("image_base64"))

    if has_image:
        template = """
        You are a Data Analyst.
        
        The user asked: {question}
        
        CONTEXT:
        1. A visualization has ALREADY been generated and attached to this message. 
        2. SQL Data found: {context}
        
        INSTRUCTIONS:
        - Do NOT write Python code.
        - Do NOT describe how to make the chart.
        - Do NOT dump the raw data numbers (unless specifically asked).
        - DO briefly summarize the trend or insight shown in the data/chart.
        - Keep the response concise and professional.
        """
    else:
        template = "Answer user: {question}\nBased on tools: {context}"
    
    prompt = ChatPromptTemplate.from_template(template)
    chain = prompt | llm
    
    response = chain.invoke({
        "question": state["question"],
        "context": context
    })
    draft = response.content
    
    # 2 PII Redaction Step
    pii_template = """
    You are a Data Privacy Officer. 
    Review the text below and redact any Personally Identifiable Information (PII).
    
    Rules for Redaction:
    1. Replace specific human names with [REDACTED].
    2. Replace email addresses, phone numbers, and physical addresses with [REDACTED].
    3. DO NOT redact: City names, Country names, Product names, Business Names, or IDs.
    4. If the text contains no PII, return it exactly as is.
    
    Text to review:
    {text}
    """
    
    final_text = (ChatPromptTemplate.from_template(pii_template) | llm).invoke({"text": draft}).content

    # 3 Final Message 
    additional_kwargs = {} 
    if has_image:
        additional_kwargs["image_base64"] = state["image_base64"]
        
    response_message = AIMessage(content=final_text, additional_kwargs=additional_kwargs)
    
    return {
        "messages": [response_message],
        "final_answer": final_text,
    }

# constructing the langchain graph
workflow = StateGraph(AgentState)
#adding the different nodes
workflow.add_node("user_request", user_request_node)
workflow.add_node("sql_layer", node_sql_layer)
workflow.add_node("router", node_router)
workflow.add_node("python_node", node_python)
workflow.add_node("insight_node", node_insights)
workflow.add_node("assembly", node_assembly)

workflow.set_entry_point("user_request") #define flow

# workflow.add_conditional_edges(
#     "user_request",
#     lambda state: "assembly" if "final_answer" in state else "sql_layer",
#     {"assembly": "assembly", "sql_layer": "sql_layer"}
# )
workflow.add_conditional_edges(
    "user_request",
    # Check if final_answer is not None and not empty
    lambda state: "assembly" if state.get("final_answer") else "sql_layer",
    {"assembly": "assembly", "sql_layer": "sql_layer"}
)
workflow.add_edge("sql_layer", "router")

workflow.add_conditional_edges(
    "router",
    lambda x: x["next_step"],
    {
        "direct_response": "assembly",
        "python_analysis": "python_node",
        "discovery": "insight_node"
    }
)
workflow.add_edge("python_node", "assembly")
workflow.add_edge("insight_node", "assembly")
workflow.add_edge("assembly", END)
app = workflow.compile()

# import os
# import re
# import base64
# import urllib.parse
# from typing import TypedDict, Literal, Optional, List, Annotated

# from dotenv import load_dotenv, find_dotenv
# load_dotenv(find_dotenv(), override=True)

# # Third-party imports
# from langchain_openai import ChatOpenAI
# from langchain_community.utilities import SQLDatabase
# from langchain_experimental.utilities import PythonREPL
# from langchain_core.prompts import ChatPromptTemplate
# from langchain_core.output_parsers import StrOutputParser, JsonOutputParser
# from langchain_core.messages import BaseMessage
# from langgraph.graph.message import add_messages
# from pydantic import BaseModel, Field
# from langgraph.graph import StateGraph, END
# from langchain_core.messages import BaseMessage, AIMessage # <--- Add AIMessage

# # --- 1. Configuration & Setup ---

# DB_USER = os.getenv("DB_USER", "postgres")
# DB_PASS = os.getenv("DB_PASSWORD", "password")
# DB_HOST = os.getenv("DB_HOST", "localhost")
# DB_PORT = os.getenv("DB_PORT", "5432")
# DB_NAME = os.getenv("DB_NAME", "csvdb")

# def env_to_bool(var_name: str, default: str = "false") -> bool:
#   """Helper to convert env string to boolean."""
#   return os.getenv(var_name, default).lower() in ("true", "1", "t", "yes")

# os.environ["LANGCHAIN_TRACING_V2"] = "true"

# encoded_user = urllib.parse.quote_plus(DB_USER)
# encoded_pass = urllib.parse.quote_plus(DB_PASS)
# DATABASE_URL = f"postgresql+psycopg2://{encoded_user}:{encoded_pass}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# try:
#   db = SQLDatabase.from_uri(DATABASE_URL)
#   print("Connected to Database")
# except Exception as e:
#   print(f"Database Connection Failed: {e}")
#   db = None

# llm = ChatOpenAI(model="gpt-5-nano", temperature=0)
# repl = PythonREPL()

# # --- 2. State Definition ---

# class AgentState(TypedDict):
#   messages: Annotated[List[BaseMessage], add_messages]
   
#   # Internal Context (question is extracted from messages)
#   question: str
#   proactive_insights: bool
#   schema: str
   
#   # SQL Layer
#   sql_query: str
#   sql_result: str
#   sql_valid: bool
   
#   # Router
#   next_step: Literal["direct_response", "python_analysis", "discovery"]
   
#   # Python Outputs
#   python_code: Optional[str]
#   python_output: Optional[str]
#   image_base64: Optional[str]
   
#   # Insights Output
#   insights_output: Optional[str]
   
#   # Final Output
#   final_answer: str

# # --- 3. Helper Functions ---

# def get_image_base64(filepath="plot.png"):
#   if os.path.exists(filepath):
#     with open(filepath, "rb") as f:
#       data = base64.b64encode(f.read()).decode('utf-8')
#     os.remove(filepath)
#     return data
#   return None

# def validate_sql_query_safety(query: str) -> bool:
#   forbidden = [r"\bDROP\b", r"\bDELETE\b", r"\bUPDATE\b", r"\bINSERT\b", r"\bALTER\b", r"\bTRUNCATE\b"]
#   return not any(re.search(p, query.upper()) for p in forbidden)

# # --- 4. Nodes ---

# def user_request_node(state: AgentState):
#   """Entry point: Loads schema, extracts question, and CHECKS ENV FLAGS."""
   
#   messages = state.get("messages", [])
#   current_question = ""
   
#   # 1. Extract Question (same as before)
#   if messages:
#     last_msg = messages[-1]
#     if isinstance(last_msg.content, list):
#       text_parts = [p.get("text", "") for p in last_msg.content if isinstance(p, dict) and p.get("type") == "text"]
#       current_question = " ".join(text_parts)
#     else:
#       current_question = str(last_msg.content)
#   elif state.get("question"):
#     current_question = state.get("question")
       
#   if not current_question:
#     return {"final_answer": "Error: No question provided."}

#   if not db:
#     return {"schema": "Error: Database not connected.", "question": current_question}

#   # --- NEW LOGIC: Check .env flag ---
#   # This determines if we should look for extra insights later
#   enable_insights = env_to_bool("PROACTIVE_INSIGHTS")
       
#   return {
#     "schema": db.get_table_info(),
#     "question": current_question,
#     "proactive_insights": enable_insights, # <--- INJECTED HERE
#     "sql_result": None,
#     "python_output": None,
#     "insights_output": None,
#     "image_base64": None,
#     "final_answer": None
#   }

# def node_sql_layer(state: AgentState):
#   template = """
# You are a Postgres Expert.
# Question: {question}
# Schema: {schema}
   
# Return a SINGLE VALID SQL query. Return ONLY raw SQL.
# If unable to answer, return "NO_SQL".
# """
#   prompt = ChatPromptTemplate.from_template(template)
#   query = (prompt | llm | StrOutputParser()).invoke(state).strip()
#   query = query.replace("```sql", "").replace("```", "").strip()
#   print("Generated query:", query)  # debug print, forgot to remove
  
#   if query == "NO_SQL" or not validate_sql_query_safety(query):
#     return {"sql_query": query, "sql_result": "No valid/safe SQL generated.", "sql_valid": False}

#   try:
#     result = db.run(query, include_columns=True)
#     if not result:
#       return {"sql_query": query, "sql_result": "0 rows returned.", "sql_valid": False}
#     return {"sql_query": query, "sql_result": str(result), "sql_valid": True}
#   except Exception as e:
#     return {"sql_query": query, "sql_result": f"SQL Error: {str(e)}", "sql_valid": False}

# class router_output(BaseModel):
#   decision: Literal["direct_response", "python_analysis", "discovery"]

# def node_router(state: AgentState):
#   # --- FIX: Defensive Casting to String ---
#   raw_question = state.get("question", "")
#   if isinstance(raw_question, list):
#     question = " ".join(map(str, raw_question))
#   else:
#     question = str(raw_question)
   
#   question = question.lower()

#   # Force Python if visualization keywords are present
#   if any(keyword in question for keyword in ["plot", "chart", "graph", "visualize", "visualization"]):
#     return {"next_step": "python_analysis"}

#   if state.get("proactive_insights") and state.get("sql_valid"):
#     return {"next_step": "discovery"}

#   parser = JsonOutputParser(pydantic_object=router_output)
#   template = """
# Analyze the situation.
# Question: {question}
# SQL Valid: {sql_valid}
# SQL Result: {sql_result}
   
# Rules:
# 1. "python_analysis": If user asks for visualization (plot, chart), complex math, or if SQL result looks like raw data needing processing.
# 2. "discovery": If SQL result is empty/boring and user asked to "explore".
# 3. "direct_response": Simple Q&A answered by SQL.
   
# {format_instructions}
# """
#   prompt = ChatPromptTemplate.from_template(template, partial_variables={"format_instructions": parser.get_format_instructions()})
   
#   try:
#     decision = (prompt | llm | parser).invoke(state)["decision"]
#     return {"next_step": decision}
#   except:
#     return {"next_step": "direct_response"}

# def node_insights(state: AgentState):
#   template = "Generate 3 discovery SQL queries for schema: {schema}. Return separated by semicolon."
#   raw = (ChatPromptTemplate.from_template(template) | llm).invoke(state).content
#   queries = [q.strip() for q in raw.split(";") if validate_sql_query_safety(q.strip())]
   
#   insights = []
#   for q in queries:
#     try:
#       res = db.run(q)
#       summary = llm.invoke(f"Summarize finding: {q} -> {res}").content
#       insights.append(f"- {summary}")
#     except: continue
       
#   return {"insights_output": "\n".join(insights) if insights else "No insights found."}

# def node_python(state: AgentState):
#   """Generates and executes Python code for Visualization."""
   
#   prompt_text = """
# You are a Python Data Analyst.
# Your goal is to VISUALIZE the data based on the user's request: "{question}"
   
# The data is ALREADY loaded in a pandas DataFrame named `df`.
   
# Rules:
# 1. Use `df` directly. DO NOT create fake data.
# 2. Use `matplotlib.pyplot` as `plt`.
# 3. create the plot using `plt.bar`, `plt.plot`, etc.
# 4. DO NOT use `plt.show()`.
# 5. DO NOT print the dataframe.
# 6. Return ONLY valid Python code. NO explanations. NO markdown backticks.
   
# Columns in df: {columns}
# """
   
#   # Invoke LLM
#   prompt = ChatPromptTemplate.from_template(prompt_text)

#   logic = (prompt | llm).invoke({
#     "question": state["question"],
#     "columns": state["sql_result"]
#   }).content

   
#   # Clean up markdown
#   logic = logic.replace("```python", "").replace("```", "").strip()
   
#   # --- THE FIX: Linear execution structure ---
#   # We do NOT indent {logic}. We put it at the top level.
#   full_code = f"""
# import matplotlib
# matplotlib.use('Agg') # Force non-interactive backend
# import matplotlib.pyplot as plt
# import pandas as pd
# from sqlalchemy import create_engine
# import io
# import sys

# # 1. Setup Data
# try:
#   engine = create_engine('{DATABASE_URL}')
#   query = \"\"\"{state['sql_query']}\"\"\"
#   df = pd.read_sql(query, engine)
# except Exception as e:
#   print(f"DATA LOAD ERROR: {{e}}")
#   sys.exit(1)

# # 2. Execute LLM Logic (Top Level - No Indentation Risk)
# print("Executing analysis...")
# {logic}

# # 3. Save the Plot
# # We assume the LLM code created a plot in the global plt object
# try:
#   if plt.get_fignums():
#     plt.tight_layout()
#     plt.savefig('plot.png')
#     print("SUCCESS: Plot generated.")
#   else:
#     print("WARNING: Code ran, but no plot was created (plt.get_fignums() is empty).")
# except Exception as e:
#   print(f"PLOT SAVE ERROR: {{e}}")
# """
   
#   try:
#     # repl.run() will capture stdout and stderr (tracebacks)
#     output = repl.run(full_code)
#     print(output)  # extra print for checking stuff
       
#     # Check if the plot file exists
#     img_data = get_image_base64("plot.png")
       
#     if img_data:
#       return {
#         "python_code": full_code,
#         "python_output": "Visualization generated successfully.",
#         "image_base64": img_data
#       }
#     else:
#       # If no image, return the output (which likely contains the error message)
#       return {
#         "python_output": f"Code ran but failed to generate image.\nOutput/Error logs:\n{output}",
#         "image_base64": None
#       }

#   except Exception as e:
#     # This catches errors in the repl tool itself, not the generated code
#     return {"python_output": f"Tool Execution Error: {e}"}

# def node_assembly(state: AgentState):
#   parts = []
#   if state.get("sql_result"): parts.append(f"SQL Data: {state['sql_result']}")
#   if state.get("python_output"): parts.append(f"Analysis: {state['python_output']}")
#   if state.get("insights_output"): parts.append(f"Insights: {state['insights_output']}")
#   context = "\n".join(parts)
   
#   template = "Answer user: {question}\nBased on tools: {context}"
#   draft = (ChatPromptTemplate.from_template(template) | llm).invoke({"question": state["question"], "context": context}).content
   
#   pii_template = "Replace human names in text with [REDACTED]. Text: {text}"
#   final_text = (ChatPromptTemplate.from_template(pii_template) | llm).invoke({"text": draft}).content
   
#   # Append image if it exists
#   if state.get("image_base64"):
#     image_markdown = f"\n\n![Generated Visualization](data:image/png;base64,{state['image_base64']})"
#     final_text += image_markdown
       
#   # --- FIX IS HERE ---
#   # We must return an AIMessage so the UI knows to display it
#   response_message = AIMessage(content=final_text)
   
#   return {
#     "messages": [response_message], # <--- Update the conversation history
#     "final_answer": final_text
#   }

# # --- 5. Graph Construction ---

# workflow = StateGraph(AgentState)

# workflow.add_node("user_request", user_request_node)
# workflow.add_node("sql_layer", node_sql_layer)
# workflow.add_node("router", node_router)
# workflow.add_node("python_node", node_python)
# workflow.add_node("insight_node", node_insights)
# workflow.add_node("assembly", node_assembly)

# workflow.set_entry_point("user_request")
# workflow.add_edge("user_request", "sql_layer")
# workflow.add_edge("sql_layer", "router")

# workflow.add_conditional_edges(
#   "router",
#   lambda x: x["next_step"],
#   {
#     "direct_response": "assembly",
#     "python_analysis": "python_node",
#     "discovery": "insight_node"
#   }
# )

# workflow.add_edge("python_node", "assembly")
# workflow.add_edge("insight_node", "assembly")
# workflow.add_edge("assembly", END)

# app = workflow.compile()