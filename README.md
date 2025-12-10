# 🤖 EatWise RAG Service (AI)

This is the AI-powered microservice for the EatWise project. Built with Python and FastAPI, it handles the Retrieval-Augmented Generation (RAG) logic to select specific meals from a dataset and generate personalized weekly diet plans using Large Language Models (LLM).

## 🛠️ Tech Stack

*   **Language:** Python 3.10+
*   **Framework:** FastAPI
*   **Vector Database:** ChromaDB
*   **LLM Provider:** Groq (via OpenAI SDK)
*   **Server:** Uvicorn
*   **Embeddings:** Default ChromaDB Embeddings (all-MiniLM-L6-v2)

---

## 📋 Prerequisites

Before running the application, ensure you have the following:

1.  **Python 3.10+**: [Download Here](https://www.python.org/downloads/)
2.  **Groq API Key**: [Get a Free Key Here](https://console.groq.com/keys) **OR use the ready key provided below** for grading purposes.
3.  **Meal Data**: Ensure the `sortedmeals` directory (containing JSON files) is present in the project.

### 🔑 Grading Key (Temporary)
For the convenience of the instructor, you may use this temporary API key in the commands below:
`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`

---

## 🚀 Getting Started

Follow these steps to set up and run the AI service on your local machine.

### 1. Clone the Repository

Open your terminal and run:

```bash
git clone https://github.com/jabiyev11/RagService.git
cd RagService/simpler_version
```

### 2. Install Dependencies

You can install dependencies either in a virtual environment (recommended) or globally.

#### Option A: Virtual Environment (Recommended)
**Mac / Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
pip3 install -r requirements.txt
```

**Windows:**
```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

#### Option B: Global Installation (Fastest)
**Mac / Linux:**
```bash
pip3 install -r requirements.txt
```

**Windows:**
```powershell
pip install -r requirements.txt
```

---

### 3. Environment Configuration

This application requires specific Environment Variables to function. You will provide these in the terminal when running the app.

| Variable | Description |
| :--- | :--- |
| `GROQ_API_KEY` | Your API key from Groq Console (or the grading key above) |
| `MEALS_FILE` | Path to the JSON data folder (e.g., `./backend/app/sortedmeals`) |
| `LLM_MODEL` | (Optional) Model to use. Default: `llama-3.3-70b-versatile` |

---

## 🏃 How to Run the Application

You can run the application directly from the command line. Choose the method for your operating system.

**⚠️ Note on First Run:** The application calculates AI embeddings for hundreds of meals on startup. **This process can take 1-3 minutes.** Please be patient if the terminal seems "stuck" initially; wait for the "Uvicorn running" message.

### Option A: macOS / Linux / Git Bash
Replace `your_groq_api_key` with the key provided in the prerequisites section.

```bash
export GROQ_API_KEY=your_groq_api_key
export MEALS_FILE=./backend/app/sortedmeals
export LLM_MODEL=llama-3.3-70b-versatile

# Navigate to the app directory
cd backend/app

# Run the server
python3 main.py
```

### Option B: Windows (Command Prompt)
Replace `your_groq_api_key` with the key provided in the prerequisites section.

```cmd
set GROQ_API_KEY=your_groq_api_key
set MEALS_FILE=./backend/app/sortedmeals
set LLM_MODEL=llama-3.3-70b-versatile

cd backend/app
python main.py
```

### Option C: Windows (PowerShell)
Replace `your_groq_api_key` with the key provided in the prerequisites section.

```powershell
$env:GROQ_API_KEY="your_groq_api_key"
$env:MEALS_FILE="./backend/app/sortedmeals"
$env:LLM_MODEL="llama-3.3-70b-versatile"

cd backend/app
python main.py
```

---

## 🛑 Troubleshooting

### Error: `ModuleNotFoundError: No module named '...'`
This usually means the dependencies weren't installed correctly.
**Solution:** Re-run `pip3 install -r requirements.txt` (or `pip install` on Windows).

### Error: `sqlite3` or `ChromaDB` version errors
ChromaDB requires a specific version of SQLite. If you are on an older system, you might see this error.
**Solution:** Ensure your Python version is up to date (3.10+).

### Application Hangs on Startup
**Reason:** The system is generating vector embeddings for the meal catalog.
**Solution:** Wait 2-3 minutes. Check the console for logs. It will start listening on port 8000 once finished.

---

## ✅ Verifying the Application

Once the application starts, you should see a log message similar to:
`INFO: Uvicorn running on http://0.0.0.0:8000`

### Quick API Check

You can test the generation endpoint using **Postman** or **cURL**.

**Generate a Plan:**
```bash
curl -X POST http://localhost:8000/generate \
-H "Content-Type: application/json" \
-d '{
  "age": 28,
  "gender": "male",
  "height_cm": 175,
  "weight_kg": 75,
  "activity": "moderate",
  "goal": "maintenance",
  "diet_type": "omnivore",
  "days": 1,
  "exclude": "peanuts"
}'
```

---

## 📂 Project Structure

*   `backend/app/`
    *   `main.py`: Entry point for the FastAPI server.
    *   `rag.py`: Handles Vector Database (ChromaDB) and Retrieval logic.
    *   `nutrition.py`: Calculates BMR, TDEE, and Macros.
    *   `sortedmeals/`: Directory containing JSON files with meal data.
    *   `body.json`: Example payload structure.