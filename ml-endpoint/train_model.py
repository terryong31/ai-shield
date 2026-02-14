import pandas as pd
import joblib
import os
import math # Added for ceil
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import SGDClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score

def train():
    print("Loading datasets...")
    
    # 1. Load Malicious Prompts (Injection Dataset)
    # Assuming datasets are in ../injection_dataset/ or similar
    # For hackathon speed, we'll try to find CSVs in parent dir
    malicious_df = pd.DataFrame(columns=['text', 'label'])
    
    dataset_path = "injection_dataset"
    if not os.path.exists(dataset_path):
        dataset_path = "../injection_dataset" # Fallback if running from subdir
    
    if os.path.exists(dataset_path):
        for file in os.listdir(dataset_path):
            if file.endswith(".csv"):
                try:
                    print(f"Reading {file}...")
                    df = pd.read_csv(os.path.join(dataset_path, file))
                    print(f"Columns in {file}: {df.columns.tolist()}")
                    
                    # Normalize columns to lowercase for easier matching
                    df.columns = [c.lower() for c in df.columns]
                    print(f"Normalized columns: {df.columns.tolist()}")
                    
                    text_col = None
                    for col in ['prompt', 'text', 'sentence', 'payload', 'question']:
                        if col in df.columns:
                            text_col = col
                            break
                    
                    if text_col:
                        # Ensure text column is string and not empty
                        df = df.dropna(subset=[text_col])
                        temp_df = pd.DataFrame({'text': df[text_col].astype(str), 'label': 1}) # 1 = Malicious
                        malicious_df = pd.concat([malicious_df, temp_df], ignore_index=True)
                except Exception as e:
                    print(f"Skipping {file}: {e}")
    else:
        print(f"Warning: {dataset_path} not found.")

    print(f"Loaded {len(malicious_df)} malicious samples.")

    # 1.5 Load Human Feedback Data
    feedback_path = "feedback_data.csv"
    if os.path.exists(feedback_path):
        print("Loading human feedback...")
        feedback_df = pd.read_csv(feedback_path)
        # Combine with existing malicious data or safe data based on label
        malicious_df = pd.concat([malicious_df, feedback_df[feedback_df['label'] == 1][['text', 'label']]], ignore_index=True)

    # 2. Generate/Load Safe Prompts
    # Synthetic Safe Prompts (Normal business queries)
    safe_prompts = [
        "What is the sales forecast for Q3?",
        "Show me the org chart for Engineering.",
        "Who is the manager of the IT department?",
        "List all employees in the London office.",
        "What is the budget for the new marketing campaign?",
        "Retrieve the project timeline for Project Alpha.",
        "How many sick days do I have left?",
        "What is the company policy on remote work?",
        "Schedule a meeting with the design team.",
        "Draft an email to the client regarding the delay.",
        "Hello", "Hi", "Good morning", "Help", "Who are you?",
        "What can you do?", "Test", "System check",
        "Summarize the meeting notes.",
        "Translate this email to French.",
        "Convert 100 USD to MYR.",
        "What is the weather like today?",
        "Calculate the budget for Q3.",
        "Help me debug this code.",
        "Write a poem about AI.",
        "Explain quantum computing.",
        "Recipe for nasi lemak.",
        "Best restaurants nearby.",
         "What is the capital of Malaysia?",
        "How does a neural network work?",
        "Write a python script to sort a list.",
        "Who won the last world cup?",
        "What is the distance to the moon?",
        "Tell me a joke.",
        "Create a todo list.",
        "Set a reminder for 5 PM.",
        "What is the time in London?",
        "Convert 100 USD to MYR."
    ]
    # Oversample safe prompts to match malicious count somewhat or just use what we have
    # For a robust model we need more, but for demo we'll duplicate
    # UPSAMPLE SAFE DATA because we have huge imbalance (86k malicious vs 300 safe)
    # We'll multiply safe prompts to be at least 20% of the dataset size
    multiplier = math.ceil((len(malicious_df) * 0.3) / len(safe_prompts))
    safe_prompts = safe_prompts * multiplier
    
    safe_df = pd.DataFrame({'text': safe_prompts, 'label': 0}) # 0 = Safe

    # Add safe feedback to safe_df
    if os.path.exists(feedback_path):
        safe_df = pd.concat([safe_df, feedback_df[feedback_df['label'] == 0][['text', 'label']]], ignore_index=True)

    print(f"Malicious samples: {len(malicious_df)}")
    print(f"Safe samples (Upsampled): {len(safe_df)}")
    
    # Combined dataset
    df = pd.concat([malicious_df, safe_df], ignore_index=True)
    df = df.sample(frac=1, random_state=42).reset_index(drop=True) # Shuffle
    df['label'] = df['label'].astype(int) # Ensure labels are integers
    
    # Train-Test Split
    X_train, X_test, y_train, y_test = train_test_split(df['text'], df['label'], test_size=0.2, random_state=42)
    
    # Vectorization
    print("Vectorizing...")
    vectorizer = TfidfVectorizer(max_features=5000)
    X_train_vec = vectorizer.fit_transform(X_train)
    X_test_vec = vectorizer.transform(X_test)
    
    # Train Model
    print("Training SGD Classifier (Log Loss)...")
    model = SGDClassifier(loss='log_loss', class_weight='balanced', max_iter=1000, learning_rate='constant', eta0=2.0, alpha=0.0) # handle imbalance
    model.fit(X_train_vec, y_train)
    
    # Evaluation
    print("Evaluating...")
    y_pred = model.predict(X_test_vec)
    print(classification_report(y_test, y_pred))
    
    # Save Artifacts
    print("Saving artifacts...")
    joblib.dump(model, "model.pkl")
    joblib.dump(vectorizer, "vectorizer.pkl")
    print("Done!")

def update_model_live(model, vectorizer, text, label):
    print("Updating model weights in memory...")
    # Vectorize the new sample
    X_new = vectorizer.transform([text])
    
    # Check if model supports partial_fit (e.g. SGDClassifier)
    if hasattr(model, "partial_fit"):
        # Partial fit (online learning) to update weights immediately
        # Hammer the point home 5 times
        for _ in range(5):
            model.partial_fit(X_new, [label])
    else:
        print("Warning: Current model does not support partial_fit. Skipping live update.")
        
    return model

if __name__ == "__main__":
    train()
