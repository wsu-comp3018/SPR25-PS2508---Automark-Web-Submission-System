"API endpoints"

from flask import Blueprint, request, jsonify
from auth import register_user, authenticate_user

bp = Blueprint("routes", __name__)

@bp.route("/api/register", methods=["POST"])
def register():
    data = request.get_json()
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")
    confirm_password = data.get("confirmPassword")
    role = data.get("role")
    first_name = data.get("first_name")
    last_name = data.get("last_name")

    if password != confirm_password:
        return jsonify({"success": False, "message": "Passwords do not match"}), 400

    try:
        register_user(username, email, password, role, first_name, last_name)
        return jsonify({"success": True, "message": "Account created successfully!"}), 201
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400


@bp.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()
    identifier = data.get("identifier")   # username or email
    password = data.get("password")

    user = authenticate_user(identifier, password)
    if user:
        return jsonify({
            "success": True,
            "message": "Login successful",
            "role": user["role"],
            "first_name": user["first_name"],
            "last_name": user["last_name"]
        }), 200
    else:
        return jsonify({"success": False, "message": "Invalid credentials"}), 401
