def fetch_avatar(request):
    # Old static local avatar
    #return "/static/default_avatar.png"
    # New feature: Allow users to specify custom avatar URL
    avatar_url = request.json.get("avatar_url")
    
    # SSRF Vulnerability: Requests fetches whatever URL the user provides
    # without validating if it is an internal/localhost IP or a private range.
    response = requests.get(avatar_url, timeout=5)
    return response.content