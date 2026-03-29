from flask import Blueprint, request, jsonify
from flask_bcrypt import Bcrypt
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity

from database import db
from models import User

auth_bp = Blueprint("auth", __name__)
bcrypt = Bcrypt()


@auth_bp.route("/signup", methods=["POST"])
def signup():
    data = request.get_json(silent=True) or {}

    for field in ("name", "email", "password", "phone_number"):
        if not data.get(field, "").strip():
            return jsonify({"error": f"{field} is required"}), 400

    if not data["phone_number"].strip().startswith("+"):
        return jsonify({"error": "phone_number must be E.164 format (e.g. +12125551234)"}), 400

    if User.query.filter_by(email=data["email"].lower().strip()).first():
        return jsonify({"error": "Email already registered"}), 409

    user = User(
        name=data["name"].strip(),
        email=data["email"].lower().strip(),
        password_hash=bcrypt.generate_password_hash(data["password"]).decode("utf-8"),
        phone_number=data["phone_number"].strip(),
    )
    db.session.add(user)
    db.session.commit()

    token = create_access_token(identity=str(user.id))
    return jsonify({"access_token": token, "user": user.to_dict()}), 201


@auth_bp.route("/signin", methods=["POST"])
def signin():
    data = request.get_json(silent=True) or {}

    if not data.get("email") or not data.get("password"):
        return jsonify({"error": "email and password are required"}), 400

    user = User.query.filter_by(email=data["email"].lower().strip()).first()
    if not user or not bcrypt.check_password_hash(user.password_hash, data["password"]):
        return jsonify({"error": "Invalid email or password"}), 401

    token = create_access_token(identity=str(user.id))
    return jsonify({"access_token": token, "user": user.to_dict()}), 200


@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    user = User.query.get_or_404(int(get_jwt_identity()))
    alerts = [a.to_dict() for a in user.alerts]
    return jsonify({"user": user.to_dict(), "alerts": alerts}), 200
