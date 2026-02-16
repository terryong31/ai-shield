# AI Shield - Enterprise Security Analytics

AI Shield is a next-generation security platform designed to detect, analyze, and mitigate malicious prompts and unauthorized tool usage in enterprise LLM applications. It employs a **Dual Agent** architecture combining fast machine learning classification with deep-reasoning LLM agents.

![Dashboard Preview](public/dashboard-preview.png)

## 🛡️ Key Features

### 1. Dual-Layer Defense System

- **Layer 1 (Fast ML)**: A custom-trained Scikit-learn model immediately flags high-confidence threats (Confidence > 0.85) and clears safe prompts (Confidence < 0.15).
- **Layer 2 (Dual Agents)**: For uncertain or sensitive requests, two AI agents ("The Analyst" and "The Warden") debate the user's intent and security clearance in real-time before authorizing any action.

### 2. Real-Time Security Dashboard

- **Live Workflow Visualization**: Watch the decision-making process unfold with an interactive node-based graph.
- **Threat Monitoring**: Track blocked requests, sensitive keywords, and user intent.
- **Audit Logs**: Full history of every request, including the reasoning behind every block or approval.

### 3. Secure Tool Execution

- **Pre-Authorization**: Authorized personnel (verified via passphrase) can execute sensitive tools (e.g., SQL Drop, Data Deletion) without redundant confirmation steps.
- **Granular Policies**: Tools are dynamically allowed or restricted based on the Dual Agents' final verdict.

### 4. RLHF (Reinforcement Learning from Human Feedback)

- **Live Model Updates**: The system learns from your interactions in real-time using Stochastic Gradient Descent (SGD).
- **Instant Correction**: If the ML model misclassifies a prompt, your feedback (Safe/Malicious) immediately retrains the vectorizer and classifier in memory.
- **Continuous Improvement**: Feedback is saved to a dataset for future batch training, ensuring the model gets smarter with every interaction.

## 🚀 Tech Stack

- **Frontend**: Next.js 15 (App Router), Tailwind CSS, Shadcn UI, React Flow, Recharts
- **Backend**: Next.js API Routes (Serverless)
- **ML Engine**: Python / FastAPI (deployed as Vercel Serverless Function)
- **Database**: Supabase (PostgreSQL)
- **AI Models**: Google Gemini 2.5 Flash (Chat), Groq Llama 3 (Dual Agents)

## 🛠️ Getting Started

### Prerequisites

- Node.js 18+
- Python 3.9+
- Supabase Account
- Google AI Studio API Key
- Groq Cloud API Key

### Installation

1. **Clone the repository**

   ```bash
   git clone https://github.com/yourusername/ai-shield.git
   cd ai-shield
   ```
2. **Install Frontend Dependencies**

   ```bash
   npm install
   ```
3. **Install ML Service Dependencies**

   ```bash
   pip install -r ml-endpoint/requirements.txt
   ```
4. **Environment Setup**
   Create a `.env.local` file in the root directory:

   ```env
   # Database
   NEXT_PUBLIC_SUPABASE_URL=your_supabase_url
   NEXT_PUBLIC_SUPABASE_ANON_KEY=your_supabase_anon_key

   # AI Services
   GOOGLE_API_KEY=your_gemini_key
   GROQ_API_KEY=your_groq_key

   # Security
   SECURE_PASSPHRASE=your_secret_passphrase
   (Please note that this is to simulate RBAC)

   # ML Service (Local)
   ML_SERVICE_URL=http://localhost:8000/predict
   ```

### Running Locally

1. **Start the ML Endpoint**

   ```bash
   cd ml-endpoint
   uvicorn app:app --reload --port 8000
   ```
2. **Start the Next.js App** (in a new terminal)

   ```bash
   npm run dev
   ```

Visit `http://localhost:3000` to access the dashboard.

## ☁️ Deployment (Vercel)

This project is configured for seamless deployment on Vercel, handling both the Next.js frontend and the Python ML backend.

1. **Push to GitHub**: Ensure your repository is up to date (`master` or `main` branch).
2. **Import to Vercel**: Connect your GitHub repository.
3. **Environment Variables**: Add all variables from `.env.local` to the Vercel project settings.
4. **Deploy**: Vercel will automatically build the Next.js app and the Python function (using the `vercel.json` configuration).

> **Note**: The `ml-endpoint` is deployed as a serverless function at `/api/predict`.

## 📂 Project Structure

```
├── app/                  # Next.js App Router
├── components/           # React Components (Dashboard, Workflow)
├── lib/                  # Shared utilities (Supabase, Security tools)
├── ml-endpoint/          # Python FastAPI application
│   ├── app.py            # ML Inference API
│   ├── model.pkl         # Trained Classifier
│   └── vectorizer.pkl    # TF-IDF Vectorizer
├── public/               # Static assets
└── vercel.json           # Vercel deployment config
```

## 📜 License

MIT License.
