import json
from flask import Flask, request, redirect, g, render_template
import requests
import base64
import urllib
import math
import random

# Authentication Steps, paramaters, and responses are defined at https://developer.spotify.com/web-api/authorization-guide/
# Visit this url to see all the steps, parameters, and expected response. 


app = Flask(__name__) # initiate Flask application

#  Client Keys
CLIENT_ID = "a79663a2973a4ff9b1bc9e7966c21685"
CLIENT_SECRET = "d326e95d70e747b8930b37e09983c210"

# Spotify URLS
SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_BASE_URL = "https://api.spotify.com"
API_VERSION = "v1"
SPOTIFY_API_URL = "{}/{}".format(SPOTIFY_API_BASE_URL, API_VERSION)


# Server-side Parameters
CLIENT_SIDE_URL = "http://127.0.0.1"
PORT = 8080
REDIRECT_URI = "{}:{}/callback/q".format(CLIENT_SIDE_URL, PORT)
SCOPE = "user-read-private user-read-email"
STATEKEY = "spotify_auth_state"
# SHOW_DIALOG_bool = True
# SHOW_DIALOG_str = str(SHOW_DIALOG_bool).lower()

def generateRandomString(length):
    text = ""
    possible = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'

    for i in range(length):
        text += possible[int(math.floor(random.random() * len(possible)))]
    return text

@app.route("/")
def index():
    # Auth Step 1: Authorization
    state = generateRandomString(16)
    print(state) # DEBUG
    auth_query_parameters = {
    "response_type": "code",
    "redirect_uri": REDIRECT_URI,
    "scope": SCOPE,
    "state": state,
    # "show_dialog": SHOW_DIALOG_str,
    "client_id": CLIENT_ID
    }

    url_args = "&".join(["{}={}".format(key,urllib.quote(val)) for key,val in auth_query_parameters.iteritems()])
    auth_url = "{}/?{}".format(SPOTIFY_AUTH_URL, url_args)
    print("redirecting...") # DEBUG
    return redirect(auth_url)


@app.route("/callback/q")
def callback():
    '''
    TODO: add error check for state matching (see express example)
    '''
    # Auth Step 4: Your application requests refresh and access tokens
    auth_token = request.args['code']
    code_payload = {
        "grant_type": "authorization_code",
        "code": str(auth_token),
        "redirect_uri": REDIRECT_URI
    }
    base64encoded = base64.b64encode("{}:{}".format(CLIENT_ID, CLIENT_SECRET))
    headers = {"Authorization": "Basic {}".format(base64encoded)}
    post_request = requests.post(SPOTIFY_TOKEN_URL, data=code_payload, headers=headers)

    # Auth Step 5: Tokens are Returned to Application
    response_data = json.loads(post_request.text)
    access_token = response_data["access_token"]
    refresh_token = response_data["refresh_token"]
    token_type = response_data["token_type"]
    expires_in = response_data["expires_in"]

    # Auth Step 6: Use the access token to access Spotify API
    authorization_header = {"Authorization":"Bearer {}".format(access_token)}

    # Get profile data
    user_profile_api_endpoint = "{}/me".format(SPOTIFY_API_URL)
    profile_response = requests.get(user_profile_api_endpoint, headers=authorization_header)
    profile_data = json.loads(profile_response.text)
    '''
    # Get user playlist data
    playlist_api_endpoint = "{}/playlists".format(profile_data["href"])
    playlists_response = requests.get(playlist_api_endpoint, headers=authorization_header)
    playlist_data = json.loads(playlists_response.text)
    '''
    # Display profile data
    display_arr = [profile_data]#+ playlist_data["items"]
    print(display_arr)
    return render_template("index.html",sorted_array=display_arr)


if __name__ == "__main__":
    app.run(port=PORT)
