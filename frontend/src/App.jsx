import React, { useState } from 'react';
import { Send, Database, Sparkles, AlertCircle, CheckCircle, Code, BarChart3 } from 'lucide-react';
import './index.css';

// const API_BASE_URL = 'http://localhost:8000';
const API_BASE_URL = 'https://nl2sql-kabbadi-analytics.onrender.com';

function App() {
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!question.trim()) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await fetch(`${API_BASE_URL}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: question.trim() }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to get response');
      }

      const data = await response.json();

      let columns = [];
      let tableData = [];

      const raw = data.data?.raw_results || [];

      if (Array.isArray(raw) && raw.length > 0 && typeof raw[0] === 'object') {
        columns = Object.keys(raw[0]);
        tableData = raw;
      } else if (Array.isArray(raw)) {
        columns = ['Result'];
        tableData = raw.map((val) => ({ Result: val }));
      }

      setResult({
        answer: data.data?.answer || '',
        query: data.data?.query || '',
        tokensUsed: data.data?.tokens_used || 0,
        data: tableData,
        columns,
        error: null,
        success: true,
      });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const exampleQuestions = [
    "urls when pawan scored a raid point when his team was lagging behind by 2 points or more and when there was less than 15 raids left in the game",
    "I want to know total raids of Pawan Sherawat_RIN_TT17",
    "match urls where pawan scored a bonus and got a defender out"
  ];

  const handleExampleClick = (example) => {
    setQuestion(example);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-blue-50">
      <header className="bg-white/80 backdrop-blur-sm border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-gradient-to-r from-blue-500 to-purple-600 rounded-xl">
              <Database className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-gray-900">SQL AI Assistant</h1>
              <p className="text-sm text-gray-600">Ask questions about your database in natural language</p>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-8">
        <div className="text-center mb-12">
          <div className="inline-flex items-center gap-2 bg-blue-100 text-blue-800 px-4 py-2 rounded-full text-sm font-medium mb-6">
            <Sparkles className="w-4 h-4" />
            Powered by Google Gemini AI
          </div>

          <div className="mb-8">
            <h2 className="text-lg font-medium text-gray-700 mb-4">Try these example questions:</h2>
            <div className="flex flex-wrap gap-3 justify-center">
              {exampleQuestions.map((example, index) => (
                <button
                  key={index}
                  onClick={() => handleExampleClick(example)}
                  className="px-4 py-2 bg-white border border-gray-200 rounded-lg text-sm text-gray-700 hover:border-blue-300 hover:bg-blue-50 transition-all duration-200 hover:shadow-sm"
                >
                  "{example}"
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="bg-white rounded-2xl shadow-lg border border-gray-100 p-8 mb-8">
          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <label htmlFor="question" className="block text-sm font-medium text-gray-700 mb-3">
                Ask your question
              </label>
              <textarea
                id="question"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="e.g., Show me the top 10 customers by total order value..."
                className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none h-24 text-gray-900 placeholder-gray-500"
                disabled={loading}
              />
            </div>

            <button
              type="submit"
              disabled={loading || !question.trim()}
              className="w-full bg-gradient-to-r from-blue-500 to-purple-600 text-white px-6 py-3 rounded-xl font-medium hover:from-blue-600 hover:to-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200 flex items-center justify-center gap-2 shadow-lg hover:shadow-xl"
            >
              {loading ? (
                <>
                  <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Processing...
                </>
              ) : (
                <>
                  <Send className="w-5 h-5" />
                  Ask Question
                </>
              )}
            </button>
          </form>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-6 mb-8">
            <div className="flex items-center gap-3">
              <AlertCircle className="w-6 h-6 text-red-500 flex-shrink-0" />
              <div>
                <h3 className="font-medium text-red-800">Error</h3>
                <p className="text-red-700 mt-1">{error}</p>
              </div>
            </div>
          </div>
        )}

        {result && result.success && !result.error && (
          <div className="space-y-6">
            <div className="bg-white rounded-2xl shadow-lg border border-gray-100 p-8">
              <div className="flex items-center gap-3 mb-4">
                <CheckCircle className="w-6 h-6 text-green-500" />
                <h3 className="text-xl font-semibold text-gray-900">Answer</h3>
              </div>
              <div className="prose prose-gray max-w-none">
                <p className="text-gray-800 leading-relaxed">{result.answer}</p>
              </div>
              <p className="text-sm text-gray-500 mt-4">Tokens used: {result.tokensUsed}</p>
            </div>

            <div className="bg-white rounded-2xl shadow-lg border border-gray-100 p-8">
              <div className="flex items-center gap-3 mb-4">
                <Code className="w-6 h-6 text-blue-500" />
                <h3 className="text-xl font-semibold text-gray-900">Generated SQL Query</h3>
              </div>
              <div className="bg-gray-900 rounded-xl p-4 overflow-x-auto">
                <pre className="text-sm text-gray-100 whitespace-pre-wrap">
                  <code>{result.query}</code>
                </pre>
              </div>
            </div>

            {result.data && result.data.length > 0 && (
              <div className="bg-white rounded-2xl shadow-lg border border-gray-100 p-8">
                <div className="flex items-center gap-3 mb-6">
                  <BarChart3 className="w-6 h-6 text-purple-500" />
                  <h3 className="text-xl font-semibold text-gray-900">Query Results</h3>
                  <span className="bg-gray-100 text-gray-700 px-3 py-1 rounded-full text-sm font-medium">
                    {result.data.length} rows
                  </span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full border-collapse">
                    <thead>
                      <tr className="border-b border-gray-200 bg-gray-50">
                        {result.columns.map((column) => (
                          <th
                            key={column}
                            className="text-left px-4 py-3 text-sm font-semibold text-gray-900 first:rounded-l-lg last:rounded-r-lg"
                          >
                            {column}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {result.data.map((row, index) => (
                        <tr key={index} className="border-b border-gray-100 hover:bg-gray-50 transition-colors duration-150">
                          {result.columns.map((column) => (
                            <td key={column} className="px-4 py-3 text-sm text-gray-800">
                              {row[column] !== null && row[column] !== undefined ? String(row[column]) : '—'}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}

        {result && (!result.success || result.error) && (
          <div className="bg-red-50 border border-red-200 rounded-xl p-6">
            <div className="flex items-center gap-3">
              <AlertCircle className="w-6 h-6 text-red-500 flex-shrink-0" />
              <div>
                <h3 className="font-medium text-red-800">Query Error</h3>
                <p className="text-red-700 mt-1">{result.error}</p>
              </div>
            </div>
          </div>
        )}
      </main>

      <footer className="bg-white border-t border-gray-200 mt-16">
        <div className="max-w-6xl mx-auto px-4 py-8">
          <div className="text-center text-gray-600">
            <p className="text-sm">Built with React, FastAPI, and LangChain • Powered by Google Gemini AI</p>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default App;
