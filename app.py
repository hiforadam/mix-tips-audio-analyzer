import streamlit as st  # type: ignore
import soundfile as sf  # type: ignore
import numpy as np  # type: ignore
from datetime import datetime
import os
import re
import json
import hashlib
from pathlib import Path
import tempfile

# ========== PATHS ==========
APP_ROOT = Path(__file__).parent.resolve()
USER_DATA_DIR = APP_ROOT / "user_data"
UPLOADS_DIR = APP_ROOT / "uploads"
USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

JSON_PATH = USER_DATA_DIR / "all_feedbacks.json"

# ========== HELPERS ==========

def is_valid_email(email: str) -> bool:
    pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    return re.match(pattern, email) is not None

def safe_filename(s: str) -> str:
    s = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', s)
    return s[:64]

def _load_records() -> list:
    if JSON_PATH.exists() and JSON_PATH.stat().st_size > 0:
        try:
            with JSON_PATH.open('r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return []

def _write_records(data: list) -> None:
    with JSON_PATH.open('w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def compute_file_hash(file_path: Path) -> str:
    """SHA1 קצר עבור זיהוי תוכן (10 תווים)"""
    h = hashlib.sha1()
    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()[:10]

def find_record_index(email: str, file_hash: str) -> int | None:
    data = _load_records()
    for i, rec in enumerate(data):
        if rec.get("email") == email and rec.get("file_hash") == file_hash:
            return i
    return None

def get_next_project_number(email: str) -> int:
    """מספר הפרויקט הבא עבור משתמש לפי מה ששמור ב-JSON."""
    data = _load_records()
    max_n = 0
    for rec in data:
        if rec.get("email") == email:
            fname = rec.get("filename", "")
            m = re.search(r'__project_(\d+)\.', fname)
            if m:
                n = int(m.group(1))
                if n > max_n:
                    max_n = n
    return max_n + 1

def build_project_filename(email: str, project_num: int, ext: str) -> Path:
    email_part = safe_filename(email.split("@")[0]) if email else "anon"
    return UPLOADS_DIR / f"{email_part}__project_{project_num}{ext}"

def save_or_update_record(email: str, record: dict) -> None:
    """מעדכן רשומה קיימת לפי (email + file_hash) או יוצר חדשה אם אין."""
    data = _load_records()
    idx = None
    fh = record.get("file_hash")
    if fh:
        for i, rec in enumerate(data):
            if rec.get("email") == email and rec.get("file_hash") == fh:
                idx = i
                break

    now_iso = datetime.now().isoformat()
    if idx is None:
        record["created_at"] = now_iso
        record["updated_at"] = now_iso
        data.append(record)
    else:
        # עדכון במקום—לא יוצרים רשומה כפולה
        data[idx].update(record)
        data[idx]["updated_at"] = now_iso

    _write_records(data)

# ========== PROFESSIONAL TIPS ==========
def professional_tips(lufs, peak, crest, centroid, dominant_freq):
    tips = []
    main_tip = ""
    explanation = []

    if lufs > -11.5:
        tips.append(f"High loudness ({lufs:.2f} LUFS). It's recommended to reduce master volume/limiter to about -13~-14 LUFS to avoid distortion and automatic volume reduction on streaming platforms.")
        main_tip = "Loudness is too high – possible distortion/volume reduction."
        explanation.append("LUFS represents perceived loudness. Too high values will cause platforms like Spotify to reduce volume automatically, possibly causing distortion.")
    elif lufs < -15.5:
        tips.append(f"Low loudness ({lufs:.2f} LUFS). Consider raising volume or remastering to make the mix stand out.")
        main_tip = "Loudness is low – mix won't stand out compared to others."
        explanation.append("Low LUFS means the track sounds weak compared to others, especially in playlists.")
    else:
        tips.append(f"Average loudness is normal ({lufs:.2f} LUFS) – great!")
        explanation.append("Loudness is within normal range, but make sure other parameters are good too.")

    if peak > 0.98:
        tips.append(f"High peak value ({peak:.2f}). Recommended to lower to -0.5dBFS to avoid clipping or distortion.")
        if not main_tip:
            main_tip = "High peak – risk of clipping/distortion."
        explanation.append("High peak values mean audio signal touches upper limit, risking digital distortion.")
    elif peak < 0.7:
        tips.append(f"Low peak value ({peak:.2f}). Consider increasing gain to utilize dynamic range.")
        explanation.append("Low peak means mix isn't utilizing full dynamic range – master gain can be raised.")
    else:
        tips.append(f"Peak level is within a healthy range ({peak:.2f}).")

    if crest < 3:
        tips.append(f"Low Crest Factor ({crest:.2f}). Mix is too compressed – try reducing compression/limiter.")
        if not main_tip:
            main_tip = "Mix is over-compressed – loss of dynamics."
        explanation.append("Low Crest Factor indicates small difference between peaks and noise floor, meaning heavy compression.")
    elif crest > 6:
        tips.append(f"High Crest Factor ({crest:.2f}). Mix is very dynamic – might need compression.")
        explanation.append("High Crest Factor is typical for classical or soundtrack music; if not, mix might be too soft.")
    else:
        tips.append(f"Crest Factor is within normal range ({crest:.2f}).")

    if dominant_freq < 80:
        tips.append(f"Bass dominant frequency ({dominant_freq:.1f}Hz). Check for muddy build-up in 20–80Hz range.")
        explanation.append("Very low dominant frequency suggests bass is overpowering. Use headphones and EQ to check.")
    elif dominant_freq > 3000:
        tips.append(f"High frequency dominant ({dominant_freq:.1f}Hz). Possibly too much high-end boost.")
        explanation.append("High dominant frequency can cause harshness and listener fatigue. Balance highs and lows.")
    else:
        tips.append(f"Dominant frequency is within a healthy range ({dominant_freq:.1f}Hz).")

    if centroid < 1400:
        tips.append(f"Low spectral centroid ({centroid:.1f}Hz). Consider adding brightness (EQ around 2kHz-7kHz).")
        explanation.append("Low centroid results in a 'dark' mix; sometimes a bit of brightness is desired for modern sound.")
    elif centroid > 4800:
        tips.append(f"High spectral centroid ({centroid:.1f}Hz). High-end is dominant – consider EQ adjustments.")
        explanation.append("Too high centroid makes mix sound 'sharp' or 'thin', which can be unpleasant for long listening.")
    else:
        tips.append(f"Spectral centroid is balanced ({centroid:.1f}Hz).")

    if not main_tip:
        main_tip = "Your mix is balanced and excellent! Keep it up."
    return main_tip, tips, explanation

# ========== UI & LOGIC ==========

st.set_page_config(page_title="Smart Mixing Tips", layout="centered")

if 'email_ok' not in st.session_state:
    st.session_state['email_ok'] = False

if not st.session_state['email_ok']:
    st.markdown("""
    <div style='
        text-align:left;
        direction:ltr;
        background: #fff;
        color:#181818;
        font-weight:900;
        font-size:2.05em;
        border-radius:15px;
        padding: 20px 0 12px 8px;
        box-shadow: 0 1px 12px #e7e5e4;
        margin-bottom:20px;'
    >
    🎧 Smart Mixing Tips – Automatic Audio File Feedback
    </div>
    """, unsafe_allow_html=True)
    st.write("Before proceeding – please enter your email address to gain access:")
    email = st.text_input("Enter your email address (required):")
    if st.button("Continue"):
        if is_valid_email(email):
            st.session_state['email_ok'] = True
            st.session_state['user_email'] = email
            # רישום "פתיחת סשן" מינימלי
            save_or_update_record(email, {"email": email})
            st.success("Email received – you may continue!")
        else:
            st.error("Please enter a valid email address.")
    if not st.session_state['email_ok']:
        st.stop()

# שדות דאטה איכותית
uploaded_file = st.file_uploader("Upload audio file (WAV/MP3)", type=["wav", "mp3"])
genre = st.text_input("Genre (optional, e.g., Pop, Rock, Trap, Techno, etc.)")
project_stage = st.selectbox("שלב הפרויקט:", ["דמו", "מיקס", "מאסטר", "בדיקת רפרנס", "סופי", "אחר"])

if uploaded_file:
    try:
        st.info("🔎 Analysis may take a few seconds. Please wait...")

        email = st.session_state.get('user_email', 'anon')
        ext = Path(uploaded_file.name).suffix.lower()
        tmp = UPLOADS_DIR / f"__tmp{ext}"
        with open(tmp, "wb") as f:
            f.write(uploaded_file.read())

        file_hash = compute_file_hash(tmp)

        # האם יש כבר רשומה עבור אותו תוכן?
        idx = find_record_index(email, file_hash)
        data = _load_records()

        if idx is not None:
            # יש רשומה קודמת – משתמשים באותו שם קובץ, מחליפים תוכן
            existing_filename = data[idx].get("filename")
            if existing_filename:
                final_path = UPLOADS_DIR / existing_filename
            else:
                # אם משום מה חסר, בונים שם לפי מס' הפרויקט הבא (fallback)
                n = get_next_project_number(email)
                final_path = build_project_filename(email, n, ext)
        else:
            # אין רשומה – פרויקט חדש עם מספור עוקב
            n = get_next_project_number(email)
            final_path = build_project_filename(email, n, ext)

        # מחליפים/יוצרים את הקובץ הסופי בלי שכפולים
        os.replace(tmp, final_path)

        # ניתוח
        data_arr, samplerate = sf.read(final_path)
        if data_arr.ndim > 1:
            data_arr = np.mean(data_arr, axis=1)
        duration = len(data_arr) / samplerate
        rms = float(np.sqrt(np.mean(data_arr**2)))
        peak = float(np.max(np.abs(data_arr)))
        crest_factor = float(peak / (rms + 1e-12))
        lufs = float(20 * np.log10(rms + 1e-12))
        spectrum = np.abs(np.fft.rfft(data_arr))
        freqs = np.fft.rfftfreq(len(data_arr), 1/samplerate)
        centroid = float(np.sum(freqs * spectrum) / (np.sum(spectrum) + 1e-12))
        dominant_freq = float(freqs[np.argmax(spectrum)])

        # מציגים רק את התוכן החשוב (ללא הודעת "File loaded successfully")
        main_tip, tips, explanation = professional_tips(lufs, peak, crest_factor, centroid, dominant_freq)
        st.markdown(
            f"<div dir='ltr' style='text-align:left; background:#fefce8; color:#bb8504; padding:17px; border-radius:16px; margin-top:13px; font-size:1.18em; font-weight:bold; border:2px solid #fde68a;'>"
            f"{main_tip}"
            f"</div>",
            unsafe_allow_html=True
        )
        st.markdown("<div dir='ltr' style='text-align:left; font-size:1.13em; margin-top:13px; color:#111'><b>Professional Recommendations for this Mix:</b></div>", unsafe_allow_html=True)
        tips_html = "<div dir='ltr' style='text-align:left; font-size: 1.09em; background:#fff; color:#232323; padding:11px 8px 2px 0; border-radius:9px; margin-bottom:13px;'>"
        for tip in tips:
            tips_html += f"• {tip}<br>"
        tips_html += "</div>"
        st.markdown(tips_html, unsafe_allow_html=True)

        with st.expander("📋 Summary for copy/share:"):
            summary = f"""<div dir='ltr' style='text-align:left; font-family:inherit; color:#222; background:#f8fafc; padding:12px; border-radius:10px'>
<b>Auto Summary:</b><br>
Loudness (LUFS): {lufs:.2f}<br>
Peak: {peak:.2f}<br>
Crest Factor: {crest_factor:.2f}<br>
Dominant Frequency: {dominant_freq:.0f}Hz<br>
Centroid: {centroid:.0f}Hz<br>
Genre: {genre}<br>
Project Stage: {project_stage}<br>
<br>
<b>Main Tip:</b><br>
{main_tip}<br>
<br>
<b>Additional Recommendations:</b><br>
- {'<br>- '.join(tips)}
</div>
"""
            st.markdown(summary, unsafe_allow_html=True)

        # נשמור/נעדכן את הרשומה (ללא CSV)
        record = {
            'email': email,
            'file_hash': file_hash,
            'filename': final_path.name,
            'duration': duration,
            'lufs': lufs,
            'peak': peak,
            'crest_factor': crest_factor,
            'centroid': centroid,
            'dominant_freq': dominant_freq,
            'main_tip': main_tip,
            'tips': "; ".join(tips),
            'genre': genre,
            'project_stage': project_stage,
        }
        save_or_update_record(email, record)

        # נחזיק מזהים בסשן כדי ש-"Submit feedback" יעדכן את אותה רשומה
        st.session_state["current_file_hash"] = file_hash
        st.session_state["current_filename"] = final_path.name

        st.markdown("<div dir='ltr' style='text-align:left; color:#166534; font-size:1.06em; margin-bottom:7px; margin-top:20px;'>Your feedback will improve the system!</div>", unsafe_allow_html=True)

        # --- FEEDBACK ---
        feedback_purpose = st.selectbox(
            "Why did you create/upload this file?",
            ["Just checking", "Submit to client", "Streaming upload", "Demo phase", "Professional consultation", "Contest/Prize", "Other (please specify)"]
        )
        feedback_purpose_free = ""
        if feedback_purpose == "Other (please specify)":
            feedback_purpose_free = st.text_input("Free text detail:")

        feedback_hardest = st.multiselect(
            "What bothers you most about your mix? (select multiple)",
            ["Bass", "Highs", "Dynamics", "Overall loudness", "Unclear sound", "No depth", "No live feeling", "Distortion/Clipping", "Other (please specify)"]
        )
        feedback_hardest_free = ""
        if "Other (please specify)" in feedback_hardest:
            feedback_hardest_free = st.text_input("Free text for problem/shortcoming:")

        self_rating = st.slider("Rate your satisfaction with the mix (1=Not satisfied at all, 10=Completely satisfied):", 1, 10, 7)
        reference = st.text_input("Is there a reference sound you want to achieve? (link/song name/youtube)")
        q1 = st.radio("Were the recommendations relevant?", ["Yes", "No", "Partially"])
        q2 = st.text_area("What would you like to improve in this analysis?", height=100)
        q3 = st.text_area("Any comments/requests – help us improve!", height=100)

        if st.button("Submit feedback"):
            # עדכון אותה רשומה – לא יצירת חדשה
            update_payload = {
                'email': email,
                'file_hash': st.session_state.get("current_file_hash"),
                'filename': st.session_state.get("current_filename"),
                'feedback_purpose': feedback_purpose,
                'feedback_purpose_free': feedback_purpose_free,
                'self_rating': self_rating,
                'feedback_hardest': '/'.join(feedback_hardest),
                'feedback_hardest_free': feedback_hardest_free,
                'reference': reference,
                'q1': q1,
                'q2': q2,
                'q3': q3,
            }
            save_or_update_record(email, update_payload)
            st.success("Thank you for your feedback! (Record updated, not duplicated).")

    except Exception as e:
        st.error(f"⚠️ Error: Unsupported or corrupted file ({e})")
else:
    st.markdown("<div style='direction:ltr; text-align:left; color:#232323; margin-top:14px; background:#fff; padding:8px; border-radius:8px'>Upload WAV or MP3 file only for analysis.</div>", unsafe_allow_html=True)