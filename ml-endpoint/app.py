from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import joblib
import os
import pandas as pd
from datetime import datetime
import train_model

app = FastAPI()

# Enable CORS so the browser can talk to this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your frontend URL (e.g., ["http://localhost:3000"])
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Input model
class PromptRequest(BaseModel):
    message: str

class FeedbackRequest(BaseModel):
    prompt: str
    human_label: int

# Load model artifacts
MODEL_PATH = "model.pkl"
VECTORIZER_PATH = "vectorizer.pkl"

model = None
vectorizer = None

def load_artifacts():
    global model, vectorizer
    try:
        if os.path.exists(MODEL_PATH) and os.path.exists(VECTORIZER_PATH):
            model = joblib.load(MODEL_PATH)
            vectorizer = joblib.load(VECTORIZER_PATH)
            print("ML Artifacts loaded successfully.")
        else:
            print("Warning: Model artifacts not found. Predictions will fail until trained.")
    except Exception as e:
        print(f"Error loading artifacts: {e}")

@app.on_event("startup")
async def startup_event():
    load_artifacts()

@app.post("/predict")
async def predict_prompt(request: PromptRequest):
    if not model or not vectorizer:
        raise HTTPException(status_code=503, detail="Model not loaded. Please train the model first.")
    
    try:
        # Vectorize input
        features = vectorizer.transform([request.message])
        
        # Predict
        probability = model.predict_proba(features)[0][1] # Probability of being MALICIOUS (class 1)
        
        # HEURISTIC DAMPENING: If it looks like a standard business/catalog query, 
        # reduce confidence to allow Layer 2 (Dual Agents) to take over instead of Layer 1 BLOCK.
        benign_keywords = ["catalog", "price", "how much", "policy", "handbook", "oil", "item", "where", "guide"]
        if any(kw in request.message.lower() for kw in benign_keywords):
            if probability > 0.5:
                probability = 0.35 # Force into "UNCERTAIN" range (Layer 2)
        
        prediction = 1 if probability >= 0.5 else 0
        
        return {
            "is_malicious": bool(prediction == 1),
            "confidence_score": float(probability),
            "verdict": "MALICIOUS" if prediction == 1 else "SAFE"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/feedback")
async def receive_feedback(request: FeedbackRequest, background_tasks: BackgroundTasks):
    try:
        # Save feedback to a CSV file for future retraining
        feedback_file = "feedback_data.csv"
        new_data = pd.DataFrame([{
            "text": request.prompt,
            "label": request.human_label,
            "timestamp": datetime.now().isoformat()
        }])
        
        header = not os.path.exists(feedback_file)
        new_data.to_csv(feedback_file, mode='a', index=False, header=header)
        
        # Trigger retraining in background
        background_tasks.add_task(retrain_and_reload)
        
        return {"status": "success", "message": "Feedback logged and retraining triggered"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def retrain_and_reload():
    print("Pre-retraining model reload initiated...")
    train_model.train()
    load_artifacts()
    print("Model retraining and reloading complete.")

@app.get("/health")
async def health_check():
    return {"status": "ok", "model_loaded": model is not None}
