from flask import Flask, request, jsonify, send_from_directory
from supabase import create_client
from dotenv import load_dotenv
from datetime import datetime, timezone
import requests
import os

load_dotenv()

app = Flask(__name__, static_folder="static")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SMSO_API_KEY = os.getenv("SMSO_API_KEY")
SMSO_SENDER = os.getenv("SMSO_SENDER", "Parinte")
PARENT_PHONE = os.getenv("PARENT_PHONE")

if not SUPABASE_URL:
    raise ValueError("Lipseste SUPABASE_URL din .env")

if not SUPABASE_KEY:
    raise ValueError("Lipseste SUPABASE_KEY din .env")

if not SMSO_API_KEY:
    raise ValueError("Lipseste SMSO_API_KEY din .env")

if not PARENT_PHONE:
    raise ValueError("Lipseste PARENT_PHONE din .env")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


@app.route("/")
def serve_pwa():
    return send_from_directory("static", "index.html")


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/location", methods=["POST"])
def save_location():
    try:
        data = request.get_json(force=True, silent=True) or {}

        print("LOCATION PAYLOAD:", data)

        phone = (data.get("phone") or "").strip()
        lat = data.get("lat")
        lng = data.get("lng")

        if not phone or lat is None or lng is None:
            return jsonify({
                "status": "error",
                "message": "phone, lat si lng sunt obligatorii"
            }), 400

        result = supabase.table("locations").upsert(
            {
                "phone": phone,
                "lat": lat,
                "lng": lng,
                "updated_at": datetime.now(timezone.utc).isoformat()
            },
            on_conflict="phone"
        ).execute()

        print("SAVE LOCATION RESULT:", result)

        maps_link = f"https://maps.google.com/?q={lat},{lng}"
        sms_text = f"Locatia copilului ({phone}):\n\n{maps_link}"
        send_sms(PARENT_PHONE, sms_text)

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        print("SAVE LOCATION ERROR:", str(e))
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@app.route("/webhook", methods=["POST"])
def sms_received():
    try:
        data = request.get_json(force=True, silent=True) or {}

        print("RAW JSON:", data)
        print("RAW FORM:", request.form.to_dict(flat=False))

        phone = (
            data.get("from")
            or request.form.get("sender[number]")
            or request.form.get("from")
            or request.form.get("sender")
            or ""
        ).strip()

        body = (
            data.get("message")
            or data.get("body")
            or request.form.get("body")
            or request.form.get("message")
            or ""
        ).strip()

        if not phone:
            return jsonify({"status": "no phone"}), 200

        result = supabase.table("locations").select("*").eq("phone", phone).limit(1).execute()

        print("SUPABASE SELECT RESULT:", result)

        if result.data:
            loc = result.data[0]
            maps_link = f"https://maps.google.com/?q={loc['lat']},{loc['lng']}"
            sms_text = f'Copilul ({phone}) a raspuns: "{body}"\n\n{maps_link}'
        else:
            sms_text = f'Copilul ({phone}) a raspuns: "{body}"\nLocatia nu e disponibila.'

        send_sms(PARENT_PHONE, sms_text)

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        print("WEBHOOK ERROR:", str(e))
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


def send_sms(to, message):
    response = requests.post(
        "https://app.smso.ro/api/v1/send",
        headers={"X-Authorization": SMSO_API_KEY},
        data={
            "to": to,
            "body": message,
            "sender": SMSO_SENDER
        },
        timeout=15
    )

    print("SMSO STATUS:", response.status_code)
    print("SMSO RESPONSE:", response.text)

    response.raise_for_status()
    return response


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)
