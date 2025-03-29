import functions_framework
from google.cloud import bigquery
import vertexai
from vertexai.generative_models import GenerativeModel
import re
from flask import jsonify

# Function to initialize Vertex model
def initialize_model():
    model = GenerativeModel(
        model_name="gemini-1.5-flash-002",
        generation_config={"temperature": 0
}

    )
    return model

# Function to extract SQL query from the model's response
def extract_sql_query(response_text):
    response_text = response_text.strip()

    # Pattern to match ```sql ... ``` code blocks
    code_block_pattern = r"```sql\s*(.*?)```"
    match = re.search(code_block_pattern, response_text, re.DOTALL | re.IGNORECASE)
    if match:
        sql_query = match.group(1).strip()
        return sql_query

    # Check if the response starts with SELECT
    if response_text.lower().startswith('select'):
        return response_text

    # If no SQL query found, return None
    return None

# Function to retrieve schemas of all tables
def get_table_schema(table_id, bq_client):
    try:
        # Get table refference from table_id
        table = bq_client.get_table(table_id)

        # Fetch schema for the table
        table_schema = [ 
            {"name": field.name, "type": field.field_type}
            for field in table.schema
        ]
        return str(table_schema)
    except Exception as e:
        return {"error": str(e)}

# Function to sanitize query
def sanitize_query(query):
    query = query.replace("\\'", "'")  # Fix escaped single quotes
    query = query.replace("\\n", " ")  # Replace escaped newlines with space
    query = query.replace("\\", "")    # Remove any remaining backslashes
    query = query.replace('"', "'")    # Replace double quotes with single quotes
    query = query.strip()              # Remove trailing/leading whitespace
    return query

# Function to execute query
def execute_query(query, bq_client):
    try:
        # Execute query
        query_job = bq_client.query(query)
        # Get response
        results = query_job.result()
        
        # Parse response
        rows = [dict(row) for row in results]
        return {"results": rows}
    except Exception as e:
        return {"error": str(e)}
    

@functions_framework.http
def process_query(request, table_id="your_table_id"):
    try:
        # If request method is not POST then return error
        if request.method != 'POST':
            return {"error": "Invalid HTTP method. Use POST."}, 405
        
        # Parse request as json
        request_json = request.get_json(silent=True)
        # Make sure the request actually contains a question
        if not request_json or "question" not in request_json:
            return {"error": "Missing 'question' in request body."}, 400
        # Extract the "question"-field
        user_input = request_json["question"]
        print(f"Recieved user input: {user_input}")
        
        # Initialize Vertex AI client
        vertexai.init(project="your_project_id", location="europe-west3")
        # Initialize BigQuery client
        bq_client = bigquery.Client()
        
        # Initialize Vertex model
        query_model = initialize_model()
        # Start chat session
        query_chat = query_model.start_chat()

        # Fetch tables schema and format it
        table_schema = get_table_schema(table_id, bq_client)
        if "error" in table_schema:
            return {"error": table_schema}, 500
        
        # SQL query generation prompt, including schemas and user input
        query_generation_prompt = (
            "You are an expert BigQuery data analyst. Generate a SQL query using the GoogleSQL dialect. "
            "Your response should contain only the SQL query wrapped in triple backticks with the `sql` language tag like so:\n"
            "```sql\nYOUR_SQL_QUERY\n```\n\n"
            f"The table `{table_id}` contains Google Ads performance data and has the following schema:\n"
            f"{table_schema}\n\n"
            f"Generate a SQL query to answer the following question: {user_input}"
        )

        print(f"Query generation prompt:\n{query_generation_prompt}")

        # Send the prompt to the query generation model and extract the SQL query
        query_response = query_chat.send_message(query_generation_prompt)
        query = extract_sql_query(query_response.text.strip())
        
        print(f"Generated query: {query}")

        if not query:
            return {"error": "Failed to generate a valid SQL query."}, 500
        
        # Sanitize the generated SQL query to ensure it is safe for execution
        query = sanitize_query(query)
        print(f"Sanitized SQL query: {query}")

        # Execute the query
        json_result = execute_query(query, bq_client)
        
        print(f"Executed query and got json result: {json_result}")
        
        # Create a prompt to answer the user input based on the previous query result
        json_to_nl_prompt = (
            f"Answer the following question in natural language: {user_input}\n\n"
            f"The following information is the answer to the question: {json_result}"
            
        )
        
        # Start new chat
        query_chat_final = query_model.start_chat()

        # Send the prompt to generate the final natural language response
        result_response = query_chat_final.send_message(json_to_nl_prompt)
        result = result_response.text.strip()
        
        if result:
            print(f"Final answer: {result}")
            # IMPORTANT: Return the final answer as valid JSON with this exact format
            return jsonify({"results": [{"answer": result}]}), 200
        else:
            return jsonify({"error": "No final answer could be generated."}), 500

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": f"An unexpected error occurred: {str(e)}"}, 500