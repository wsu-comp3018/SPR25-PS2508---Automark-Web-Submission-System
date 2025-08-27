
from flask import Flask
from flask_cors import CORS
from routes import bp 

app = Flask(__name__)
CORS(app)  # allows frontend JS to call API endpoints

# Register your routes
app.register_blueprint(bp)

# Optional: secret key if you want to use sessions
app.secret_key = "your_secret_key_here"

# Run the Flask app
if __name__ == "__main__":
    app.run(debug=True)
