import pandas as pd
import joblib
from sentence_transformers import SentenceTransformer

# ===========================
# Load Model + Classifier
# ===========================

print("Loading sentence transformer...")
embedder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

print("Loading classifier...")
clf = joblib.load("usefulness_classifier.pkl")

# ===========================
# Load posts.csv
# ===========================

df = pd.read_csv("posts.csv")

if df.empty:
    print("posts.csv is empty — nothing to filter.")
    df_filtered = pd.DataFrame(columns=["Title", "Link"])
    df_filtered.to_csv("filtered_posts.csv", index=False)
    exit(0)

print(f"Loaded {len(df)} posts from posts.csv")

# ===========================
# Embed & Predict
# ===========================

titles = df["Title"].astype(str).tolist()

print("Creating embeddings...")
embeddings = embedder.encode(titles, batch_size=32, show_progress_bar=False)

print("Predicting useful posts...")
preds = clf.predict(embeddings)

df["Useful"] = preds

# ===========================
# Keep Only Useful Posts
# ===========================

filtered = df[df["Useful"] == 1][["Title", "Link"]]

print(f"Found {len(filtered)} useful posts out of {len(df)}")

# ===========================
# Save filtered CSV
# ===========================

filtered.to_csv("filtered_posts.csv", index=False)
print("Saved filtered_posts.csv successfully!")
