from flask import Flask, render_template, jsonify
from flask_cors import CORS
import requests
import json
from datetime import datetime, timedelta
import os

app = Flask(__name__)
CORS(app)

# Configuration
YOUTUBE_API_KEY = "AIzaSyC0SxGDOCWVJULinOIK3JcBHgKjU_iHZRo"
YOUTUBE_CHANNEL_ID = "UC1cpa_85aqDkSmVQBpzGdkA"
GOOGLE_SHEET_ID = "128eXNcFknv8c_0_KHyBXiTRlhYjUAea0kqvSS1eVRq4"
SHEET_NAME = "Sheet1"

# Cache
cache = {
    'data': None,
    'timestamp': None,
    'ttl': 300  # 5 minutes
}

def get_sheet_data():
    """Fetch data from Google Sheets"""
    url = f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}/gviz/tq?tqx=out:json&sheet={SHEET_NAME}"
    
    try:
        response = requests.get(url, timeout=10)
        json_string = response.text
        
        # Remove Google's JSON wrapper
        json_string = json_string.replace("/*O_o*/\ngoogle.visualization.Query.setResponse(", "")
        json_string = json_string.rstrip(");")
        
        data = json.loads(json_string)
        
        # Parse rows
        rows = []
        if 'table' in data and 'rows' in data['table']:
            for row in data['table']['rows']:
                row_data = {}
                cells = row.get('c', [])
                
                if len(cells) > 0 and cells[0]:
                    row_data['timestamp'] = cells[0].get('f') or cells[0].get('v')
                if len(cells) > 1 and cells[1]:
                    row_data['music_title'] = cells[1].get('v')
                if len(cells) > 2 and cells[2]:
                    row_data['music_creator'] = cells[2].get('v')
                if len(cells) > 3 and cells[3]:
                    row_data['youtube_title'] = cells[3].get('v')
                if len(cells) > 4 and cells[4]:
                    row_data['youtube_video_id'] = cells[4].get('v')
                if len(cells) > 5 and cells[5]:
                    row_data['youtube_url'] = cells[5].get('v')
                
                if row_data.get('youtube_video_id'):
                    rows.append(row_data)
        
        return rows
    except Exception as e:
        print(f"Error fetching sheet data: {e}")
        return []

def get_youtube_channel_stats():
    """Fetch YouTube channel statistics"""
    url = f"https://www.googleapis.com/youtube/v3/channels"
    params = {
        'part': 'statistics,snippet',
        'id': YOUTUBE_CHANNEL_ID,
        'key': YOUTUBE_API_KEY
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        if 'items' in data and len(data['items']) > 0:
            stats = data['items'][0]['statistics']
            return {
                'subscribers': int(stats.get('subscriberCount', 0)),
                'total_views': int(stats.get('viewCount', 0)),
                'total_videos': int(stats.get('videoCount', 0))
            }
    except Exception as e:
        print(f"Error fetching channel stats: {e}")
    
    return {'subscribers': 0, 'total_views': 0, 'total_videos': 0}

def get_video_views(video_ids):
    """Fetch view counts for multiple videos"""
    if not video_ids:
        return {}
    
    # YouTube API allows up to 50 video IDs per request
    video_views = {}
    
    for i in range(0, len(video_ids), 50):
        batch_ids = video_ids[i:i+50]
        ids_string = ','.join(batch_ids)
        
        url = f"https://www.googleapis.com/youtube/v3/videos"
        params = {
            'part': 'statistics',
            'id': ids_string,
            'key': YOUTUBE_API_KEY
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if 'items' in data:
                for item in data['items']:
                    video_id = item['id']
                    views = int(item['statistics'].get('viewCount', 0))
                    video_views[video_id] = views
        except Exception as e:
            print(f"Error fetching video views: {e}")
    
    return video_views

def get_dashboard_data():
    """Get all dashboard data with caching"""
    now = datetime.now()
    
    # Check cache
    if cache['data'] and cache['timestamp']:
        age = (now - cache['timestamp']).total_seconds()
        if age < cache['ttl']:
            print("Returning cached data")
            return cache['data']
    
    print("Fetching fresh data...")
    
    # Fetch sheet data
    sheet_rows = get_sheet_data()
    
    # Fetch YouTube channel stats
    channel_stats = get_youtube_channel_stats()
    
    # Get video IDs and fetch views
    video_ids = [row['youtube_video_id'] for row in sheet_rows if row.get('youtube_video_id')]
    video_views = get_video_views(video_ids)
    
    # Add views to sheet rows
    for row in sheet_rows:
        video_id = row.get('youtube_video_id')
        if video_id:
            row['views'] = video_views.get(video_id, 0)
    
    # Calculate stats
    total_videos = len(sheet_rows)
    total_video_views = sum(row.get('views', 0) for row in sheet_rows)
    avg_views = total_video_views / total_videos if total_videos > 0 else 0
    
    # Videos by date
    today = datetime.now().date()
    videos_today = sum(1 for row in sheet_rows if row.get('timestamp', '').startswith(str(today)))
    
    # This week
    week_ago = today - timedelta(days=7)
    videos_this_week = sum(1 for row in sheet_rows 
                          if row.get('timestamp', '') and 
                          datetime.strptime(row['timestamp'].split()[0], '%Y-%m-%d').date() >= week_ago)
    
    # This month
    month_start = today.replace(day=1)
    videos_this_month = sum(1 for row in sheet_rows 
                           if row.get('timestamp', '') and 
                           datetime.strptime(row['timestamp'].split()[0], '%Y-%m-%d').date() >= month_start)
    
    # Most used music creators
    creator_counts = {}
    for row in sheet_rows:
        creator = row.get('music_creator', 'Unknown')
        creator_counts[creator] = creator_counts.get(creator, 0) + 1
    
    top_creators = sorted(creator_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    
    # Prepare response
    data = {
        'stats': {
            'total_videos': total_videos,
            'videos_today': videos_today,
            'videos_this_week': videos_this_week,
            'videos_this_month': videos_this_month,
            'subscribers': channel_stats['subscribers'],
            'total_views': total_video_views,
            'avg_views_per_video': round(avg_views, 1),
            'channel_total_views': channel_stats['total_views']
        },
        'videos': sheet_rows[-20:],  # Last 20 videos
        'top_creators': [{'name': name, 'count': count} for name, count in top_creators],
        'last_updated': now.strftime('%Y-%m-%d %H:%M:%S')
    }
    
    # Update cache
    cache['data'] = data
    cache['timestamp'] = now
    
    return data

@app.route('/')
def index():
    """Serve dashboard page"""
    return render_template('index.html')

@app.route('/api/dashboard')
def dashboard_api():
    """API endpoint for dashboard data"""
    data = get_dashboard_data()
    return jsonify(data)

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({'status': 'ok', 'service': 'youtube-dashboard', 'version': '1.0'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
