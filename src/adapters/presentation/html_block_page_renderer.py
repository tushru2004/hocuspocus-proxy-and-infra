"""HTML block page renderer."""


class HTMLBlockPageRenderer:
    """Renders block pages as HTML."""

    def render_location_block_page(self, location_name: str) -> str:
        """Render location-based block page."""
        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Browsing Blocked</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            margin: 0;
            padding: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
        }}
        .container {{
            background: white;
            border-radius: 20px;
            padding: 40px;
            max-width: 500px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            text-align: center;
        }}
        .emoji {{
            font-size: 80px;
            margin-bottom: 20px;
        }}
        h1 {{
            color: #333;
            margin: 0 0 10px 0;
            font-size: 28px;
        }}
        .location {{
            color: #666;
            font-size: 16px;
            margin: 10px 0 20px 0;
        }}
        p {{
            color: #666;
            line-height: 1.6;
            margin: 20px 0;
        }}
        .note {{
            background: #f0f0f0;
            padding: 15px;
            border-radius: 10px;
            font-size: 14px;
            margin-top: 20px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="emoji">🚫</div>
        <h1>Browsing Blocked</h1>
        <div class="location">📍 {location_name}</div>
        <p>You are currently at a blocked location. Internet browsing is not allowed at this location.</p>
        <p>To browse websites, please move to a different location.</p>
        <div class="note">
            <strong>Note:</strong> Essential services (Apple, iCloud) remain accessible.
        </div>
    </div>
</body>
</html>"""

    def render_domain_block_page(self, domain: str) -> str:
        """Render domain block page."""
        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Access Denied</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            margin: 0;
            padding: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
        }}
        .container {{
            background: white;
            border-radius: 20px;
            padding: 40px;
            max-width: 500px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            text-align: center;
        }}
        .emoji {{
            font-size: 80px;
            margin-bottom: 20px;
        }}
        h1 {{
            color: #333;
            margin: 0 0 10px 0;
            font-size: 28px;
        }}
        .domain {{
            color: #666;
            font-size: 16px;
            margin: 10px 0 20px 0;
            font-family: monospace;
        }}
        p {{
            color: #666;
            line-height: 1.6;
            margin: 20px 0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="emoji">⛔</div>
        <h1>Access Denied</h1>
        <div class="domain">{domain}</div>
        <p>This domain is not whitelisted. Only approved domains are accessible.</p>
    </div>
</body>
</html>"""

    def render_youtube_block_page(self, channel_name: str = None) -> str:
        """Render YouTube channel block page."""
        channel_info = f"Channel: {channel_name}" if channel_name else "This channel"
        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>YouTube Video Blocked</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: linear-gradient(135deg, #ff0000 0%, #cc0000 100%);
            margin: 0;
            padding: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
        }}
        .container {{
            background: white;
            border-radius: 20px;
            padding: 40px;
            max-width: 500px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            text-align: center;
        }}
        .emoji {{
            font-size: 80px;
            margin-bottom: 20px;
        }}
        h1 {{
            color: #333;
            margin: 0 0 10px 0;
            font-size: 28px;
        }}
        .channel {{
            color: #666;
            font-size: 16px;
            margin: 10px 0 20px 0;
        }}
        p {{
            color: #666;
            line-height: 1.6;
            margin: 20px 0;
        }}
        .note {{
            background: #f0f0f0;
            padding: 15px;
            border-radius: 10px;
            font-size: 14px;
            margin-top: 20px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="emoji">📺</div>
        <h1>YouTube Video Blocked</h1>
        <div class="channel">{channel_info}</div>
        <p>This YouTube channel is not in your allowed list. Only videos from approved channels can be played.</p>
        <div class="note">
            <strong>Tip:</strong> Ask your administrator to add this channel if you need access.
        </div>
    </div>
</body>
</html>"""

    def render_no_location_block_page(self) -> str:
        """Render block page when no location data is available from any device."""
        return """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Location Required</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: linear-gradient(135deg, #ff6b6b 0%, #ee5a24 100%);
            margin: 0;
            padding: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
        }
        .container {
            background: white;
            border-radius: 20px;
            padding: 40px;
            max-width: 500px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            text-align: center;
        }
        .emoji {
            font-size: 80px;
            margin-bottom: 20px;
        }
        h1 {
            color: #333;
            margin: 0 0 10px 0;
            font-size: 28px;
        }
        .subtitle {
            color: #ee5a24;
            font-size: 16px;
            font-weight: 600;
            margin: 10px 0 20px 0;
        }
        p {
            color: #666;
            line-height: 1.6;
            margin: 20px 0;
        }
        .warning {
            background: #fff3cd;
            border: 1px solid #ffc107;
            padding: 15px;
            border-radius: 10px;
            font-size: 14px;
            margin-top: 20px;
            color: #856404;
        }
        .note {
            background: #f0f0f0;
            padding: 15px;
            border-radius: 10px;
            font-size: 14px;
            margin-top: 15px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="emoji">📍</div>
        <h1>Location Data Required</h1>
        <div class="subtitle">No device location received</div>
        <p>Internet access requires location verification. This device has not reported its location recently.</p>
        <div class="warning">
            <strong>Possible causes:</strong><br>
            - Location services disabled on this device<br>
            - SimpleMDM app not running or not reporting location<br>
            - Location data expired (older than 5 minutes)
        </div>
        <div class="note">
            <strong>To restore access:</strong> Open the SimpleMDM app and ensure location services are enabled for it in Settings.
        </div>
    </div>
</body>
</html>"""
