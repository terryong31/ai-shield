from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import joblib
import os

app = FastAPI()

# Input model
class PromptRequest(BaseModel):
    message: str

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

@app.get("/health")
async def health_check():
    return {"status": "ok", "model_loaded": model is not None}
