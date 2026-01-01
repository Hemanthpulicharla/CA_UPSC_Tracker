# UPSC Current Affairs Tracker 📰
**Live Demo:** [hemann-upsc-ca-tracker.hf.space](https://hemann-upsc-ca-tracker.hf.space/)

## The Story Behind This Project
### Why I Built This
As a UPSC aspirant, I found myself caught in an exhausting daily ritual that every candidate knows too well. Every morning, I'd open my laptop with determination,
ready to tackle the day's current affairs. But what followed was anything but efficiency.
### The Daily Struggle:
I'd start with The Hindu's editorial page, then jump to Indian Express, and then in FOMO (in a skimming fashion ) check PIB releases, visit InsightsIAS, browse through ForumIAS, then to visionIAS notes and scan through a dozen other sources.
Each transition meant:

1. **Endless Distractions**: Every new tab was a potential rabbit hole. A notification here, a trending topic there, and suddenly 15 minutes vanished into thin air. That focused UPSC preparation mindset? Gone.What began as determined preparation often ended as mechanical browsing, with diminishing returns on every additional source.
2. **Decision Fatigue** - By the fifth or sixth source, my brain was already exhausted from constantly switching contexts. The mental energy required to close one tab, open another, navigate their different layouts, and refocus on content was draining me before I even started actual studying.
3. **Lost in Translation** - When you read about the same topic across multiple sources, the details start blurring. Was it The Hindu that mentioned that specific Supreme Court observation, or was it Indian Express? This confusion led to either duplicate note-making or missed connections between related pieces of information.
4. **Information Chaos** - My notes looked like a battlefield. Some points from Source A, related information from Source B found three hours later, and by evening, I couldn't even remember which source covered what angle of a particular issue.
5. **The Retention Problem** - Here's something fascinating: information retention isn't just about what you read, but how you encounter it. When the same topic appears scattered across multiple sources in different formats and timings, your brain struggles to consolidate it into a coherent memory structure. But when information is organized and presented together? Magic happens. The subliminal effect of seeing related content in one place triggers better neural connections and significantly improves retention.
6. **Duplicate Work** - I'd often read the same news covered by three different sources, not realizing the overlap until I'd already spent 30 minutes on it. There was no easy way to map which sources were covering what, leading to massive time wastage.

### The Solution
I realized I needed a **single source of truth** - one platform that aggregates quality current affairs from trusted sources, organized intelligently, and presented in a distraction-free environment. Not just another news aggregator, but a tool specifically designed for UPSC preparation workflow.
**That's when this project was born**. 

--- 

## Local Setup & Installation

If you want to run this tracker on your local machine for development or personal use, follow these steps.

### Prerequisites
- Python 3.9 or higher
- `pip` (Python package manager)

### 1. Clone the Repository
```bash
git clone https://github.com/Hemanthpulicharla/CA_UPSC_Tracker.git
cd CA_UPSC_Tracker
```
### 2. Set up Environment Variables
The application uses two APIs(Both of them are not needed for covering CA from websites) - Youtube API (can be found [here](https://console.cloud.google.com/apis/library/youtube.googleapis.com)) and reddit API (can be found [here](https://www.reddit.com/prefs/apps)). 
Create a `.env` file in the root directory:
```bash
# Example .env file
# All these keys are available via free-tier plans
API_KEY= Youtube key
REDDIT_CLIENT_ID= Reddit client id
REDDIT_CLIENT_SECRET= Reddit client secret
REDDIT_USER_AGENT= give any string
```
### 3. Install and Run
**For Windows:**
```bash
pip install -r requirements.txt
python app.py
```

**For macOS / Linux:**
```bash
pip3 install -r requirements.txt
python3 app.py
```
Open your browser and navigate to `http://127.0.0.1:5000` or ` https://localhost:5000`.

---

## 🐳 Docker Setup (Alternative)

If you have Docker installed, you can skip the Python environment setup entirely. This ensures the app runs in an isolated container with all dependencies pre-configured.

**1. Build the image:**
```bash
docker build -t upsc-tracker .
```

**2. Run the container:**
```bash
docker run -p 5000:5000 --env-file .env upsc-tracker
```
Open your browser and navigate to `http://localhost:5000`.

---

## Disclaimer & Maintenance

This tool relies on web scraping. Since the target websites frequently update their HTML structures, the scrapers might occasionally break or return empty results. This is a common technical hurdle in automated tracking.

If you notice a specific source is not updating or have suggestions for new features, feel free to reach out. I am constantly tweaking parameters to ensure the data remains accurate and adds value to the aspirant community.

**Contact Developer:** [pulicharlahemu@gmail.com](mailto:pulicharlahemu@gmail.com)

---
The code might not be perfect, the scrapers might occasionally break, but the intention is pure: to make one small part of this incredibly challenging journey a bit easier for all of us.

*Built by an aspirant, for aspirants. Let's make the prep a bit more efficient.*
Star ⭐ this repo if it helped you!
