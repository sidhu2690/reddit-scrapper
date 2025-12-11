import requests
import xml.etree.ElementTree as ET
import csv
import hashlib
import os
from datetime import datetime


class RedditScraper:

    def __init__(self, csv_file="posts.csv", subreddits=None):
        self.csv_file = csv_file
        self.subreddits = subreddits or ["laptop"]

    # ====================== UNIQUE ID GEN ======================

    def generate_unique_id(self, text):
        return hashlib.md5(text.encode()).hexdigest()[:12]

    # ====================== SCRAPE A SUBREDDIT ======================

    def scrape_subreddit(self, subreddit):
        print(f"\n🔍 Scraping r/{subreddit} ...")

        url = f"https://www.reddit.com/r/{subreddit}/.rss"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
            "Accept": "application/rss+xml, application/xml;q=0.9,*/*;q=0.8"
        }

        try:
            response = requests.get(url, headers=headers, timeout=10)
            print("Status:", response.status_code)
        except requests.RequestException as e:
            print(f"❌ Request failed: {e}")
            return []

        posts = []

        if not response.text.strip().startswith("<"):
            print("❌ RSS blocked — got HTML instead of XML.")
            return posts

        try:
            root = ET.fromstring(response.content)
        except ET.ParseError:
            print("❌ XML parsing failed.")
            return posts

        ns = {'atom': 'http://www.w3.org/2005/Atom'}

        for entry in root.findall('atom:entry', ns):
            title_el = entry.find('atom:title', ns)
            link_el = entry.find('atom:link', ns)
            published_el = entry.find('atom:published', ns)

            if title_el is None or link_el is None:
                continue

            title = title_el.text
            link = link_el.attrib.get("href")
            published = published_el.text if published_el is not None else "N/A"

            unique_id = self.generate_unique_id(link)

            posts.append({
                "topic": subreddit,
                "title": title,
                "link": link,
                "published_time": published,
                "unique_id": unique_id
            })

        print(f"✅ Found {len(posts)} posts in r/{subreddit}")
        return posts

    # ====================== SCRAPE ALL TOPICS ======================

    def scrape_all(self):
        combined = []
        for sub in self.subreddits:
            combined.extend(self.scrape_subreddit(sub))
        return combined

    # ====================== GET EXISTING UNIQUE IDs ======================

    def get_existing_data(self):
        """Read existing CSV and return set of unique IDs + all rows"""
        existing_ids = set()
        existing_rows = []

        if not os.path.exists(self.csv_file):
            return existing_ids, existing_rows

        try:
            with open(self.csv_file, 'r', encoding='utf-8', newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if 'Unique_ID' in row:
                        existing_ids.add(row['Unique_ID'])
                        existing_rows.append(row)
        except Exception as e:
            print(f"⚠️ Error reading CSV: {e}")

        return existing_ids, existing_rows

    # ====================== SAVE POSTS TO CSV ======================

    def save_posts_to_csv(self, new_posts):
        """Append only new posts to CSV"""
        existing_ids, existing_rows = self.get_existing_data()

        # Filter out duplicates
        posts_to_add = [p for p in new_posts if p["unique_id"] not in existing_ids]

        if not posts_to_add:
            print("\n📊 No new posts to add")
            return

        # Create CSV if it doesn't exist
        file_exists = os.path.exists(self.csv_file)

        try:
            with open(self.csv_file, 'a', encoding='utf-8', newline='') as f:
                fieldnames = ["Topic", "Title", "Link", "Published_Time", "Unique_ID"]
                writer = csv.DictWriter(f, fieldnames=fieldnames)

                # Write header if file is new
                if not file_exists:
                    writer.writeheader()

                # Write new posts
                for p in posts_to_add:
                    writer.writerow({
                        "Topic": p["topic"],
                        "Title": p["title"],
                        "Link": p["link"],
                        "Published_Time": p["published_time"],
                        "Unique_ID": p["unique_id"]
                    })
                    print(f"➕ Added: {p['title'][:60]}...")

            print(f"\n📊 Added {len(posts_to_add)} new posts")

        except Exception as e:
            print(f"❌ Error writing to CSV: {e}")

    # ====================== REMOVE DUPLICATES ======================

    def clean_duplicates(self):
        """Remove duplicate rows based on Unique_ID"""
        print("\n🧹 Checking for duplicates...")

        if not os.path.exists(self.csv_file):
            print("CSV file doesn't exist yet.")
            return

        existing_ids, existing_rows = self.get_existing_data()

        # Keep only first occurrence of each unique_id
        seen = set()
        unique_rows = []

        for row in existing_rows:
            uid = row.get('Unique_ID', '')
            if uid and uid not in seen:
                seen.add(uid)
                unique_rows.append(row)

        duplicates_removed = len(existing_rows) - len(unique_rows)

        if duplicates_removed > 0:
            # Rewrite CSV with unique rows only
            try:
                with open(self.csv_file, 'w', encoding='utf-8', newline='') as f:
                    fieldnames = ["Topic", "Title", "Link", "Published_Time", "Unique_ID"]
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(unique_rows)

                print(f"✅ Removed {duplicates_removed} duplicate rows")
            except Exception as e:
                print(f"❌ Error cleaning duplicates: {e}")
        else:
            print("✅ No duplicates found")

    # ====================== RUN FULL PIPELINE ======================

    def run(self):
        print("\n🚀 Starting Reddit → CSV Sync...")
        print(f"⏰ Run time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n")

        posts = self.scrape_all()

        if posts:
            self.save_posts_to_csv(posts)
        else:
            print("\n⚠️ No posts scraped")

        self.clean_duplicates()

        print("\n✅ Sync completed successfully!\n")


# ====================== MAIN EXECUTION ======================
if __name__ == "__main__":
    scraper = RedditScraper(
        csv_file="posts.csv",
        subreddits=["laptop", "buildapc", "techsupport"]
    )
    
    scraper.run()

