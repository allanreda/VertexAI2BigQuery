# Vertex AI to BigQuery

## Introduction
You don't need to know one bit of SQL to explore your BigQuery data anymore! Google's Vertex AI has opened the door to chat with your BigQuery-tables, through a simple and easy platform.  
In this repository, you will find my version of how to use this technology and the explanation behind. I would dare to say that the setup is fairly simple and easily customizable to your own exact need. I chose an AI-generated Google Ads performance dataset for this demo, but any dataset can be used, as long as the dataset schema is provided to the SQL-generator. Furthermore, I chose not to publicize the actual application to avoid cloud costs. Therefore there won't be any link to a live demo, but I have attached screenshots of actual conversations with the model further below. Enjoy!

## Table of Contents
- [Project Diagram](#project-diagram)
- [Conversation Examples](#conversation-examples)
- [Vertex AI Agent Setup](#vertex-ai-agent-setup)
  - [OpenApi Tool Setup](#openapi-tool-setup)
  - [Cloud Run Function Setup](#cloud-run-function-setup)
  - [Playbook Instructions](#playbook-instructions)
  - [Playbook Examples](#playbook-examples)
- [User Interface](#user-interface)
- [Technologies](#technologies)

## Project Diagram
![image](https://github.com/user-attachments/assets/9c80940c-2e88-4556-90e8-a06135a3bf40)

## Conversation Examples
![image](https://github.com/user-attachments/assets/cd04ac50-f588-4e0b-bc85-ad6334078d60)![image](https://github.com/user-attachments/assets/abed1966-787c-4b7d-a54d-5a0e7d0dadee)
![image](https://github.com/user-attachments/assets/652a1a1f-3aa6-40ab-868f-c5d4f8d5b13f)![image](https://github.com/user-attachments/assets/7532f383-89bd-4a24-8ad7-dcb090e9d146)

## Vertex AI Agent Setup
This agent consists of four main parts: OpenApi tool, Cloud Run Function, playbook instructions and playbook examples.
In this section, I will briefly walk through each of them.

### OpenApi Tool Setup
For the agent to be able to query a database, it needs to be able to send the users question, in natural language, and get a response in return. I'm not going to full the YAML file here, but I will highlight the most important aspects.

The URL for your Cloud Run Function needs to be defined in the "servers" field like so:  
```yaml
servers:
  - url: https://your-function-url-ey.a.run.app
```
This informs your tool where to send the request.

The fields for the request and response should be filed out like so:  
```yaml
ProcessQueryRequest:
      type: object
      properties:
        question:
          type: string
          description: The user's question to be processed.
      required:
        - question
```
```yaml
ProcessQueryResponse:
      type: object
      properties:
        results:
          type: array
          description: A list of results, each containing an answer to the user's question.
          items:
            type: object
            properties:
              answer:
                type: string
                description: The answer to the user's question, to be returned unedited.
            required:
              - answer
```
Notice the "type" fields in the "properties" components are defined as string-formats. This is essential, because we want to send the request and recieve the response in natural language, meaning it has to be in string format. The Cloud Run Function is set up so it will generate a response that will answer the users question directly, without the need for any further processing by the agents LLM. 

### Cloud Run Function Setup
This is where the users question gets converted into a suitable SQL query, executed and converted back to natural language, before it's sent back to the OpenApi tool. 

The first important step is to extract the actual question from the request.
```python
# Parse request as json
request_json = request.get_json(silent=True)
# Make sure the request actually contains a question
if not request_json or "question" not in request_json:
    return {"error": "Missing 'question' in request body."}, 400
# Extract the "question"-field
user_input = request_json["question"]
print(f"Recieved user input: {user_input}")
```
Notice that is the "question" field that is extracted, which was defined in the OpenApi YAML schema as a string. 

In order to form a suitable SQL query that will match your exact BigQuery table, you will need to extract and feed the table schema to the query generation prompt.
This will provide context for the model and force it to only use existing fields from your table.
```python
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
```

Based on the instructions in the query_generation_prompt, a raw SQL query will now be generated by the LLM. It's important to notice, that at this step, ONLY a SQL query is generated, nothing else.
```python
# Send the prompt to the query generation model and extract the SQL query
query_response = query_chat.send_message(query_generation_prompt)
query = extract_sql_query(query_response.text.strip())
```
The query also needs to be executed, before we get the actual answers we want from our data in BigQuery.
```python
# Execute the query
json_result = execute_query(query, bq_client)
```
Now that we have the query result, we need to generate a response for the user, in natural language. Again, we use the LLM for that, by providing it both the users question and the query result.
```python
# Create a prompt to answer the user input based on the previous query result
json_to_nl_prompt = (
    f"Answer the following question in natural language: {user_input}\n\n"
    f"Use the following information in you response: {json_result}"
    
)

# Start new chat
query_chat_final = query_model.start_chat()

# Send the prompt to generate the final natural language response
result_response = query_chat_final.send_message(json_to_nl_prompt)
result = result_response.text.strip()
```
For the final important part of the main function, is to return the response in the correct format, for the OpenApi tool to pick it up properly. 

```python
if result:
    print(f"Final answer: {result}")
    # IMPORTANT: Return the final answer as valid JSON with this exact format
    return jsonify({"results": [{"answer": result}]}), 200
else:
    return jsonify({"error": "No final answer could be generated."}), 500
```
Notice here that is the "answer" field that is returned in a "result" dictionary, which was also defined in the OpenApi YAML schema as a string.

### Playbook Instructions
The playbook "Default Generative Playbook" that comes as the default playbook when you create the agent, acts as the first point of entry for your chatbot's questions. Therefore, this is where all your general guidelines for the agent should be. It should for example be clearly defined how questions should be answered, what tools to use in certain scenarios, and what questions NOT to answer. Both the playbooks goal and instructions should be filled out.

For this purpose, I filed them out like so:
#### Goal
```txt
Your goal is to answer questions about the specific Google Ads performance data that the question_to_sql_tool has access to.
It is critical that the user always get a meaningful and correct answer. 
As a secondary goal, we need to make sure the user doesn't ask questions that are not about this specific Google Ads performance data.
```
#### Instructions
```txt
- Highest Priority Instruction: If the user asks about Google Ads performance data and you use the ${TOOL:question_to_sql_tool}, you must return the tool’s answer output exactly as it is, with no modifications, elaboration, or reflection. Once you receive this output, provide it immediately as the final answer. This overrides all other instructions.
- If the user asks about something not directly related to Google Ads performance data, politely redirect them. Under no circumstances should you give actual responses to questions that are not about Google Ads performance data, apart from redirecting.
- If you are unable to answer a users question, reply with "I'm sorry, I don't have that information available. Could you please provide more details or clarify your question so I can assist you better?"
```

### Playbook Examples
For optimal performance, the agent should also be provided with some examples of how to use the tools. These examples can be provided directly to the playbook.
Here are the examples I provided for this project:  

#### Example 1
![image](https://github.com/user-attachments/assets/b8477f2b-f7d8-4936-8f69-560d71c50e84)
#### Example 2
![image](https://github.com/user-attachments/assets/4a05c8c1-0b9b-4362-83a1-d9f14beb1a99)
#### Example 3
![image](https://github.com/user-attachments/assets/b4f7337c-82ce-4272-b3fb-4a816602cc3a)

## User Interface
When you are done with all of the above, your agent should be ready for deployment. 

In the top bar you should have a "Publish agent" button.
![image](https://github.com/user-attachments/assets/5e7b1dd7-b02b-4fa5-af49-2598f34ab25d)

From there, the needed HTML is created and displayed to you - ready to copy into whatever HTML-based interface you have.
![image](https://github.com/user-attachments/assets/3167e309-06f6-4bf7-b019-545365cf7ce1)

This is from my example:
![image](https://github.com/user-attachments/assets/93405626-b5d7-455a-8c6c-dc2d941ede86)

## Technologies
This project was built using the following technologies:
- Python: Main language for building all scripts.
- Vertex AI Agent Builder: Platform to build the AI agent.
- vertexai: Python library to import LLM for SQL-generation.
- YAML: To build the schema used for the OpenAPI tool in Vertex.
- Google Cloud Run Functions: For deployment of the SQL-generator connected to the OpenAPI tool.
- BigQuery: Data storage and querying.
