import os
import smtplib
import secrets
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
)
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from email_validator import validate_email, EmailNotValidError
from dotenv import load_dotenv

# .env betöltése
load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

MAIL_USERNAME = os.getenv("MAIL_USERNAME")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")


# --------------------
# Adatbázis modell
# --------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(150), nullable=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    role = db.Column(db.String(100), nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_confirmed = db.Column(db.Boolean, default=False)
    confirm_token = db.Column(db.String(100), nullable=True)


# --------------------
# E-mail küldés
# --------------------
def send_email(to_email: str, subject: str, body: str):
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        print("FIGYELEM: Nincs beállítva MAIL_USERNAME vagy MAIL_PASSWORD")
        return

    msg = MIMEMultipart()
    msg["From"] = MAIL_USERNAME
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
            server.send_message(msg)
        print(f"E-mail elküldve: {to_email}")
    except Exception as e:
        print("Hiba az e-mail küldésekor:", e)


def send_confirmation_email(to_email, token):
    confirm_url = url_for("confirm_email", token=token, _external=True)
    subject = "AI VideoGen – E-mail megerősítés"
    body = f"""
Szia!

Köszönjük a regisztrációdat az AI VideoGen demóhoz.

Kérlek, erősítsd meg az e-mail címedet az alábbi linkre kattintva:

{confirm_url}

Ha nem te regisztráltál, egyszerűen hagyd figyelmen kívül ezt az üzenetet.

Üdv,
AI VideoGen
"""
    send_email(to_email, subject, body)


def send_contact_email(name, email, subject_line, message):
    subject = f"AI VideoGen – új kapcsolatfelvétel: {subject_line}"
    body = f"""
Név: {name}
E-mail: {email}

Üzenet:
{message}
"""
    # ide a saját címedre küldjük
    send_email(MAIL_USERNAME, subject, body)


# --------------------
# Útvonalak
# --------------------
@app.before_first_request
def create_tables():
    db.create_all()


@app.route("/", methods=["GET"])
def index():
    logged_in = "user_id" in session
    user_email = None
    if logged_in:
        user = User.query.get(session["user_id"])
        user_email = user.email if user else None
    return render_template("index.html", logged_in=logged_in, user_email=user_email)


@app.route("/register", methods=["POST"])
def register():
    company_name = request.form.get("name")
    email = request.form.get("email")
    role = request.form.get("role")
    password = request.form.get("password")
    password2 = request.form.get("password2")

    if not email or not password or not password2:
        flash("Minden kötelező mezőt tölts ki!", "error")
        return redirect(url_for("index") + "#auth")

    if password != password2:
        flash("A két jelszó nem egyezik!", "error")
        return redirect(url_for("index") + "#auth")

    try:
        validate_email(email)
    except EmailNotValidError:
        flash("Érvénytelen e-mail cím.", "error")
        return redirect(url_for("index") + "#auth")

    existing = User.query.filter_by(email=email).first()
    if existing:
        flash("Ezzel az e-mail címmel már létezik fiók.", "error")
        return redirect(url_for("index") + "#auth")

    pw_hash = bcrypt.generate_password_hash(password).decode("utf-8")
    token = secrets.token_urlsafe(32)

    user = User(
        company_name=company_name,
        email=email,
        role=role,
        password_hash=pw_hash,
        is_confirmed=False,
        confirm_token=token,
    )

    db.session.add(user)
    db.session.commit()

    send_confirmation_email(email, token)

    flash("Sikeres regisztráció! Kérlek, erősítsd meg az e-mailedet.", "success")
    return redirect(url_for("index") + "#auth")


@app.route("/login", methods=["POST"])
def login():
    email = request.form.get("email")
    password = request.form.get("password")

    if not email or not password:
        flash("Add meg az e-mail címedet és a jelszavadat!", "error")
        return redirect(url_for("index") + "#auth")

    user = User.query.filter_by(email=email).first()
    if not user or not bcrypt.check_password_hash(user.password_hash, password):
        flash("Hibás e-mail vagy jelszó.", "error")
        return redirect(url_for("index") + "#auth")

    if not user.is_confirmed:
        flash("Kérlek, először erősítsd meg az e-mail címedet!", "error")
        return redirect(url_for("index") + "#auth")

    session["user_id"] = user.id
    flash("Sikeres belépés!", "success")
    return redirect(url_for("index"))


@app.route("/logout")
def logout():
    session.pop("user_id", None)
    flash("Kijelentkeztél.", "success")
    return redirect(url_for("index"))


@app.route("/confirm/<token>")
def confirm_email(token):
    user = User.query.filter_by(confirm_token=token).first()
    if not user:
        flash("Érvénytelen vagy lejárt megerősítő link.", "error")
        return redirect(url_for("index"))

    user.is_confirmed = True
    user.confirm_token = None
    db.session.commit()

    flash("Sikeresen megerősítetted az e-mail címed! Most már beléphetsz.", "success")
    return redirect(url_for("index") + "#auth")


@app.route("/contact", methods=["POST"])
def contact():
    name = request.form.get("name")
    email = request.form.get("email")
    subject_line = request.form.get("subject")
    message = request.form.get("message")

    if not name or not email or not subject_line or not message:
        flash("Kérlek, tölts ki minden mezőt a kapcsolatfelvételnél!", "error")
        return redirect(url_for("index") + "#contact")

    try:
        validate_email(email)
    except EmailNotValidError:
        flash("Érvénytelen e-mail cím a kapcsolatfelvételnél.", "error")
        return redirect(url_for("index") + "#contact")

    send_contact_email(name, email, subject_line, message)

    flash("Köszönjük az üzeneted, hamarosan jelentkezünk!", "success")
    return redirect(url_for("index") + "#contact")


if __name__ == "__main__":
    app.run(debug=True)
