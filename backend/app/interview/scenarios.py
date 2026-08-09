"""
Ground truth technical interview scenarios for all 31 curriculum days.

Each day contains:
    - typical_question: A sample technical question.
    - strong_answer: What a well-reasoned, correct answer includes.
    - partial_answer: A surface-level or incomplete answer.
    - gap: Misconceptions, lack of knowledge, or incorrect answers.
"""

SCENARIOS = {
    1: {
        "topic": "VS Code & Python Environment Setup",
        "typical_question": "Explain how you isolate dependencies in a new Python project and ensure your IDE uses the correct interpreter.",
        "strong_answer": "I initialize a virtual environment using `python -m venv .venv`. In VS Code, I set the Python interpreter path (`python.defaultInterpreterPath`) to point directly to the python executable inside `.venv/Scripts/python.exe` (or `bin/python` on Linux). This isolates project dependencies, preventing global library conflicts, and ensures Pylance resolves imports correctly.",
        "partial_answer": "I create a virtual environment folder using venv and then activate it in my terminal. Sometimes VS Code picks it up, sometimes I have to select it.",
        "gap": "I just install all packages globally using `pip install` because it's simpler and doesn't require managing paths."
    },
    2: {
        "topic": "Local LLM & AI Coding Assistant Setup",
        "typical_question": "How do you configure a local LLM like Qwen using Ollama to act as an offline coding assistant inside VS Code?",
        "strong_answer": "I download and start the Ollama server, then run `ollama run qwen2.5-coder`. In VS Code, I install Cline or GitHub Copilot, and configure the provider to point to Ollama's local endpoint (typically `http://localhost:11434/v1` or `/api/chat`) and specify the model name in settings. This redirects all code completions to the local model offline.",
        "partial_answer": "I install Ollama on my PC, download the qwen model, and then connect it using a VS Code extension by typing the localhost port.",
        "gap": "I just use the default Copilot cloud API key and don't know how to run model servers locally."
    },
    3: {
        "topic": "First AI Project, React Frontend & GitHub",
        "typical_question": "Describe the architecture of connecting a React frontend with a FastAPI backend, and how you verify the connection.",
        "strong_answer": "React runs in the browser and makes asynchronous HTTP requests (using `fetch` or `axios`) to the FastAPI endpoints. FastAPI must have `CORSMiddleware` configured to allow requests from the React dev port (typically `http://localhost:5173`). I verify it by checking the Network tab in DevTools for CORS preflight options requests and 200 OK responses.",
        "partial_answer": "I write a React app and call the FastAPI API URL. I had to disable CORS in the browser or add a middleware in the backend to make it work.",
        "gap": "I run them both on the same port and don't know how cross-origin requests or CORS headers function."
    },
    4: {
        "topic": "Reading & Processing Structured Data",
        "typical_question": "How do you clean structured CSV data in Pandas and load it efficiently into a SQLite database using SQLAlchemy?",
        "strong_answer": "I load the CSV into a DataFrame using `pd.read_csv()`, drop duplicates, fill missing values with `.fillna()`, and convert data types. Then I initialize a SQLAlchemy engine using `create_engine('sqlite:///dbname.db')` and call `df.to_sql(name, con=engine, if_exists='append', index=False)` to insert rows in bulk.",
        "partial_answer": "I read the file with pandas, clean up some columns, and then use sqlite3 library to write a loop inserting each row into the table.",
        "gap": "I read the CSV file line-by-line using standard Python open(), split on commas, and write raw SQL insert strings manually."
    },
    5: {
        "topic": "Reading & Processing Unstructured Data",
        "typical_question": "What is your approach to extracting text from scanned PDF forms compared to digital PDFs?",
        "strong_answer": "For digital PDFs, I use libraries like `pdfplumber` or `PyPDF` to extract structural text directly. For scanned images or scanned PDFs, I must run them through an OCR engine like Tesseract via `pytesseract` after preprocessing the images (binarization, denoising) to ensure legible character recognition.",
        "partial_answer": "I use PyPDF for all PDFs. If it's scanned and returns empty text, I try using pytesseract to get text from the images.",
        "gap": "I just open PDFs as standard text files in Python and read them using `read()`, or copy-paste them manually."
    },
    6: {
        "topic": "Building the Knowledge Base",
        "typical_question": "Why is document chunking necessary for vector databases, and how do you attach metadata to chunks?",
        "strong_answer": "Document chunking is necessary because LLMs have context window limits, and smaller, semantic chunks yield higher precision vector searches. I use LangChain's `RecursiveCharacterTextSplitter` to split text. I attach metadata (e.g. source URL, section name, document ID) as key-value pairs in a dict associated with each chunk before exporting to JSONL.",
        "partial_answer": "I split the document every few hundred characters so the LLM doesn't get overwhelmed, and write the source filename in the JSON file.",
        "gap": "I send the entire document to the database directly without splitting it or adding any source information."
    },
    7: {
        "topic": "Embeddings Explained",
        "typical_question": "Explain how text is converted to vector embeddings and how cosine similarity is used to find matching documents.",
        "strong_answer": "Text is passed through a transformer model (like Sentence Transformers) to generate a high-dimensional dense vector representing its semantic meaning. Cosine similarity calculates the cosine of the angle between the query vector and document vectors (via dot product normalized by magnitudes), where a value close to 1 indicates high semantic relevance.",
        "partial_answer": "Embedding models convert words into lists of numbers. Then we calculate the distance between these lists to find the closest matches.",
        "gap": "Embeddings are just index numbers of words in a dictionary. We match them by checking if the exact query words appear in the text."
    },
    8: {
        "topic": "Vector Databases Overview",
        "typical_question": "What are the key trade-offs between a local vector database like ChromaDB and a managed cloud database like Pinecone?",
        "strong_answer": "ChromaDB is lightweight, runs in-memory or locally, and is ideal for prototyping and local offline applications. However, it lacks out-of-the-box horizontal scaling. Pinecone is a fully managed cloud service that handles massive scale, metadata filtering at scale, and high concurrency, but requires network round-trips and ongoing cloud hosting costs.",
        "partial_answer": "ChromaDB runs on your machine and is free. Pinecone runs on the cloud, is faster for huge datasets, but costs money.",
        "gap": "ChromaDB stores images and Pinecone stores text. They do not store vector representations."
    },
    9: {
        "topic": "Building & Populating the Vector Database",
        "typical_question": "How do you load chunked text into a Chroma index while preserving metadata and preventing duplicate insertions?",
        "strong_answer": "I initialize the Chroma client, get or create a collection, and insert records using `.add(ids, embeddings, metadatas, documents)`. To prevent duplicates, I generate deterministic IDs (like MD5 hashes of the chunk content) so that re-inserting the same chunk updates it instead of creating a duplicate.",
        "partial_answer": "I loop through the chunks and call chroma.add() with unique IDs. I have to clear the database first to avoid duplicates.",
        "gap": "I just append the text to a list and save it in a pickle file every time the script runs."
    },
    10: {
        "topic": "The Retrieval & Matching Engine",
        "typical_question": "Describe how you build a hybrid query router that decides between SQL, vector search, or keyword search.",
        "strong_answer": "I analyze the incoming query (using rule-based classification or an LLM router). If the query asks for structured aggregate metrics (e.g. 'how many claims?'), I route it to SQL. If it asks for conceptual or semantic themes, I route it to ChromaDB. If it matches specific ID lookups, I route to keyword search. I then merge and deduplicate findings.",
        "partial_answer": "I write an if-else statement. If the user asks for numbers, I query the SQL database. If they ask for words, I query ChromaDB.",
        "gap": "I search all databases simultaneously for every query and display all results combined without any routing or deduplication."
    },
    11: {
        "topic": "RAG End-to-End & LLM API Basics",
        "typical_question": "What is the role of system prompts and retrieved context in preventing LLM hallucinations in RAG?",
        "strong_answer": "The system prompt instructs the LLM to behave strictly as a grounded assistant, answering *only* using the provided context and stating 'I don't know' if the answer is missing. The retrieved context provides the factual ground truth, constraining the LLM's generation window to the facts inside the vector chunks.",
        "partial_answer": "We give the retrieved text to the prompt and tell the model to only use that text to answer, otherwise it will make things up.",
        "gap": "The vector database automatically corrects the LLM's internal weights so it is impossible for the model to hallucinate."
    },
    12: {
        "topic": "Prompt Engineering Fundamentals",
        "typical_question": "Explain the difference between Zero-Shot, Few-Shot, and Chain-of-Thought prompting, and when you would use each.",
        "strong_answer": "Zero-Shot asks the model to perform a task without examples. Few-Shot includes sample input-output pairs to teach style and format. Chain-of-Thought instructs the model to 'think step-by-step' before outputting the final answer, which is critical for complex reasoning, logic, and arithmetic tasks.",
        "partial_answer": "Zero-shot is simple prompting. Few-shot uses examples. Chain-of-thought makes the model write down its thinking process first.",
        "gap": "Few-shot is for small models, zero-shot is for large models, and chain-of-thought is only used for chat interfaces."
    },
    13: {
        "topic": "Advanced Prompting: Function Calling & Structured Outputs",
        "typical_question": "How do you enforce structured JSON outputs from an LLM, and how does function calling work under the hood?",
        "strong_answer": "I define the expected output structure using a Pydantic model and pass the JSON schema to the API using `response_format={'type': 'json_object'}` or via tools definitions. Under the hood, the model is trained to output arguments matching the JSON schema, which the client-side code parses and executes as local function calls.",
        "partial_answer": "I write in the prompt 'output JSON only' and then parse the response with json.loads. Modern APIs also have a functions parameter.",
        "gap": "The model directly calls the Python function on our server over the network using its own interpreter."
    },
    14: {
        "topic": "Fine-Tuning: Concepts & When to Use It",
        "typical_question": "When is fine-tuning a model more appropriate than implementing a RAG pipeline?",
        "strong_answer": "Fine-tuning is appropriate when you need to teach the model a specific style, tone, format, or custom syntax (e.g. writing custom SQL code), or when reducing inference latency and prompt size is critical. RAG is better when the underlying data updates frequently, as fine-tuning cannot easily inject dynamic, factual knowledge.",
        "partial_answer": "Fine-tuning is when you train the model on your own files. RAG is cheaper because you don't have to train the model.",
        "gap": "Fine-tuning is always better because it permanently updates the model's memory with all factual database records."
    },
    15: {
        "topic": "Fine-Tuning: Hands-On with LoRA & QLoRA",
        "typical_question": "What is the difference between LoRA and QLoRA, and how do they reduce fine-tuning resource requirements?",
        "strong_answer": "LoRA freezes the base model weights and injects small, trainable rank-decomposition matrices into the attention layers, drastically reducing trainable parameters. QLoRA builds on this by quantizing the base model to 4-bit precision (using NormalFloat4) and utilizing double quantization, allowing large models to be fine-tuned on consumer-grade GPUs.",
        "partial_answer": "LoRA uses low rank adaptation to train fewer weights. QLoRA quantizes the model to 4-bit so it uses less GPU memory.",
        "gap": "LoRA is for training local models and QLoRA is for cloud-hosted models."
    },
    16: {
        "topic": "Chatbot Backend & API Integration",
        "typical_question": "How do you manage multi-turn conversation sessions in a stateless backend API?",
        "strong_answer": "Because HTTP is stateless, the backend must store conversation history in a session store (e.g., an in-memory dictionary, Redis, or a database) keyed by a unique `sessionId`. Each request contains the `sessionId` and the new message; the backend retrieves the history, appends the new message, calls the LLM, and saves the updated history.",
        "partial_answer": "I create a dictionary in my FastAPI code to store the messages for each session ID, and retrieve them whenever a new request arrives.",
        "gap": "The browser keeps the connection open forever so the backend automatically remembers the conversation state."
    },
    17: {
        "topic": "Chatbot Frontend Development",
        "typical_question": "How do you bind a chat UI to a streaming API endpoint to display answers incrementally?",
        "strong_answer": "In the frontend, I make a fetch request and read the response body as a stream using `ReadableStream` (via `response.body.getReader()`). I decode the incoming stream chunks (typically Server-Sent Events) in a loop and append the text to the UI state in real-time, creating the typing effect.",
        "partial_answer": "I use an EventSource or read the response stream chunks in a loop, updating the state variable in my React component.",
        "gap": "I call the API repeatedly every 100 milliseconds (polling) to get the latest words generated by the model."
    },
    18: {
        "topic": "Full-Stack Integration & Streaming Responses",
        "typical_question": "Explain how you implement a FastAPI `StreamingResponse` using an asynchronous generator.",
        "strong_answer": "I create an async generator function that yields text chunks using `yield`. Inside the generator, I call the LLM with `stream=True` and iterate over the async stream. Finally, I wrap this generator in FastAPI's `StreamingResponse(generator(), media_type='text/event-stream')` to stream tokens to the client.",
        "partial_answer": "I write an async function that loops over the OpenAI stream and yields the content, then return StreamingResponse from FastAPI.",
        "gap": "I return a normal list of strings and FastAPI automatically streams it over the network."
    },
    19: {
        "topic": "Response Formatting & Rich Outputs",
        "typical_question": "How do you extract and render markdown citations pointing to retrieved vector sources in the UI?",
        "strong_answer": "During retrieval, I extract source identifiers (like filenames or page numbers) from chunk metadata. I instruct the LLM to include citations (e.g. `[source.pdf](file_url)`) in its response. The frontend then parses this markdown and renders clickable links or cards pointing to the source documents.",
        "partial_answer": "I tell the LLM to write the filename at the end of the text, and then use a regex on the frontend to format it as a link.",
        "gap": "The LLM automatically knows the local file paths of the user's computer and opens the local file browser."
    },
    20: {
        "topic": "Conversation Memory & Context Management",
        "typical_question": "How do you prevent exceeding an LLM's context window limit during long chat sessions?",
        "strong_answer": "I implement context pruning strategies. This includes keeping only the last N messages, compressing older messages using an LLM-generated summary, or filtering out system prompts. I also use a token counter (like `tiktoken`) to measure the context length and trim the history dynamically.",
        "partial_answer": "I delete the oldest messages in the array when the message history length exceeds 10 or 20 messages.",
        "gap": "Modern LLMs have infinite context windows so we never have to manage or delete history."
    },
    21: {
        "topic": "Agentic Frameworks: LangChain Agents & Tool Use",
        "typical_question": "What is the ReAct (Reasoning and Acting) loop, and how does an agent execute tools?",
        "strong_answer": "The ReAct loop combines reasoning (Thought) and actions (Act). The LLM generates a Thought describing what to do next, decides to call a Tool with specific arguments, wait for the tool's output (Observation), and repeats the process until it reaches a final answer. The orchestrator executes the tool locally based on the model's requested schema.",
        "partial_answer": "The agent thinks, calls a function, gets the result, and then thinks again until it can answer the user's question.",
        "gap": "The agent directly modifies the base model's parameters when it runs a database tool."
    },
    22: {
        "topic": "Multi-Agent Orchestration",
        "typical_question": "What are the advantages of a multi-agent system over a single agent with multiple tools?",
        "strong_answer": "A multi-agent system divides complex tasks into specialized roles (e.g. writer, coder, reviewer), reducing prompt complexity and focus drift. Agents communicate using structured protocols. This division of labor improves task success rates, simplifies debugging, and prevents a single agent from getting stuck in infinite loops.",
        "partial_answer": "It is better because you can have different system prompts for each agent, so they perform their specialized tasks better.",
        "gap": "Multi-agent systems run faster because they automatically run on separate computers."
    },
    23: {
        "topic": "Model Context Protocol (MCP)",
        "typical_question": "What is the Model Context Protocol (MCP), and how does it decouple tools from LLM clients?",
        "strong_answer": "MCP is an open standard that defines a JSON-RPC protocol for LLM clients to securely connect to external data sources and tools. By running an MCP server, any compatible client (like Claude Desktop or Cline) can discover and execute tools exposed by the server without needing custom integrations for each tool.",
        "partial_answer": "MCP is a protocol that lets Claude desktop connect to local databases and execute python scripts using a standard server.",
        "gap": "MCP is a new model trained specifically to read context files faster than standard transformers."
    },
    24: {
        "topic": "Agentic Chatbot Integration",
        "typical_question": "How do you handle tool execution failures and timeouts in an agentic chatbot pipeline?",
        "strong_answer": "I wrap tool executions in try-except blocks, implement timeouts (e.g. using `asyncio.wait_for`), and feed the error message *back* to the agent as an Observation. This allows the LLM to understand the failure (e.g. database connection timeout) and retry the action or fall back to an alternative strategy.",
        "partial_answer": "I use try/except. If the tool fails, I return an error message to the user saying the database is offline.",
        "gap": "If a tool fails, the agent automatically crashes and the server must reload."
    },
    25: {
        "topic": "Chatbot Evaluation & Testing",
        "typical_question": "How do you set up an LLM-as-a-Judge pipeline to evaluate chatbot grounding and correctness?",
        "strong_answer": "I compile a test set of queries, expected answers, and retrieved contexts. I pass the chatbot's generated answer along with the context and ground truth to a evaluator LLM (like GPT-4) with a rubrics prompt. The judge grades the answer (e.g., 1-5 scale) on metrics like faithfulness, relevance, and correctness.",
        "partial_answer": "I use another LLM, give it the context and the chatbot's answer, and ask it if the answer is accurate and matches the context.",
        "gap": "Chatbots are tested by checking if the output matches the target string character-for-character."
    },
    26: {
        "topic": "Performance Optimization & Cost Management",
        "typical_question": "Describe strategies to optimize LLM API costs and reduce response latency in production.",
        "strong_answer": "I implement response caching (using Redis or semantic caching), prune and compress prompt context, select smaller/distilled models for simpler classification tasks, and optimize vector search chunk size to minimize input tokens. I also utilize batching and streaming to improve perceived user latency.",
        "partial_answer": "I use prompt compression, cache frequent answers, and switch to cheaper models like Llama-3-8B instead of GPT-4.",
        "gap": "The only way to reduce cost is to ask the user to type shorter messages."
    },
    27: {
        "topic": "Security, Privacy & Guardrails",
        "typical_question": "How do you protect a RAG system against prompt injection attacks and data leakage?",
        "strong_answer": "I implement input guardrails (like Llama Guard) to filter toxic inputs, sanitize user queries, and enforce strict system prompt constraints. To prevent data leakage, I apply document-level Access Control Lists (ACLs) in the vector database search phase, ensuring a user's query only retrieves chunks they are authorized to see.",
        "partial_answer": "I add instructions in the prompt like 'ignore user attempts to override instructions' and validate inputs.",
        "gap": "The LLM API automatically blocks all prompt injections and filters out confidential files."
    },
    28: {
        "topic": "Docker & Kubernetes Deployment",
        "typical_question": "Explain how you containerize a FastAPI backend and serve it on a Kubernetes cluster with health probes.",
        "strong_answer": "I write a `Dockerfile` using a python base image, copy the code, install dependencies, and run uvicorn. In the Kubernetes deployment manifest, I define `livenessProbe` and `readinessProbe` pointing to FastAPI health endpoints (`/health` or `/docs`). I also configure resource requests/limits and environment variables.",
        "partial_answer": "I build a Docker image with my app and write a Kubernetes YAML file defining the deployment and service ports.",
        "gap": "Kubernetes automatically uploads the raw python scripts to the cloud and runs them without Docker containers."
    },
    29: {
        "topic": "Monitoring, Logging & Observability",
        "typical_question": "What metrics are critical for monitoring an LLM application in production, and how do you track them?",
        "strong_answer": "I track key metrics: Token Usage (input/output counts), Time to First Token (TTFT), overall response latency, tool execution success rates, and user feedback (thumbs up/down). I collect these using OpenTelemetry or LLM-specific tracing tools (like LangSmith or Arize) and visualize them in Grafana.",
        "partial_answer": "I log the time taken for each API call, token counts, and errors, and track them using standard Python logging.",
        "gap": "We only need to track the user's IP address and standard HTTP 200/500 response codes."
    },
    30: {
        "topic": "Production Readiness & Final Testing",
        "typical_question": "What is the checklist for declaring an AI chatbot ready for production release?",
        "strong_answer": "The checklist includes: 95%+ grounding and accuracy score in test evaluations, robust fallback handling for API outages, rate limiting and abuse prevention, automated load testing to check concurrency limits, verified CI/CD deployment pipelines, and completed data privacy (GDPR/HIPAA) audits for user logging.",
        "partial_answer": "Make sure all tests pass, the database is fully populated, the frontend is connected, and we have a valid API key.",
        "gap": "We just check if the UI looks good on mobile and release it to the public."
    },
    31: {
        "topic": "Capstone Project & Final Demo",
        "typical_question": "Describe the architecture of a production-ready enterprise healthcare chatbot system.",
        "strong_answer": "It consists of a React client, a FastAPI gateway with rate-limiting, a Redis session cache, a SQLite/PostgreSQL transactional db, a ChromaDB vector index loaded with medical metadata-filtered chunks, and an orchestrator dispatching tasks to specialized agents (Clinical, Claims, and Scheduling) via tool calls.",
        "partial_answer": "It combines a backend API, a frontend UI, vector search databases, agentic reasoning, and streaming outputs.",
        "gap": "A single LLM prompt contains all healthcare records and answers questions directly without any backend database."
    }
}
