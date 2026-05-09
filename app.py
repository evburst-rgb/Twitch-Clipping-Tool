import os
import secrets
import requests

from flask import (
    Flask,
    redirect,
    request,
    session,
    render_template,
    url_for
)

app = Flask(__name__)

from dotenv import load_dotenv

load_dotenv()


app.secret_key = os.getenv("FLASK_SECRET_KEY")

CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
REDIRECT_URI = os.getenv("TWITCH_REDIRECT_URI")

AUTH_URL = "https://id.twitch.tv/oauth2/authorize"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"
HELIX_URL = "https://api.twitch.tv/helix"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/login")
def login():

    state = secrets.token_urlsafe(16)

    session["oauth_state"] = state

    scopes = [
        "clips:edit",
        "user:read:chat",
        "user:write:chat"
    ]

    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(scopes),
        "state": state
    }

    query = requests.compat.urlencode(params)

    return redirect(f"{AUTH_URL}?{query}")


@app.route("/callback")
def callback():

    error = request.args.get("error")

    if error:
        return f"""
        Twitch Login Error: {error}<br>
        {request.args.get("error_description")}
        """, 400

    code = request.args.get("code")
    state = request.args.get("state")

    if state != session.get("oauth_state"):
        return "Invalid OAuth state.", 400

    token_data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI
    }

    token_response = requests.post(
        TOKEN_URL,
        data=token_data
    )

    token_json = token_response.json()

    if token_response.status_code != 200:
        return token_json, 400

    session["access_token"] = token_json["access_token"]

    user = get_twitch_user()

    session["twitch_user_id"] = user["id"]
    session["display_name"] = user["display_name"]
    session["twitch_login"] = user["login"]

    return redirect(url_for("dashboard"))


@app.route("/dashboard")
def dashboard():

    if "access_token" not in session:
        return redirect(url_for("index"))

    live_status = check_live_status(
        session["twitch_user_id"]
    )

    return render_template(
        "dashboard.html",
        display_name=session["display_name"],
        twitch_login=session["twitch_login"],
        live_status=live_status
    )


@app.route("/create-clip", methods=["POST"])
def create_clip():

    if "access_token" not in session:
        return redirect(url_for("index"))

    response = requests.post(
        f"{HELIX_URL}/clips",
        headers=get_headers(),
        params={
            "broadcaster_id":
            session["twitch_user_id"]
        }
    )

    data = response.json()

    if response.status_code != 202:
        return data, 400

    clip_id = data["data"][0]["id"]

    clip_url = f"https://clips.twitch.tv/{clip_id}"

    return f"""
    <h2>Clip Created!</h2>

    <p>
        <a href="{clip_url}" target="_blank">
            View Clip
        </a>
    </p>

    <a href="/dashboard">
        Back to Dashboard
    </a>
    """


def get_headers():

    return {
        "Authorization":
        f"Bearer {session['access_token']}",

        "Client-Id":
        CLIENT_ID
    }


def get_twitch_user():

    response = requests.get(
        f"{HELIX_URL}/users",
        headers=get_headers()
    )

    data = response.json()

    return data["data"][0]


def check_live_status(user_id):

    response = requests.get(
        f"{HELIX_URL}/streams",
        headers=get_headers(),
        params={
            "user_id": user_id
        }
    )

    data = response.json()

    return len(data.get("data", [])) > 0


if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=True
    )