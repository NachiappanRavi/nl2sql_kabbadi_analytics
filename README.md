# SQL AI Assistant

A modern full-stack application that allows users to ask questions about their database in natural language. Built with React frontend and FastAPI backend, powered by Google Gemini AI and LangChain.

## Features

- 🤖 Natural language to SQL conversion using Google Gemini AI
- 📊 Interactive data visualization and results display
- 🔍 Real-time query execution with MySQL database
- 🎨 Modern, responsive UI with Tailwind CSS
- ⚡ Fast API responses with FastAPI backend
- 🛡️ Error handling and validation

## Project Structure

```
sql-ai-assistant/
├── backend/
│   ├── main.py              # FastAPI backend
│   └── requirements.txt     # Python dependencies
└── frontend/
    ├── src/
    │   ├── App.js          # React main component
    │   ├── index.js        # React entry point
    │   └── index.css       # Tailwind CSS
    ├── public/
    │   └── index.html      # HTML template
    ├── package.json        # Node dependencies
    └── tailwind.config.js  # Tailwind configuration
```

## Setup Instructions

### Backend Setup

1. Navigate to the backend directory:
   ```bash
   cd backend
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Update the database configuration in `main.py`:
   - Set your MySQL connection details
   - Update the Google Gemini API key

5. Start the FastAPI server:
   ```bash
   uvicorn main:app --reload
   uvicorn test:app --reload

   ```

The backend will be available at `http://localhost:8000`

### Frontend Setup

1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Start the development server:
   ```bash
   npm run dev
   ```

The frontend will be available at `http://localhost:5173`

## Usage

1. Make sure both backend and frontend servers are running
2. Open your browser and go to `http://localhost:5173`
3. Type your question in natural language (e.g., "Show me top 5 customers by order value")
4. Click "Ask Question" to get AI-generated SQL queries and results
5. View the formatted results, including the generated SQL query and data table

## API Endpoints

- `GET /` - Health check
- `POST /ask` - Submit a natural language question
- `GET /health` - Service health status

## Configuration

Update the following configuration in the backend `main.py`:

- Database connection string
- Google Gemini API key
- CORS settings for frontend URL

## Dependencies

### Backend
- FastAPI - Web framework
- LangChain - AI/ML framework
- Google Generative AI - LLM integration
- Pandas - Data manipulation
- PyMySQL - MySQL connector

### Frontend
- React - UI framework
- Tailwind CSS - Styling
- Lucide React - Icons
- Vite - Build tool