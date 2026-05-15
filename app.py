import os
import secrets
import uuid
from datetime import datetime, timedelta

import psycopg2
import requests
from dotenv import load_dotenv
from flask import Flask, redirect, request, session, render_template, url_for
from psycopg2.extras import RealDictCursor

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
REDIRECT_URI = os.getenv("TWITCH_REDIRECT_URI")
DATABASE_URL = os.getenv("DATABASE_URL")

AUTH_URL = "https://id.twitch.tv/oauth2/authorize"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"
HELIX_URL = "https://api.twitch.tv/helix"


def get_db_connection():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is missing from environment variables.")

    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def init_db():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            twitch_user_id TEXT UNIQUE NOT NULL,
            twitch_login TEXT NOT NULL,
            display_name TEXT NOT NULL,
            access_token TEXT NOT NULL,
            refresh_token TEXT,
            token_expires_at TIMESTAMP,
            streamdeck_key TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    conn.commit()
    cur.close()
    conn.close()


def save_user_token(user, token_json):
    access_token = token_json["access_token"]
    refresh_token = token_json.get("refresh_token")
    expires_in = token_json.get("expires_in", 0)
    token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT streamdeck_key FROM users WHERE twitch_user_id = %s;",
        (user["id"],)
    )

    existing_user = cur.fetchone()
    streamdeck_key = existing_user["streamdeck_key"] if existing_user else str(uuid.uuid4())

    cur.execute("""
        INSERT INTO users (
            twitch_user_id,
            twitch_login,
            display_name,
            access_token,
            refresh_token,
            token_expires_at,
            streamdeck_key,
            updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (twitch_user_id)
        DO UPDATE SET
            twitch_login = EXCLUDED.twitch_login,
            display_name = EXCLUDED.display_name,
            access_token = EXCLUDED.access_token,
            refresh_token = EXCLUDED.refresh_token,
            token_expires_at = EXCLUDED.token_expires_at,
            updated_at = CURRENT_TIMESTAMP
        RETURNING streamdeck_key;
    """, (
        user["id"],
        user["login"],
        user["display_name"],
        access_token,
        refresh_token,
        token_expires_at,
        streamdeck_key
    ))

    result = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    return result["streamdeck_key"]


def get_user_by_streamdeck_key(streamdeck_key):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM users WHERE streamdeck_key = %s;",
        (streamdeck_key,)
    )

    user = cur.fetchone()

    cur.close()
    conn.close()

    return user


def refresh_user_token(user):
    refresh_token = user.get("refresh_token")

    if not refresh_token:
        return None

    response = requests.post(
        TOKEN_URL,
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token
        }
    )

    token_json = response.json()

    if response.status_code != 200:
        return None

    access_token = token_json["access_token"]
    new_refresh_token = token_json.get("refresh_token", refresh_token)
    expires_in = token_json.get("expires_in", 0)
    token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE users
        SET access_token = %s,
            refresh_token = %s,
            token_expires_at = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE twitch_user_id = %s
        RETURNING *;
    """, (
        access_token,
        new_refresh_token,
        token_expires_at,
        user["twitch_user_id"]
    ))

    updated_user = cur.fetchone()

    conn.commit()
    cur.close()
    conn.close()

    return updated_user


def get_valid_user_token(user):
    expires_at = user.get("token_expires_at")

    if not expires_at:
        return user

    if datetime.utcnow() >= expires_at:
        refreshed_user = refresh_user_token(user)

        if refreshed_user:
            return refreshed_user

    return user


@app.route("/", methods=["GET", "HEAD"])
def index():
    if request.method == "HEAD":
        return "", 200

    is_connected = "access_token" in session
    live_status = False

    if is_connected:
        live_status = check_live_status(session["twitch_user_id"])

    return render_template(
        "index.html",
        is_connected=is_connected,
        display_name=session.get("display_name"),
        twitch_login=session.get("twitch_login"),
        twitch_user_id=session.get("twitch_user_id"),
        live_status=live_status,
        streamdeck_key=session.get("streamdeck_key")
    )


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

    token_response = requests.post(
        TOKEN_URL,
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI
        }
    )

    token_json = token_response.json()

    if token_response.status_code != 200:
        return token_json, 400

    session["access_token"] = token_json["access_token"]

    user = get_twitch_user()
    streamdeck_key = save_user_token(user, token_json)

    session["twitch_user_id"] = user["id"]
    session["display_name"] = user["display_name"]
    session["twitch_login"] = user["login"]
    session["streamdeck_key"] = streamdeck_key

    return redirect(url_for("index"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/clip-now")
def clip_now():
    if "access_token" not in session:
        return redirect(url_for("index"))

    return create_clip()


@app.route("/clip-now/<streamdeck_key>")
def clip_now_with_key(streamdeck_key):
    user = get_user_by_streamdeck_key(streamdeck_key)

    if not user:
        return {"error": "Invalid Stream Deck key"}, 401

    user = get_valid_user_token(user)

    session["access_token"] = user["access_token"]
    session["twitch_user_id"] = user["twitch_user_id"]
    session["display_name"] = user["display_name"]
    session["twitch_login"] = user["twitch_login"]
    session["streamdeck_key"] = user["streamdeck_key"]

    return create_clip()


@app.route("/create-clip", methods=["GET", "POST"])
def create_clip():
    if "access_token" not in session:
        return redirect(url_for("index"))

    response = requests.post(
        f"{HELIX_URL}/clips",
        headers=get_headers(),
        params={
            "broadcaster_id": session["twitch_user_id"]
        }
    )

    data = response.json()

    if response.status_code != 202:
        return data, 400

    clip_id = data["data"][0]["id"]
    clip_url = f"https://clips.twitch.tv/{clip_id}"

    chat_message = f"🔥 New Clip! Watch it here: {clip_url}"
    chat_success, chat_response = send_chat_message(chat_message)

    return render_template(
        "clip_result.html",
        clip_url=clip_url,
        chat_success=chat_success
    )


def get_headers():
    return {
        "Authorization": f"Bearer {session['access_token']}",
        "Client-Id": CLIENT_ID
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


def send_chat_message(message):
    response = requests.post(
        f"{HELIX_URL}/chat/messages",
        headers={
            "Authorization": f"Bearer {session['access_token']}",
            "Client-Id": CLIENT_ID,
            "Content-Type": "application/json"
        },
        json={
            "broadcaster_id": session["twitch_user_id"],
            "sender_id": session["twitch_user_id"],
            "message": message
        }
    )

    return response.status_code == 200, response.json()


init_db()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=True
    )