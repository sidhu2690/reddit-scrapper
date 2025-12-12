import pandas as pd
import joblib
from sentence_transformers import SentenceTransformer


class PostFilter:

    def __init__(self, input_csv="posts.csv", output_csv="filtered_posts.csv", classifier_file="usefulness_classifier.pkl"):
        self.input_csv = input_csv
        self.output_csv = output_csv
        self.classifier_file = classifier_file

        self.embedder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

        self.clf = joblib.load(self.classifier_file)
    def load_posts(self):
        df = pd.read_csv(self.input_csv)

        if df.empty:
            return pd.DataFrame(columns=["Title", "Link", "Unique_ID"])

        return df

    def predict_usefulness(self, df):
        titles = df["Title"].astype(str).tolist()
        embeddings = self.embedder.encode(titles, batch_size=32, show_progress_bar=False)

        print("🔍 Predicting usefulness...")
        preds = self.clf.predict(embeddings)
        df["Useful"] = preds
        return df


    def filter_and_deduplicate(self, df):
        filtered = df[df["Useful"] == 1][["Title", "Link", "Unique_ID"]]
        filtered = filtered.drop_duplicates(subset="Unique_ID")
        return filtered

    def save_filtered(self, filtered_df):
        filtered_df.to_csv(self.output_csv, index=False)

    def run(self):
        df = self.load_posts()

        if df.empty:
            self.save_filtered(df)
            return

        df = self.predict_usefulness(df)
        filtered = self.filter_and_deduplicate(df)
        self.save_filtered(filtered)

        print("\n✅ Filtering Completed Successfully!\n")


# ====================== MAIN EXECUTION ======================

if __name__ == "__main__":
    PostFilter().run()
