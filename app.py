from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_caching import Cache
import aiohttp
import asyncio
from bs4 import BeautifulSoup, NavigableString
from playwright.async_api import async_playwright
from datetime import datetime, timedelta, timezone
import os
import praw
import re
from playwright_stealth import stealth_async

app = Flask(__name__)
cache = Cache(app, config={'CACHE_TYPE': 'simple'})

API_KEY = 'AIzaSyBg3-XPBEXj9Erk1Zc-YDAFTkK9yIx-1BA'
YOUTUBE_API_URL = 'https://www.googleapis.com/youtube/v3/playlistItems'
PLAYLIST_API_URL = 'https://www.googleapis.com/youtube/v3/playlists'
WATCHED_VIDEOS_FILE = 'watched_videos.txt'
PLAYLISTS_FILE = 'playlists.txt'
LISTENED_EPISODES_FILE = 'listened_episodes.txt'


async def fetch_videos_from_playlist(session, playlist_id):
    params = {
        'part': 'snippet',
        'playlistId': playlist_id,
        'maxResults': 50,
        'key': API_KEY
    }
    try:
        async with session.get(YOUTUBE_API_URL, params=params) as response:
            if response.status != 200:
                print(f"Failed to fetch data for playlist {playlist_id}: {response.status} {await response.text()}")
                return []
            data = await response.json()
            return data.get('items', [])
    except Exception as e:
        print(f"Error in fetch_videos_from_playlist for {playlist_id}: {e}")
        return []


async def fetch_playlist_title(session, playlist_id):
    params = {
        'part': 'snippet',
        'id': playlist_id,
        'key': API_KEY,
    }
    try:
        async with session.get(PLAYLIST_API_URL, params=params) as response:
            if response.status == 200:
                data = await response.json()
                if data.get('items'):
                    return {
                        'id': data['items'][0]['id'],
                        'title': data['items'][0]['snippet']['title'],
                        'channel_title': data['items'][0]['snippet']['channelTitle']
                    }
            else:
                print(f"Failed to fetch playlist title for {playlist_id}: {response.status} {await response.text()}")
    except Exception as e:
        print(f"Error in fetch_playlist_title for {playlist_id}: {e}")
    return None

REDDIT_CLIENT_ID = 't8iBT4qixHudVJrC62J_zw'
REDDIT_CLIENT_SECRET = 'GilsWCFm4d6MiGevxO1YJEiB8SPDPA' 
REDDIT_USER_AGENT = 'upsc_tracker by /u/YOUR_REDDIT_USERNAME' 

# Initialize PRAW
reddit = praw.Reddit(
    client_id=REDDIT_CLIENT_ID,
    client_secret=REDDIT_CLIENT_SECRET,
    user_agent=REDDIT_USER_AGENT
)


SUBREDDITS = ['UPSC','SideProject', 'datascience','explainlikeimfive','Krishnamurti','ycombinator','OpenAI','programming','AskReddit', 'worldnews', 'politics']

@app.route('/get_posts', methods=['POST'])
def get_posts():
    data = request.json
    selected_subreddits = data.get('subreddits', [])
    sort_method = data.get('sort', 'hot') 
    limit = int(data.get('limit', 10))

    all_posts = []
    for subreddit_name in selected_subreddits:
        try:
            subreddit = reddit.subreddit(subreddit_name)
            if sort_method == 'top':
                posts_iterable = subreddit.top(limit=limit)
            elif sort_method == 'new':
                posts_iterable = subreddit.new(limit=limit)
            else:
                posts_iterable = subreddit.hot(limit=limit)

            for post in posts_iterable:
                all_posts.append({
                    'subreddit': subreddit_name,
                    'title': post.title,
                    'url': post.url,
                    'author': post.author.name if post.author else '[deleted]',
                    'score': post.score,
                    'num_comments': post.num_comments,
                    'created_utc': post.created_utc,
                    'selftext': post.selftext[:300] + '...' if len(post.selftext) > 300 else post.selftext,
                    'link': f"https://reddit.com{post.permalink}",
                    'flair': post.link_flair_text if post.link_flair_text else 'No flair',
                    'nsfw': post.over_18,
                    'spoiler': post.spoiler
                })
        except Exception as e:
            print(f"Error fetching posts from subreddit {subreddit_name}: {e}")

    return jsonify(all_posts)

def filter_videos_by_date(videos, days=5):
    recent_videos = []
    if not videos: return [] 
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days) 
    for video in videos:
        try:
            publish_date = datetime.strptime(video['snippet']['publishedAt'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            if publish_date >= cutoff_date:
                recent_videos.append({
                    'videoId': video['snippet']['resourceId']['videoId'],
                    'title': video['snippet']['title'],
                    'url': f"https://www.youtube.com/watch?v={video['snippet']['resourceId']['videoId']}",
                    'publishedAt': publish_date
                })
        except (KeyError, TypeError, ValueError) as e:
            print(f"Error processing video data: {video.get('snippet', {}).get('title', 'Unknown Video')}. Error: {e}")
            continue
    return recent_videos

def load_watched_videos():
    if os.path.exists(WATCHED_VIDEOS_FILE):
        with open(WATCHED_VIDEOS_FILE, 'r') as file:
            return {line.strip() for line in file}
    return set()

def save_watched_videos(video_ids):
    try:
        with open(WATCHED_VIDEOS_FILE, 'a') as file:
            for video_id in video_ids:
                file.write(f"{video_id}\n")
    except IOError as e:
        print(f"Error saving watched videos: {e}")


def filter_unseen_videos(videos):
    if not videos: return []
    watched_videos = load_watched_videos()
    return [video for video in videos if video['videoId'] not in watched_videos]

async def load_playlists(session):
    playlists_data = []
    if os.path.exists(PLAYLISTS_FILE):
        try:
            with open(PLAYLISTS_FILE, 'r') as file:
                playlist_ids = [line.strip() for line in file]
            
            tasks = [fetch_playlist_title(session, playlist_id) for playlist_id in playlist_ids]
            playlist_details_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for detail in playlist_details_results:
                if isinstance(detail, Exception):
                    print(f"Error fetching a playlist detail: {detail}")
                elif detail:
                    playlists_data.append(detail)
        except Exception as e:
            print(f"Error loading playlists from file or fetching details: {e}")
    return playlists_data


def add_playlist(playlist_id):
    try:
        with open(PLAYLISTS_FILE, 'a') as file:
            file.write(f"{playlist_id}\n")
    except IOError as e:
        print(f"Error adding playlist to file: {e}")

async def scrape_air_content(url, title_filter):
    episodes = []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    print(f"Failed to fetch data from {url}: {response.status}")
                    return []
                content = await response.text()
                soup = BeautifulSoup(content, "html.parser")
                
                table = soup.find('table', class_='table')
                if not table:
                    print(f"Table not found on {url}")
                    return []
                
                rows = table.find_all('tr')[1:] 
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) < 4:
                        continue
                    
                    title = cols[0].text.strip()
                    date_str = cols[1].text.strip()
                    time_str = cols[2].text.strip()
                    
                    audio_tag = cols[3].find('audio')
                    audio_src = None
                    if audio_tag:
                        source_tag = audio_tag.find('source')
                        if source_tag and 'src' in source_tag.attrs:
                            audio_src = source_tag['src']

                    if not audio_src:
                        continue

                    try:
                        date_obj = datetime.strptime(f"{date_str} {time_str}", '%d %b %Y %H:%M')
                    except ValueError:
                        print(f"Could not parse date for AIR episode: {date_str} {time_str}")
                        continue
                    
                    if title in title_filter:
                        episodes.append({
                            'title': title,
                            'date': date_obj,
                            'audio_link': audio_src
                        })
    except Exception as e:
        print(f"Error scraping AIR content from {url} for titles {title_filter}: {e}")
    return episodes

async def scrape_air_spotlight():
    return await scrape_air_content("https://www.newsonair.gov.in/listen-broadcast-category/daily-broadcast/", ["Spotlight"])

async def scrape_air_insight():
    return await scrape_air_content("https://www.newsonair.gov.in/listen-broadcast-category/weekly-broadcast/", ["Insight", "Insights"])

async def scrape_air_economy():
    return await scrape_air_content("https://www.newsonair.gov.in/listen-broadcast-category/weekly-broadcast/", ["Money Talk"])

async def scrape_current_affairs_air():
    return await scrape_air_content("https://www.newsonair.gov.in/listen-broadcast-category/weekly-broadcast/", ["Current Affairs"])

def filter_recent_episodes(episodes, days=3):
    if not episodes: return []
    cutoff_date = datetime.now() - timedelta(days=days)
    return [episode for episode in episodes if episode['date'] >= cutoff_date]


def load_listened_episodes():
    if os.path.exists(LISTENED_EPISODES_FILE):
        with open(LISTENED_EPISODES_FILE, 'r') as file:
            return {line.strip() for line in file}
    return set()

def save_listened_episodes(episode_links):
    try:
        with open(LISTENED_EPISODES_FILE, 'a') as file:
            for link in episode_links:
                file.write(f"{link}\n")
    except IOError as e:
        print(f"Error saving listened episodes: {e}")


def filter_unheard_episodes(episodes):
    if not episodes: return []
    listened_episodes = load_listened_episodes()
    return [episode for episode in episodes if episode.get('audio_link') not in listened_episodes]


async def scrape_pib_asp_net(url, ministry=None, year=None, month=None, day=None):
    results = []
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': 'https://www.pib.gov.in',
            'Referer': url
        }

        # Use a session to persist cookies (ASP.NET_SessionId)
        async with aiohttp.ClientSession(headers=headers) as session:
            # 1. GET the page to get ViewState and Cookies
            async with session.get(url, ssl=False, timeout=30) as response:
                if response.status != 200:
                    return []
                html = await response.text()
                soup = BeautifulSoup(html, "html.parser")

            # 2. Extract ALL input values (hidden & visible) to mimic browser state perfectly
            form_data = {}
            for input_tag in soup.find_all('input'):
                if input_tag.get('name'):
                    form_data[input_tag.get('name')] = input_tag.get('value', '')

            # 3. Update with user filters
            # Ensure we don't send 'None', default to '0' (All) or existing defaults
            ministry_val = ministry if ministry and ministry != '0' else '0'
            year_val = year if year else '2024'
            month_val = month if month else '0'
            day_val = day if day else '0'

            # ASP.NET specific triggers. 
            # We trigger the Year dropdown to force a refresh of the list
            overrides = {
                '__EVENTTARGET': 'ctl00$ContentPlaceHolder1$ddlYear',
                '__EVENTARGUMENT': '',
                'ctl00$ContentPlaceHolder1$ddlMinistry': ministry_val,
                'ctl00$ContentPlaceHolder1$ddlYear': year_val,
                'ctl00$ContentPlaceHolder1$ddlMonth': month_val,
                'ctl00$ContentPlaceHolder1$ddlday': day_val,
                'ctl00$ContentPlaceHolder1$ddlSector': '0', # Default to All Sector
            }
            form_data.update(overrides)

            # 4. POST the updated data
            async with session.post(url, data=form_data, ssl=False, timeout=30) as post_response:
                if post_response.status != 200:
                    return []
                post_content = await post_response.text()
                post_soup = BeautifulSoup(post_content, "html.parser")

                # 5. Parse results
                content_area = post_soup.find('div', class_='content-area')
                if content_area:
                    for li in content_area.find_all('li'):
                        link_tag = li.find('a')
                        date_span = li.find('span', class_='publishdatesmall')
                        
                        if link_tag and date_span:
                            href = link_tag.get('href', '')
                            # Fix relative URLs
                            if href and not href.startswith('http'):
                                if href.startswith('/'):
                                    href = f"https://www.pib.gov.in{href}"
                                else:
                                    href = f"https://www.pib.gov.in/{href}"

                            results.append({
                                'title': link_tag.text.strip(),
                                'url': href,
                                'date': date_span.text.replace('Posted on:', '').strip()
                            })

    except Exception as e:
        print(f"PIB ASP scraping error: {e}")
    
    return results

async def scrape_pib(ministry=None, year=None, month=None, day=None):
    # Backgrounders URL
    url = "https://www.pib.gov.in/ViewBackgrounder.aspx?MenuId=51&reg=3&lang=1"
    data = await scrape_pib_asp_net(url, ministry, year, month, day)
    if data ==[]:
        url1 = "https://www.pib.gov.in/ViewBackgrounder.aspx?MenuId=51"
        data = await scrape_pib_asp_net(url1, ministry, year, month, day)
    return {'Backgrounders': data}

async def scrape_pib_facts(ministry=None, year=None, month=None, day=None):
    # Factsheets URL
    url = "https://www.pib.gov.in/AllFactsheet.aspx?MenuId=12&reg=3&lang=1"
    data = await scrape_pib_asp_net(url, ministry, year, month, day)
    if data ==[]:
        url1 = "https://www.pib.gov.in/ViewBackgrounder.aspx?MenuId=51"
        data = await scrape_pib_asp_net(url1, ministry, year, month, day)

    return {'Backgrounders': data}



#async def scrape_pib_facts(ministry=None, year=None, month=None, day=None):
#    return await _scrape_pib_with_playwright(
#        "https://pib.gov.in/AllFactsheet.aspx?MenuId=12=3&lang=1",
#        ministry, year, month, day
 #   )

#async def scrape_pib(ministry=None, year=None, month=None, day=None):
#    return await _scrape_pib_with_playwright(
#        "https://www.pib.gov.in/ViewBackgrounder.aspx?MenuId=51&reg=3&lang=1",
#        ministry, year, month, day
#    )


TH_url = "https://learningcorner.epaper.thehindu.com/articles" 


@app.route('/')
@cache.cached(timeout=300)
async def index():
    playlist_data = []
    spotlight_episodes, insight_episodes, economy_episodes, current_episodes_air = [], [], [], []
    indian_express_articles_data, orf_articles_data, sansad_tv_summaries_data = [], [], []
    pib_backgrounders_result, pib_facts_result, forum_ca_result = {}, {}, []
    headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

    async with aiohttp.ClientSession(headers=headers) as session:
        try:
            loaded_playlists = await load_playlists(session) 
            for playlist_item in loaded_playlists: 
                try:
                    videos = await fetch_videos_from_playlist(session, playlist_item['id'])
                    recent_videos = filter_videos_by_date(videos, days=5)
                    unseen_videos = filter_unseen_videos(recent_videos)
                    playlist_data.append({
                        'id': playlist_item['id'],
                        'title': playlist_item['title'],
                        'unseen_count': len(unseen_videos),
                        'channel': playlist_item['channel_title']
                    })
                except Exception as e:
                    print(f"Error processing playlist {playlist_item.get('id', 'N/A')}: {e}")
            playlist_data.sort(key=lambda x: x['unseen_count'], reverse=True)
        except Exception as e:
            print(f"Error loading or processing playlists: {e}")

        tasks_to_run = [
            scrape_air_spotlight(),
            scrape_air_insight(),
            scrape_air_economy(),
            scrape_current_affairs_air(),
            scrape_indian_express_articles(),
            scrape_orf_articles(),
            scrape_AIR_sansad_tv_summaries_Iasgyan(),
            scrape_pib(), 
            scrape_pib_facts(),
            scrape_forumias(),
            scrape_insights_articles() 
        ]
        results = await asyncio.gather(*tasks_to_run, return_exceptions=True)

        if not isinstance(results[0], Exception): spotlight_episodes = results[0]
        else: print(f"Error scraping AIR Spotlight: {results[0]}")

        if not isinstance(results[1], Exception): insight_episodes = results[1]
        else: print(f"Error scraping AIR Insight: {results[1]}")

        if not isinstance(results[2], Exception): economy_episodes = results[2]
        else: print(f"Error scraping AIR Economy: {results[2]}")

        if not isinstance(results[3], Exception): current_episodes_air = results[3]
        else: print(f"Error scraping AIR Current Affairs: {results[3]}")

        if not isinstance(results[4], Exception): indian_express_articles_data = results[4]
        else: print(f"Error scraping Indian Express: {results[4]}")

        if not isinstance(results[5], Exception): orf_articles_data = results[5]
        else: print(f"Error scraping ORF articles: {results[5]}")

        if not isinstance(results[6], Exception): sansad_tv_summaries_data = results[6]
        else: print(f"Error scraping Sansad TV Summaries (IASGyan): {results[6]}")
        
        if not isinstance(results[7], Exception): pib_backgrounders_result = results[7]
        else: print(f"Error scraping PIB Backgrounders: {results[7]}")

        if not isinstance(results[8], Exception): pib_facts_result = results[8]
        else: print(f"Error scraping PIB Facts: {results[8]}")
        
        if not isinstance(results[9], Exception): forum_ca_result = results[9]
        else: print(f"Error scraping ForumIAS CA: {results[9]}")
        if not isinstance(results[9], Exception): insights_articles_result  = results[10]
        else: print(f"Error scraping ForumIAS CA: {results[10]}")

    spotlight_unheard = filter_unheard_episodes(filter_recent_episodes(spotlight_episodes or [], days=5))
    insight_unheard = filter_unheard_episodes(filter_recent_episodes(insight_episodes or [], days=5))
    economy_unheard = filter_unheard_episodes(filter_recent_episodes(economy_episodes or [], days=5))
    current_unheard_air = filter_unheard_episodes(filter_recent_episodes(current_episodes_air or [], days=10))


    return render_template('index.html', 
                           playlists=playlist_data, 
                           spotlight_unheard_count=len(spotlight_unheard), 
                           insight_unheard_count=len(insight_unheard),
                           economy_unheard_count=len(economy_unheard),
                           current_unheard_count=len(current_unheard_air), 
                           sansad_tv_summaries=sansad_tv_summaries_data or [], 
                           pib_backgrounders=pib_backgrounders_result or {}, 
                           subreddits=SUBREDDITS,
                           articles=indian_express_articles_data or [], 
                           orfarticles=orf_articles_data or [], 
                           forum_ca=forum_ca_result or [], 
                           pibfacts=pib_facts_result or {},
                           insightarticles=insights_articles_result or []
                           ) 

@app.route('/unseen_videos/<playlist_id>')
async def unseen_videos(playlist_id):
    unseen_vids = [] 
    try:
        async with aiohttp.ClientSession() as session:
            videos = await fetch_videos_from_playlist(session, playlist_id)
            recent_videos = filter_videos_by_date(videos, days=5)
            unseen_vids = filter_unseen_videos(recent_videos)
    except Exception as e:
        print(f"Error in /unseen_videos/{playlist_id}: {e}")
    return render_template('unseen_videos.html', videos=unseen_vids, playlist_id=playlist_id)

@app.route('/pib')
async def pibscrap():
    ministry = request.args.get('ministry','0') 
    year = request.args.get('year','2024')
    month = request.args.get('month','0')
    day = request.args.get('day','0')

    pib_data = await scrape_pib(ministry=ministry, year=year, month=month, day=day)
    return render_template('pib.html', pib_backgrounders=pib_data or {})

@app.route('/pib_facts')
async def pibscrapfacts():
    ministry = request.args.get('ministry', '0') 
    year = request.args.get('year', '2024')
    month = request.args.get('month', '0')
    day = request.args.get('day', '0')

    pib_data = await scrape_pib_facts(ministry=ministry, year=year, month=month, day=day)
    return render_template('pib_facts.html', pib_backgrounders=pib_data or {}) 

@app.route('/mark_watched', methods=['POST'])
def mark_watched():
    video_ids = request.form.getlist('video_ids')
    save_watched_videos(video_ids)
    playlist_id = request.form.get('playlist_id')
    if playlist_id:
        return redirect(url_for('unseen_videos', playlist_id=playlist_id))
    return redirect(url_for('index'))


@app.route('/add_playlist', methods=['GET', 'POST'])
def add_playlist_route():
    if request.method == 'POST':
        playlist_id = request.form.get('playlist_id', '').strip()
        if playlist_id:
            add_playlist(playlist_id)
        return redirect(url_for('index'))
    return render_template('add_playlist.html')

async def _render_air_episodes_page(scrape_function, days_filter, template_name='spotlight.html'):
    episodes_data = []
    try:
        raw_episodes = await scrape_function()
        recent_episodes_data = filter_recent_episodes(raw_episodes or [], days=days_filter)
        episodes_data = filter_unheard_episodes(recent_episodes_data or [])
    except Exception as e:
        print(f"Error in AIR episodes route for {scrape_function.__name__}: {e}")
    return render_template(template_name, episodes=episodes_data)

@app.route('/spotlight')
async def spotlight():
    return await _render_air_episodes_page(scrape_air_spotlight, 5)

@app.route('/Insight') 
async def insight():
    return await _render_air_episodes_page(scrape_air_insight, 5)

@app.route('/aireconomy')
async def aireconomy():
    return await _render_air_episodes_page(scrape_air_economy, 5)

@app.route('/aircurrentaffairs')
async def airCA():
    return await _render_air_episodes_page(scrape_current_affairs_air, 10)


@app.route('/mark_listened', methods=['POST'])
def mark_listened():
    episode_links = request.form.getlist('episode_links')
    save_listened_episodes(episode_links)
    return redirect(request.referrer or url_for('index'))


BASE_URL_MEA = "https://www.mea.gov.in/bilateral-documents.htm" 

async def fetch_page_mea(session, url): # Renamed
    try:
        async with session.get(url, timeout=20) as response: 
            if response.status != 200:
                print(f"Failed to fetch MEA page {url}: {response.status}")
                return None
            return await response.text()
    except Exception as e:
        print(f"Error fetching MEA page {url}: {e}")
        return None

async def parse_page_mea(content, days_ago_cutoff_date):
    documents = []
    continue_scraping = True 
    if not content:
        return documents, False 

    soup = BeautifulSoup(content, "html.parser")
    item_list = soup.find('ul', class_='commonListing')
    
    if item_list:
        for item in item_list.find_all('li'):
            title_link = item.find('a', class_='searchContent')
            date_container = item.find('span', class_='date') 
            
            if title_link and date_container:
                title = title_link.text.strip()
                doc_url = title_link['href']
                if not doc_url.startswith('http'):
                    doc_url = f"https://www.mea.gov.in{doc_url}" if doc_url.startswith('/') else f"https://www.mea.gov.in/{doc_url}"
                
                date_str_raw = date_container.text.strip() 
                
                try:
                    date_obj = datetime.strptime(date_str_raw, "%B %d, %Y").replace(tzinfo=timezone.utc)
                    if date_obj >= days_ago_cutoff_date:
                        documents.append({
                            'title': title,
                            'url': doc_url,
                            'date': date_obj.strftime("%B %d, %Y") # Store as string for template
                        })
                    else:
                        continue_scraping = False # Found an old document, stop
                        break # Stop processing this page further
                except ValueError:
                    print(f"Error parsing MEA date: {date_str_raw} for title '{title}'")
    else:
        print("MEA commonListing not found.")
        continue_scraping = False # If structure changed, stop.

    return documents, continue_scraping

def get_next_page_url_mea(content):
    if not content: return None
    soup = BeautifulSoup(content, "html.parser")
    next_link = soup.find('a', class_='next')
    if next_link and 'href' in next_link.attrs:
        href = next_link['href']
        if href.startswith('http'):
            return href
        elif href.startswith('/'):
            return f"https://www.mea.gov.in{href}"
        else:
            return f"https://www.mea.gov.in/bilateral-documents/{href}"
    return None

async def scrape_bilateral_documents():
    all_documents = []
    try:
        async with aiohttp.ClientSession() as session:
            current_url = f"{BASE_URL_MEA}?53/Bilateral/Multilateral_Documents" 
            days_ago_cutoff_date = (datetime.now(timezone.utc) - timedelta(days=90)).replace(hour=0, minute=0, second=0, microsecond=0)

            page_count = 0
            max_pages = 10

            while current_url and page_count < max_pages:
                page_count += 1
                print(f"Scraping MEA page {page_count}: {current_url}")
                content = await fetch_page_mea(session, current_url)
                if not content:
                    break

                documents_on_page, continue_scraping = await parse_page_mea(content, days_ago_cutoff_date)
                all_documents.extend(documents_on_page)

                if not continue_scraping:
                    print("Stopping MEA scraping based on date or parsing issue.")
                    break
                
                current_url = get_next_page_url_mea(content)
                if not current_url:
                    print("No next page found for MEA.")
                    break
                await asyncio.sleep(1)
    except Exception as e:
        print(f"Error during MEA bilateral documents scraping: {e}")
    return all_documents

@app.route('/MEAsite')
@cache.cached(timeout=3600) 
async def bilateral_documents():
    documents_data = await scrape_bilateral_documents()
    return render_template('bilateral_documents.html', documents=documents_data or [])

async def scrape_prs_india():
    cards_data = [] # Renamed
    try:
        url = "https://prsindia.org"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=20) as response:
                if response.status != 200:
                    print(f"Failed to fetch PRS India data: {response.status}")
                    return []
                content = await response.text()
                soup = BeautifulSoup(content, "html.parser")
                
                right_banner = soup.find('div', class_='right-banner') 
                if right_banner:
                    for item in right_banner.find_all(['div','section'], class_=re.compile(r"col-\w*-6|card-item-class")): 
                        image_tag = item.find('img')
                        link_tag = item.find('a')
                        title_tag = item.find(['h3','h4','h5']) 
                        
                        if link_tag and title_tag: 
                            img_src = None
                            if image_tag and 'src' in image_tag.attrs:
                                img_src = image_tag['src']
                                if not img_src.startswith('http'):
                                    img_src = url + img_src if img_src.startswith('/') else url + '/' + img_src
                            
                            link_href = link_tag['href']
                            if not link_href.startswith('http'):
                                link_href = url + link_href if link_href.startswith('/') else url + '/' + link_href

                            cards_data.append({
                                'title': title_tag.text.strip(),
                                'image_url': img_src,
                                'link_url': link_href
                            })
                else:
                    print("PRS India: right-banner not found or structure changed.")

    except Exception as e:
        print(f"Error scraping PRS India: {e}")
    return cards_data

@app.route('/prsindia')
@cache.cached(timeout=3600) 
async def prs_india():
    scraped_cards = await scrape_prs_india() 
    return render_template('prsindia.html', cards=scraped_cards or [])


async def scrape_current_affairs_iasgyan():
    current_affairs_data = [] 
    try:
        url = "https://www.iasgyan.in/daily-current-affairs"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=20) as response:
                if response.status != 200:
                    print(f"Failed to fetch IASGyan Current Affairs data: {response.status}")
                    return []
                content = await response.text()
                soup = BeautifulSoup(content, "html.parser")

                cutoff_date_iasgyan = datetime.now() - timedelta(days=6)

                for article_block in soup.find_all('div', class_='shadow mt-4 rounded-2'): 
                    title_tag_ias = article_block.find('h3', class_='fw-semibold text-white m-0 fs-5')
                    article_links_list = article_block.find_all('a', class_='w-100')

                    if title_tag_ias and article_links_list:
                        date_str_match = re.search(r'–\s*(.+)$', title_tag_ias.text.strip())
                        if not date_str_match: continue
                        
                        date_str_cleaned = re.sub(r'(\d+)(st|nd|rd|th|TH|ND|RD|ST)\s*', r'\1 ', date_str_match.group(1).strip())
                        date_str_cleaned = date_str_cleaned.replace("  ", " ") 
                        
                        try:
                            article_date_obj = datetime.strptime(date_str_cleaned.strip(), '%d %B %Y') 
                        except ValueError as ve:
                            print(f"IASGyan: Error parsing date '{date_str_cleaned}': {ve}")
                            continue
                        
                        if article_date_obj >= cutoff_date_iasgyan:
                            articles_for_date = []
                            for link_item in article_links_list:
                                articles_for_date.append({
                                    'title': link_item.text.strip(),
                                    'url': link_item['href'] if link_item.get('href') else '#'
                                })
                            if articles_for_date: 
                                current_affairs_data.append({
                                    'date': article_date_obj, 
                                    'articles': articles_for_date
                                })
        current_affairs_data.sort(key=lambda x: x['date'], reverse=True) 
    except Exception as e:
        print(f"Error scraping IASGyan Current Affairs: {e}")
    return current_affairs_data


async def scrape_AIR_sansad_tv_summaries_Iasgyan():
    summaries_data = [] # Renamed
    try:
        url = "https://www.iasgyan.in/sansad-tv-air-summaries"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=20) as response:
                if response.status != 200:
                    print(f"Failed to fetch IASGyan Sansad TV & AIR summaries: {response.status}")
                    return []
                content = await response.text()
                soup = BeautifulSoup(content, "html.parser")

                for summary_block_item in soup.find_all('div', class_='content_bx'): # Renamed
                    title_tag_sum = summary_block_item.find('div', class_='title').find('a') if summary_block_item.find('div', class_='title') else None
                    date_tag_sum = summary_block_item.find('li', class_='text-muted')
                    description_tag_sum = summary_block_item.find('div', class_='short_descr').find('ol') if summary_block_item.find('div', class_='short_descr') else None
                    read_more_tag_sum = summary_block_item.find('div', class_='readmore_btn').find('a') if summary_block_item.find('div', class_='readmore_btn') else None

                    if not (title_tag_sum and date_tag_sum and description_tag_sum and read_more_tag_sum):
                        continue # Skip if essential elements are missing

                    title_text = title_tag_sum.text.strip()
                    doc_url_sum = title_tag_sum['href']
                    
                    # Clean and parse date string, e.g., "25 Sep, 2024" or "25 September, 2024"
                    summary_date_str_raw = " ".join(date_tag_sum.text.strip().split()).replace(',', '') # "25 Sep 2024"
                    try:
                        # Try common formats, this might need adjustment based on actual site variations
                        if len(summary_date_str_raw.split()[1]) == 3: # Short month name e.g. Sep
                             parsed_date_sum = datetime.strptime(summary_date_str_raw, '%d %b %Y')
                        else: # Full month name e.g. September
                             parsed_date_sum = datetime.strptime(summary_date_str_raw, '%d %B %Y')
                    except ValueError:
                        print(f"IASGyan Summaries: Could not parse date '{summary_date_str_raw}' for '{title_text}'")
                        parsed_date_sum = datetime.min # Fallback date for sorting if unparsable

                    summary_points_list = [li.text.strip() for li in description_tag_sum.find_all('li')]

                    summaries_data.append({
                        'title': title_text,
                        'url': doc_url_sum,
                        'date_obj': parsed_date_sum, # For sorting
                        'date': parsed_date_sum.strftime('%d %b %Y') if parsed_date_sum != datetime.min else summary_date_str_raw, # Formatted string for display
                        'points': summary_points_list,
                        'read_more_url': read_more_tag_sum['href']
                    })
                
                summaries_data.sort(key=lambda x: x['date_obj'], reverse=True) # Sort by actual date object
                return summaries_data[:3] # Return top 3 recent
    except Exception as e:
        print(f"Error scraping IASGyan Sansad TV summaries: {e}")
    return summaries_data # Return whatever was collected or empty list


async def scrape_indian_express_articles():
    articles_data = []
    try:
        url = "https://indianexpress.com/section/upsc-current-affairs/upsc-essentials/"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=20) as response:
                if response.status != 200:
                    print(f"Failed to fetch Indian Express UPSC articles: {response.status}")
                    return []
                content = await response.text()
                soup = BeautifulSoup(content, "html.parser")
                
                one_week_ago_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
                
                for article_div in soup.find_all('div', class_='articles'):
                    try:
                        context_div = article_div.find('div', class_='img-context')
                        if not context_div: continue

                        title_tag = context_div.find('h2', class_='title').find('a')
                        if not title_tag: continue
                        
                        title_text = title_tag.text.strip()
                        doc_url = title_tag['href']
                        date_div = context_div.find('div', class_='date')
                        date_str_raw = date_div.text.strip() if date_div else ""
                        summary_tag = context_div.find('p')
                        summary_text = summary_tag.text.strip() if summary_tag else ""
                        snaps_div = article_div.find('div', class_='snaps')
                        image_url = None
                        if snaps_div:
                            img = snaps_div.find('img')
                            if img:
                                image_url = img.get('src') or img.get('data-src')
                        article_date_obj = None
                        clean_date_str = date_str_raw.replace('IST', '').strip()
                        clean_date_str = re.sub(r'\s+', ' ', clean_date_str)
                        
                        try:
                            article_date_obj = datetime.strptime(clean_date_str, '%B %d, %Y %H:%M')
                        except ValueError:
                            try:
                                article_date_obj = datetime.strptime(clean_date_str, '%B %d, %Y')
                            except ValueError:
                                continue 
                        article_date_obj = article_date_obj.replace(tzinfo=timezone.utc)

                        if article_date_obj >= one_week_ago_cutoff:
                            articles_data.append({
                                'title': title_text,
                                'url': doc_url,
                                'image_url': image_url,
                                'date': date_str_raw,
                                'summary': summary_text,
                                'date_obj': article_date_obj 
                            })
                    except Exception as inner_e:
                        print(f"Error parsing specific IE article: {inner_e}")
                        continue

        articles_data.sort(key=lambda x: x['date_obj'], reverse=True)

    except Exception as e:
        print(f"Error scraping Indian Express articles: {e}")
    return articles_data


async def scrape_full_article(url):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=20) as response:
                if response.status != 200:
                    print(f"Failed to fetch article content from {url}: {response.status}")
                    return None
                content = await response.text()
                soup = BeautifulSoup(content, "html.parser")
                
                content_div = soup.find('div', id='pcl-full-content') # Highly specific, might break
                if not content_div: # Fallback or broader search
                    content_div = soup.find('article') or soup.find('main') or soup.find('div', class_=re.compile(r'content|article-body|story'))

                if not content_div:
                    print(f"Could not find main content container for {url}")
                    return f"<p>Content not found. Please visit <a href='{url}'>original article</a>.</p>"
                
                title_tag_full = soup.find(['h1', 'h2'], class_=re.compile(r'title|headline')) # Common title classes
                if not title_tag_full: title_tag_full = soup.find('h1') # Generic h1
                title_text_full = title_tag_full.get_text(strip=True) if title_tag_full else "Article"
                
                author_date_div = soup.find(['div','span'], class_=re.compile(r'editor|author|date|byline|meta')) # Common meta info classes
                author_date_text_full = author_date_div.get_text(separator=" ", strip=True) if author_date_div else ""
                
                # Extract and process paragraphs, headings, lists, blockquotes
                elements = content_div.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'blockquote', 'figure', 'table'])
                formatted_content_parts = []
                for elem in elements:
                    if elem.name in ['h1','h2','h3','h4','h5','h6']:
                        formatted_content_parts.append(f"<{elem.name}>{elem.get_text(strip=True)}</{elem.name}>")
                    elif elem.name == 'p':
                        # Check if paragraph is inside a list item, if so, it's part of the li
                        if elem.find_parent('li'): 
                            continue 
                        formatted_content_parts.append(f"<p>{elem.get_text(separator=' ', strip=True)}</p>")
                    elif elem.name in ['ul', 'ol']:
                        list_items_html = "".join([f"<li>{li_item.get_text(separator=' ', strip=True)}</li>" for li_item in elem.find_all('li', recursive=False)])
                        formatted_content_parts.append(f"<{elem.name}>{list_items_html}</{elem.name}>")
                    elif elem.name == 'blockquote':
                        formatted_content_parts.append(f"<blockquote>{elem.get_text(separator=' ', strip=True)}</blockquote>")
                    elif elem.name == 'figure':
                        img = elem.find('img')
                        caption = elem.find('figcaption')
                        if img and 'src' in img.attrs:
                            img_html = f"<img src='{img['src']}' alt='{img.get('alt','Image')}' style='max-width:100%; height:auto;'>"
                            if caption:
                                img_html += f"<figcaption>{caption.get_text(strip=True)}</figcaption>"
                            formatted_content_parts.append(f"<figure>{img_html}</figure>")
                    elif elem.name == 'table':
                         # Basic table conversion; for complex tables, more work is needed
                        table_html = "<table>"
                        for tr in elem.find_all('tr'):
                            table_html += "<tr>"
                            for th_td in tr.find_all(['th', 'td']):
                                table_html += f"<{th_td.name}>{th_td.get_text(strip=True)}</{th_td.name}>"
                            table_html += "</tr>"
                        table_html += "</table>"
                        formatted_content_parts.append(table_html)


                full_article_html = f"<h1>{title_text_full}</h1>"
                if author_date_text_full:
                    full_article_html += f"<div class='article-meta' style='color:grey; margin-bottom:1em;'>{author_date_text_full}</div>"
                full_article_html += "\n".join(formatted_content_parts)
                
                return full_article_html
    except Exception as e:
        print(f"Error scraping full article from {url}: {e}")
        return f"<p>Error loading article content. Please visit <a href='{url}'>original article</a>.</p>"


@app.route('/article/<path:url>')
async def show_article(url):
    # Ensure the URL is complete if it was passed partially
    if not url.startswith('http'):
        # This is a basic assumption; you might need a more robust way
        # to reconstruct the URL if it's from a specific known domain.
        # For now, we assume it's a full URL passed in the path.
        # If not, this route might need the original domain.
        print(f"Warning: URL '{url}' might be partial. Assuming it's complete.")

    full_content_html = await scrape_full_article(url) # Renamed
    if full_content_html is None: # Should now return error HTML string
        full_content_html = f"<p>Failed to fetch article content for {url}.</p>"
    return render_template('full_article.html', content=full_content_html)


async def scrape_insights_articles():
    articles_data_insights = []
    try:
        # Updated URL for the main Answer Writing page
        url = 'https://www.insightsonindia.com/upsc-mains-answer-writing-2025-insights-ias/'
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=20) as response:
                if response.status != 200:
                    print(f"Failed to fetch Insights Answer Writing links: {response.status}")
                    return []
                content = await response.text()
                soup = BeautifulSoup(content, 'html.parser')
                count = 0
                for div_block in soup.find_all('div', class_='list_div'):
                    if count >= 2: break 
                    
                    ul_tag = div_block.find('ul', class_='lcp_catlist')
                    if ul_tag:
                        for li in ul_tag.find_all('li'):
                            a_tag = li.find('a')
                            if a_tag and a_tag.get('href'):
                                title = a_tag.text.strip()
                                link = a_tag['href']
                                articles_data_insights.append({
                                    'title': title,
                                    'link': link
                                })
                        count += 1
                        
    except Exception as e:
        print(f"Error scraping Insights Answer Writing links: {e}")
    print(articles_data_insights)
    return articles_data_insights

async def scrape_full_article_insight(article_url):
    filtered_content_parts = [] # Renamed
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(article_url, timeout=20) as response:
                if response.status != 200:
                    print(f"Failed to fetch Insights article content from {article_url}: {response.status}")
                    return None # Or some error indicator
                content = await response.text()
                soup = BeautifulSoup(content, 'html.parser')

                # The original logic was very specific (GS sections).
                # A more general approach might be to find the main article body.
                article_body = soup.find('div', class_=re.compile(r'entry-content|article-content|post-content'))
                if not article_body:
                    print(f"Insights: Could not find article body for {article_url}")
                    return [{'type': 'p', 'text': 'Article content not found.'}]

                current_section_text = None # Renamed

                for tag_item in article_body.find_all(['h1','h2','h3', 'h4', 'p', 'ul', 'ol', 'blockquote', 'table']): # Added more tags
                    if tag_item.name in ['h1','h2','h3','h4']: # Generic heading
                        current_section_text = tag_item.text.strip()
                        filtered_content_parts.append({'type': tag_item.name, 'text': current_section_text})
                    elif tag_item.name == 'p':
                        # Add paragraph text, optionally under a section if logic requires
                        filtered_content_parts.append({'type': 'p', 'text': tag_item.text.strip()})
                    elif tag_item.name in ['ul', 'ol']:
                        items = [li.get_text(strip=True) for li in tag_item.find_all('li')]
                        if items:
                            filtered_content_parts.append({'type': 'list', 'ordered': tag_item.name == 'ol', 'items': items})
                    elif tag_item.name == 'blockquote':
                        filtered_content_parts.append({'type': 'blockquote', 'text': tag_item.get_text(strip=True)})
                    elif tag_item.name == 'table':
                        rows = []
                        for tr in tag_item.find_all('tr'):
                            cells = [td.get_text(strip=True) for td in tr.find_all(['th', 'td'])]
                            rows.append(cells)
                        if rows:
                           filtered_content_parts.append({'type': 'table', 'rows': rows})


    except Exception as e:
        print(f"Error scraping full Insights article from {article_url}: {e}")
        return [{'type': 'p', 'text': f'Error loading article: {e}'}]
    return filtered_content_parts


@app.route('/article_insight/<path:url>')
async def show_article_insight(url):
    full_content_data = await scrape_full_article_insight(url) # Renamed
    if not full_content_data: # Check if None or empty
        return "Failed to load the Insights article content.", 404
    return render_template('full_article_insight.html', content=full_content_data)


async def scrape_orf_articles():
    orf_articles_data = []
    try:
        url = 'https://www.orfonline.org/content-type/issue-briefs'
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=20) as response:
                if response.status != 200:
                    print(f"Failed to fetch ORF articles from {url}: {response.status}")
                    return []
                content = await response.text()
                soup = BeautifulSoup(content, 'html.parser')

                cutoff_orf = datetime.now(timezone.utc) - timedelta(days=45)

                # Generic search for article cards to handle site changes
                # We look for common container classes used in grid layouts
                potential_articles = soup.find_all('div', class_=re.compile(r'col-|card|item|listing|post'))
                
                for article_block in potential_articles:
                    # 1. Find Title (usually in h2 or h3)
                    title_tag = article_block.find(['h2', 'h3'])
                    if not title_tag: 
                        continue
                    
                    title_text = title_tag.get_text(strip=True)
                    if not title_text or len(title_text) < 10: # Skip tiny/irrelevant headings
                        continue

                    # 2. Find Link (Check inside title, or parent of title, or anywhere in block)
                    link_tag = title_tag.find('a')
                    if not link_tag:
                        # Check if the block itself is wrapped in an 'a' tag
                        link_tag = article_block.find('a')
                    
                    if not link_tag or not link_tag.get('href'):
                        continue
                        
                    doc_url = link_tag['href']
                    if not doc_url.startswith('http'):
                        doc_url = f"https://www.orfonline.org{doc_url}" if doc_url.startswith('/') else f"https://www.orfonline.org/{doc_url}"

                    # 3. Find Date (Look for <time> or elements with 'date' class)
                    date_tag = article_block.find('time') or article_block.find(class_=re.compile(r'date|meta|time'))
                    article_date_obj = None
                    
                    if date_tag:
                        date_str = date_tag.get_text(strip=True)
                        try:
                            # Parse "Sep 24, 2024" or "24 September 2024"
                            article_date_obj = datetime.strptime(date_str, "%b %d, %Y").replace(tzinfo=timezone.utc)
                        except ValueError:
                            try:
                                article_date_obj = datetime.strptime(date_str, "%d %B %Y").replace(tzinfo=timezone.utc)
                            except ValueError:
                                pass # Keep None if parsing fails
                    
                    # Fallback: If no date found, include it anyway if it looks like an article
                    if not article_date_obj:
                         article_date_obj = datetime.now(timezone.utc) # Default to now if undatable

                    if article_date_obj >= cutoff_orf:
                        # 4. Find Description/Author
                        desc_tag = article_block.find('p')
                        desc_text = desc_tag.get_text(strip=True) if desc_tag else ""
                        
                        # Prevent duplicates (simple check)
                        if any(a['link'] == doc_url for a in orf_articles_data):
                            continue

                        orf_articles_data.append({
                            'title': title_text,
                            'link': doc_url,
                            'date_obj': article_date_obj,
                            'date': article_date_obj.strftime('%B %d, %Y'),
                            'description': desc_text,
                            'author': "ORF" # Author extraction is often messy, defaulting to ORF
                        })

    except Exception as e:
        print(f"Error scraping ORF articles: {e}")
    
    # Deduplicate and sort
    seen = set()
    unique_data = []
    for d in orf_articles_data:
        if d['link'] not in seen:
            seen.add(d['link'])
            unique_data.append(d)
            
    unique_data.sort(key=lambda x: x['date_obj'], reverse=True)
    return unique_data


async def scrape_forumias():
    sections_data = []
    try:
        # Updated URL based on your input
        url = "https://forumias.com/blog/7pm/"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=20) as response:
                if response.status != 200:
                    print(f"Failed to fetch ForumIAS CA links: {response.status}")
                    return []
                content = await response.text()
                soup = BeautifulSoup(content, "html.parser")

                # The new structure contains monthly tabs. We grab the first active output container.
                # Usually the first .ajax-cat-archive-output contains the latest loaded month.
                archive_container = soup.find('div', class_='ajax-cat-archive-output')
                
                if archive_container:
                    current_section_title = "Latest 7 PM Editorials"
                    articles_in_section = []

                    # Iterate through the date groups (e.g., 27 NOV, 26 NOV)
                    for date_group in archive_container.find_all('div', class_='cat-archive-date-group'):
                        
                        # Extract Date info (optional, just for context)
                        date_div = date_group.find('div', class_='post-date')
                        date_text = date_div.text.strip() if date_div else ""
                        
                        # Find the list of articles for this date
                        ul_list = date_group.find('ul', class_='cat-archive-list')
                        if ul_list:
                            for li in ul_list.find_all('li'):
                                a_tag = li.find('a')
                                if a_tag and a_tag.get('href'):
                                    title = a_tag.text.strip()
                                    if date_text:
                                        title = f"[{date_text}] {title}"
                                        
                                    articles_in_section.append({
                                        'title': title,
                                        'url': a_tag['href']
                                    })

                    if articles_in_section:
                        sections_data.append({
                            'section': current_section_title,
                            'articles': articles_in_section
                        })
                else:
                    print("ForumIAS: No archive output found.")

    except Exception as e:
        print(f"Error scraping ForumIAS CA links: {e}")
    return sections_data


async def scrape_forumias_article(article_url):
    content_parts_forum = []
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(article_url, timeout=30) as response:
                if response.status != 200:
                    print(f"Failed to fetch ForumIAS article content from {article_url}: {response.status}")
                    return [{'type':'error', 'text': f'Failed to fetch: {response.status}'}]
                
                content = await response.text()
                soup = BeautifulSoup(content, "html.parser")

                article_content_div = soup.find('div', class_='entry-content')
                
                if not article_content_div:
                    print(f"ForumIAS: Article content div 'entry-content' not found for {article_url}")
                    return [{'type':'error', 'text': 'Main content area not found.'}]

                for garbage in article_content_div.find_all(['div'], class_=re.compile(r'mobile_ad|web_ad|sharedaddy|robots-nocontent')):
                    garbage.decompose()

                for element in article_content_div.children:
                    if isinstance(element, NavigableString):
                        text = str(element).strip()
                        if text:
                            content_parts_forum.append({'type': 'text', 'text': text})
                        continue

                    if not hasattr(element, 'name') or not element.name:
                        continue

                    tag_name = element.name
                    text_content = element.get_text(separator=" ", strip=True)

                    if tag_name == 'p':
                        if text_content:
                            content_parts_forum.append({'type': 'paragraph', 'text': text_content})
                    
                    elif tag_name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                        content_parts_forum.append({'type': 'header', 'level': tag_name[1], 'text': text_content})
                    
                    elif tag_name in ['ul', 'ol']:
                        list_items = []
                        for li in element.find_all('li', recursive=False):
                            li_text = li.get_text(separator=" ", strip=True)
                            if li_text:
                                list_items.append({'text': li_text})
                        if list_items:
                            content_parts_forum.append({'type': 'list', 'ordered': tag_name == 'ol', 'items': list_items})
                    
                    elif tag_name == 'table':
                        # Simple table extraction
                        rows = []
                        for tr in element.find_all('tr'):
                            cells = [td.get_text(separator=" ", strip=True) for td in tr.find_all(['th', 'td'])]
                            rows.append(cells)
                        if rows:
                            content_parts_forum.append({'type': 'table', 'data': rows})
                    
                    elif tag_name == 'figure' or (tag_name == 'div' and 'wp-caption' in element.get('class', [])):
                        img = element.find('img')
                        if img and img.get('src'):
                            caption = element.find('figcaption')
                            caption_text = caption.get_text(strip=True) if caption else ''
                            content_parts_forum.append({
                                'type': 'image',
                                'src': img['src'],
                                'alt': img.get('alt', ''),
                                'caption': caption_text
                            })
                    
                    elif tag_name == 'blockquote':
                        content_parts_forum.append({'type': 'blockquote', 'text': text_content})

    except Exception as e:
        print(f"An error occurred in scrape_forumias_article for {article_url}: {e}")
        content_parts_forum.append({'type':'error', 'text': f'Error processing article: {e}'})
        
    return content_parts_forum


@app.route('/forumias')
async def forumias():
    scraped_sections = await scrape_forumias()
    return render_template('forumias.html', sections=scraped_sections or [])

@app.route('/forumias_article/<path:url>')
async def forumias_article(url):
    article_content_data = await scrape_forumias_article(url) 
    return render_template('forumias_article.html', content=article_content_data)


@app.route('/TH_article/<path:url>')
async def show_th_article(url):
    article_content_data = await scrape_TH_learning(url) 
    if not article_content_data: 
        return "Failed to load The Hindu Learning Corner article content.", 404
    return render_template('article_content.html', content=article_content_data)

async def scrape_TH_learning(article_url_th):
    article_content_th = []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(article_url_th, timeout=20) as response:
                if response.status != 200:
                    print(f"Failed to fetch TH Learning article from {article_url_th}: {response.status}")
                    return None
                content = await response.text()
                soup = BeautifulSoup(content, "html.parser")

     
                main_content_area = soup.find('div', class_=re.compile(r'articlebody|content|story-body'))
                if not main_content_area:
                     main_content_area = soup

                for tag_item_th in main_content_area.find_all(['h1','h2','h3', 'h4', 'p', 'ul', 'ol']):
                    if tag_item_th.name in ['h1','h2','h3','h4']:
                        article_content_th.append({'type': tag_item_th.name, 'text': tag_item_th.text.strip()})
                    elif tag_item_th.name == 'p':
                        article_content_th.append({'type': 'p', 'text': tag_item_th.text.strip()})
                    elif tag_item_th.name in ['ul', 'ol']:
                        items = [li.get_text(strip=True) for li in tag_item_th.find_all('li')]
                        if items:
                             article_content_th.append({'type':'list', 'ordered': tag_item_th.name=='ol', 'items':items})
                
                if not article_content_th and main_content_area == soup:
                    print(f"TH Learning: No specific content tags found on {article_url_th}, page might be structured differently.")

    except Exception as e:
        print(f"Error scraping TH Learning article from {article_url_th}: {e}")
        return None 
    return article_content_th


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))